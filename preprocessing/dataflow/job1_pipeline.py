import apache_beam as beam
import pyarrow as pa
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions
from s2sphere import CellId, LatLng
from typing import Iterable, NamedTuple, Optional

from .io_wrappers import (
    ReadNodesFromParquet,
    ReadEdgesFromParquet,
    WriteParquet,
    WriteToParquetByDestination,
)

S2_LEVEL = 9


class NodeRow(NamedTuple):
    id: int
    x: float
    y: float
    shard_id: int


class EdgeBase(NamedTuple):
    u: int
    v: int
    weight: float


class EdgeWithU(NamedTuple):
    u: int
    v: int
    weight: float
    shard_u: int


class EdgeWithShards(NamedTuple):
    u: int
    v: int
    weight: float
    shard_u: int
    shard_v: int


class BoundaryNode(NamedTuple):
    shard_id: int
    node_id: int


beam.coders.registry.register_coder(NodeRow, beam.coders.RowCoder)
beam.coders.registry.register_coder(EdgeBase, beam.coders.RowCoder)
beam.coders.registry.register_coder(EdgeWithU, beam.coders.RowCoder)
beam.coders.registry.register_coder(EdgeWithShards, beam.coders.RowCoder)
beam.coders.registry.register_coder(BoundaryNode, beam.coders.RowCoder)


def _compute_shard_id(x, y):
    lat_lng = LatLng.from_degrees(y, x)
    return int(CellId.from_lat_lng(lat_lng).parent(S2_LEVEL).id())


def _normalize_node(row):
    node_id = int(row["id"])
    x = float(row["x"])
    y = float(row["y"])
    shard_id = _compute_shard_id(x, y)
    return NodeRow(id=node_id, x=x, y=y, shard_id=shard_id)


def _normalize_edge(row):
    return EdgeBase(u=int(row["u"]), v=int(row["v"]), weight=float(row["weight"]))


def _first_or_none(values: Iterable[int]) -> Optional[int]:
    for value in values:
        return value
    return None


def _attach_shard_u(element):
    node_id, grouped = element
    shard_u = _first_or_none(grouped["node_id_shard"])
    edges_iter = grouped["edges_u"]
    saw_edge = False

    for edge in edges_iter:
        saw_edge = True
        if shard_u is None:
            raise ValueError(
                f"Node {node_id} referenced by edge(s) but not found in nodes input."
            )
        yield (
            edge.v,
            EdgeWithU(u=edge.u, v=edge.v, weight=edge.weight, shard_u=shard_u),
        )

    if not saw_edge:
        return


def _attach_shard_v(element):
    node_id, grouped = element
    shard_v = _first_or_none(grouped["node_id_shard"])
    edges_iter = grouped["edges_with_u"]
    saw_edge = False

    for edge in edges_iter:
        saw_edge = True
        if shard_v is None:
            raise ValueError(
                f"Node {node_id} referenced as edge target but not found in nodes input."
            )
        yield EdgeWithShards(
            u=edge.u,
            v=edge.v,
            weight=edge.weight,
            shard_u=edge.shard_u,
            shard_v=shard_v,
        )

    if not saw_edge:
        return


def _destination_for_shard(prefix, shard_id):
    return f"shard_id={shard_id}/{prefix}/part"


def create_job1_pipeline(
    project,
    temp_location,
    input_nodes,
    input_edges,
    output_base,
    setup_file,
    pipeline_args=None,
):
    if pipeline_args is None:
        pipeline_args = []

    is_dataflow = any("DataflowRunner" in arg for arg in pipeline_args)
    if is_dataflow:
        pipeline_args.append("--prebuild_sdk_container_engine=cloud_build")
        pipeline_args.append(
            f"--docker_registry_push_url=gcr.io/{project}/dataflow/graph-routing-worker-sdk"
        )
        pipeline_args.append("--experiments=use_runner_v2")
        pipeline_args.append(
            f"--sdk_container_image=docker.io/apache/beam_python3.11_sdk:{beam.version.__version__}"
        )

    options = PipelineOptions(flags=pipeline_args)
    options.view_as(SetupOptions).save_main_session = True

    google_cloud_options = options.view_as(
        beam.options.pipeline_options.GoogleCloudOptions
    )
    google_cloud_options.project = project
    google_cloud_options.temp_location = temp_location

    setup_options = options.view_as(SetupOptions)
    setup_options.setup_file = setup_file

    output_base = output_base.rstrip("/")

    # Output schemas: keep per-shard outputs minimal to avoid duplication.
    # (Parquet writer ignores extra fields when a schema is provided.)
    node_schema = pa.schema(
        [
            ("id", pa.int64()),
            ("x", pa.float64()),
            ("y", pa.float64()),
        ]
    )
    internal_edge_schema = pa.schema(
        [
            ("u", pa.int64()),
            ("v", pa.int64()),
            ("weight", pa.float64()),
        ]
    )
    bridge_edge_schema = pa.schema(
        [
            ("u", pa.int64()),
            ("v", pa.int64()),
            ("weight", pa.float64()),
            ("shard_u", pa.int64()),
            ("shard_v", pa.int64()),
        ]
    )
    boundary_schema = pa.schema([("node_id", pa.int64())])

    with beam.Pipeline(options=options) as p:
        nodes = (
            p
            | "ReadNodes" >> ReadNodesFromParquet(input_nodes)
            | "NormalizeNodes" >> beam.Map(_normalize_node)
        )
        edges = (
            p
            | "ReadEdges" >> ReadEdgesFromParquet(input_edges)
            | "NormalizeEdges" >> beam.Map(_normalize_edge)
        )

        node_id_shard = nodes | "KeyNodesById" >> beam.Map(
            lambda n: (n.id, n.shard_id)
        )
        edges_keyed_by_u = edges | "KeyEdgesByU" >> beam.Map(lambda e: (e.u, e))

        edges_with_u_shard = (
            {"node_id_shard": node_id_shard, "edges_u": edges_keyed_by_u}
            | "GroupEdgesAndNodesByU" >> beam.CoGroupByKey()
            | "AttachShardU" >> beam.FlatMap(_attach_shard_u)
        )

        edges_with_shards = (
            {"node_id_shard": node_id_shard, "edges_with_u": edges_with_u_shard}
            | "GroupEdgesAndNodesByV" >> beam.CoGroupByKey()
            | "AttachShardV" >> beam.FlatMap(_attach_shard_v)
        )

        bridges = edges_with_shards | "FilterBridges" >> beam.Filter(
            lambda e: e.shard_u != e.shard_v
        )
        internal_edges = edges_with_shards | "FilterInternalEdges" >> beam.Filter(
            lambda e: e.shard_u == e.shard_v
        )

        # Use primitive tuples for Distinct() to avoid Dataflow falling back to a
        # deterministic coder for BoundaryNode (which adds CPU overhead).
        boundary_in = (
            bridges
            | "BoundaryInPairs" >> beam.Map(lambda e: (e.shard_v, e.v))
            | "DistinctBoundaryIn" >> beam.Distinct()
            | "BoundaryInRows" >> beam.Map(lambda kv: BoundaryNode(shard_id=kv[0], node_id=kv[1]))
        )
        boundary_out = (
            bridges
            | "BoundaryOutPairs" >> beam.Map(lambda e: (e.shard_u, e.u))
            | "DistinctBoundaryOut" >> beam.Distinct()
            | "BoundaryOutRows" >> beam.Map(lambda kv: BoundaryNode(shard_id=kv[0], node_id=kv[1]))
        )

        _ = bridges | "WriteBridges" >> WriteParquet(
            file_path_prefix=f"{output_base}/bridges/part", schema=bridge_edge_schema
        )

        _ = internal_edges | "WriteShardEdges" >> WriteToParquetByDestination(
            base_path=output_base,
            schema=internal_edge_schema,
            destination_fn=lambda e: _destination_for_shard("edges", e.shard_u),
        )
        _ = nodes | "WriteShardNodes" >> WriteToParquetByDestination(
            base_path=output_base,
            schema=node_schema,
            destination_fn=lambda n: _destination_for_shard("nodes", n.shard_id),
        )
        _ = boundary_in | "WriteBoundaryIn" >> WriteToParquetByDestination(
            base_path=output_base,
            schema=boundary_schema,
            destination_fn=lambda n: _destination_for_shard("boundary_in", n.shard_id),
        )
        _ = boundary_out | "WriteBoundaryOut" >> WriteToParquetByDestination(
            base_path=output_base,
            schema=boundary_schema,
            destination_fn=lambda n: _destination_for_shard("boundary_out", n.shard_id),
        )
