import apache_beam as beam
import pyarrow as pa
import pyarrow.parquet as pq
from apache_beam.io import fileio
from apache_beam.io.gcp.bigquery import ReadFromBigQuery
from apache_beam.io.gcp.bigtableio import WriteToBigTable
from apache_beam.io.parquetio import ReadFromParquet, WriteToParquet as BeamWriteToParquet
from google.cloud.bigtable import row

class ReadNodesFromBQ(beam.PTransform):
    def __init__(self, table):
        self.table = table

    def expand(self, pcoll):
        return (
            pcoll 
            | "ReadNodes" >> ReadFromBigQuery(table=self.table)
            | "ParseNode" >> beam.Map(lambda row: {
                "id": row["id"],
                "x": row["x"],
                "y": row["y"],
                "shard_id": row["ShardId"],
            })
        )

class ReadEdgesFromBQ(beam.PTransform):
    def __init__(self, table):
        self.table = table

    def expand(self, pcoll):
        return (
            pcoll 
            | "ReadEdges" >> ReadFromBigQuery(table=self.table)
            | "ParseEdge" >> beam.Map(lambda row: {
                "u": row["u"],
                "v": row["v"],
                "weight": row["weight"],
            })
        )

class WriteToBT(beam.PTransform):
    def __init__(self, project_id, instance_id, table_id):
        self.project_id = project_id
        self.instance_id = instance_id
        self.table_id = table_id

    def expand(self, pcoll):
        # Expects pcoll of DirectRow objects
        return pcoll | WriteToBigTable(
            project_id=self.project_id,
            instance_id=self.instance_id,
            table_id=self.table_id
        )


class ReadNodesFromParquet(beam.PTransform):
    def __init__(self, file_pattern):
        self.file_pattern = file_pattern

    def expand(self, pcoll):
        return (
            pcoll
            | "ReadNodesParquet" >> ReadFromParquet(self.file_pattern)
        )


class ReadEdgesFromParquet(beam.PTransform):
    def __init__(self, file_pattern):
        self.file_pattern = file_pattern

    def expand(self, pcoll):
        return (
            pcoll
            | "ReadEdgesParquet" >> ReadFromParquet(self.file_pattern)
        )


class WriteParquet(beam.PTransform):
    def __init__(self, file_path_prefix, schema, file_name_suffix=".parquet"):
        self.file_path_prefix = file_path_prefix
        self.schema = schema
        self.file_name_suffix = file_name_suffix

    def expand(self, pcoll):
        return (
            pcoll
            | "NormalizeParquetRows" >> beam.Map(_normalize_record)
            | BeamWriteToParquet(
                file_path_prefix=self.file_path_prefix,
                schema=self.schema,
                file_name_suffix=self.file_name_suffix,
            )
        )


class _ParquetFileSink(fileio.FileSink):
    def __init__(self, schema, batch_size=50_000):
        self.schema = schema
        self.batch_size = batch_size
        self._writer = None
        self._buffer = []

    def open(self, file_handle):
        self._writer = pq.ParquetWriter(file_handle, self.schema)
        self._buffer = []

    def write(self, record):
        self._buffer.append(_normalize_record(record))
        if len(self._buffer) >= self.batch_size:
            self._flush_buffer()

    def flush(self):
        self._flush_buffer()
        if self._writer:
            self._writer.close()
            self._writer = None

    def _flush_buffer(self):
        if not self._buffer:
            return
        table = pa.Table.from_pylist(self._buffer, schema=self.schema)
        self._writer.write_table(table)
        self._buffer = []


class WriteToParquetByDestination(beam.PTransform):
    def __init__(self, base_path, schema, destination_fn, file_name_suffix=".parquet"):
        self.base_path = base_path
        self.schema = schema
        self.destination_fn = destination_fn
        self.file_name_suffix = file_name_suffix

    def expand(self, pcoll):
        return pcoll | "WriteByDestination" >> fileio.WriteToFiles(
            path=self.base_path,
            destination=self.destination_fn,
            sink=lambda _: _ParquetFileSink(self.schema),
            file_naming=fileio.destination_prefix_naming(suffix=self.file_name_suffix)
        )


class _BytesFileSink(fileio.FileSink):
    def open(self, file_handle):
        self._file_handle = file_handle

    def write(self, record):
        data = _normalize_bytes_record(record)
        if data:
            self._file_handle.write(data)

    def flush(self):
        if self._file_handle:
            self._file_handle.flush()
            self._file_handle = None


class WriteBytesByDestination(beam.PTransform):
    def __init__(self, base_path, destination_fn, file_name_suffix=".pb", shards=1):
        self.base_path = base_path
        self.destination_fn = destination_fn
        self.file_name_suffix = file_name_suffix
        self.shards = shards

    def expand(self, pcoll):
        return pcoll | "WriteBytesByDestination" >> fileio.WriteToFiles(
            path=self.base_path,
            destination=self.destination_fn,
            sink=lambda _: _BytesFileSink(),
            shards=self.shards,
            file_naming=_fixed_destination_naming(suffix=self.file_name_suffix),
        )


def _fixed_destination_naming(suffix=""):
    def _inner(window, pane, shard_index, total_shards, compression, destination):
        return f"{destination}{suffix}"

    return _inner


def _normalize_record(record):
    if hasattr(record, "_asdict"):
        return record._asdict()
    if hasattr(record, "as_dict"):
        return record.as_dict()
    return record


def _normalize_bytes_record(record):
    if isinstance(record, (bytes, bytearray, memoryview)):
        return bytes(record)
    if isinstance(record, tuple) and len(record) == 2 and isinstance(record[1], (bytes, bytearray, memoryview)):
        return bytes(record[1])
    return None
