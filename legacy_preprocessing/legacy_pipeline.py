import math
import re
from collections import defaultdict
from typing import Dict, List, NamedTuple, Optional

import apache_beam as beam
import pyarrow.parquet as pq
from apache_beam.io import fileio
from apache_beam.io.filesystems import FileSystems
from apache_beam.io.parquetio import ReadFromParquet
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions
from google.cloud.bigtable import row as bt_row

from io_wrappers import WriteToBT
from storage_types import bigtable_storage_pb2

_SHARD_RE = re.compile(r"/shard_id=(\d+)/")


class EdgeBase(NamedTuple):
    u: int
    v: int
    weight: float


class NodeLocationRow(NamedTuple):
    node_id: int
    x: float
    y: float


beam.coders.registry.register_coder(EdgeBase, beam.coders.RowCoder)
beam.coders.registry.register_coder(NodeLocationRow, beam.coders.RowCoder)


def _extract_shard_id(path: str) -> int:
    match = _SHARD_RE.search(path)
    if not match:
        raise ValueError(f"Shard id not found in path: {path}")
    return int(match.group(1))


def _read_sharded_paths(pipeline, file_pattern, label, tag):
    return (
        pipeline
        | f"Match{label}Files" >> fileio.MatchFiles(file_pattern)
        | f"Read{label}Matches" >> fileio.ReadMatches()
        | f"Extract{label}Paths" >> beam.Map(lambda file: file.metadata.path)
        | f"Tag{label}Paths"
        >> beam.Map(lambda path: (_extract_shard_id(path), (tag, path)))
    )


def _edge_from_row(row) -> EdgeBase:
    return EdgeBase(u=int(row["u"]), v=int(row["v"]), weight=float(row["weight"]))


def _node_id_from_row(row) -> int:
    return int(row["node_id"])


def _node_location_from_row(row) -> NodeLocationRow:
    return NodeLocationRow(
        node_id=int(row["id"]), x=float(row["x"]), y=float(row["y"])
    )


def _weight_to_uint32(weight: float) -> int:
    if math.isnan(weight) or math.isinf(weight):
        return 0
    return max(0, int(round(weight)))


def _iter_parquet_rows(path: str, columns: Optional[List[str]] = None):
    with FileSystems.open(path) as file_handle:
        pq_file = pq.ParquetFile(file_handle)
        for batch in pq_file.iter_batches(columns=columns):
            for row in batch.to_pylist():
                yield row


class ReadShardFiles(beam.DoFn):
    def process(self, element):
        shard_id, tagged_paths = element
        paths_by_tag: Dict[str, List[str]] = defaultdict(list)
        for tag, path in tagged_paths:
            paths_by_tag[tag].append(path)

        edges: List[EdgeBase] = []
        for path in paths_by_tag.get("edges", []):
            for row in _iter_parquet_rows(path, columns=["u", "v", "weight"]):
                edges.append(_edge_from_row(row))

        nodes: List[NodeLocationRow] = []
        for path in paths_by_tag.get("nodes", []):
            for row in _iter_parquet_rows(path, columns=["id", "x", "y"]):
                nodes.append(_node_location_from_row(row))

        boundary_in: List[int] = []
        for path in paths_by_tag.get("boundary_in", []):
            for row in _iter_parquet_rows(path, columns=["node_id"]):
                boundary_in.append(_node_id_from_row(row))

        boundary_out: List[int] = []
        for path in paths_by_tag.get("boundary_out", []):
            for row in _iter_parquet_rows(path, columns=["node_id"]):
                boundary_out.append(_node_id_from_row(row))

        yield (
            shard_id,
            {
                "edges": edges,
                "nodes": nodes,
                "boundary_in": boundary_in,
                "boundary_out": boundary_out,
            },
        )


class ProcessShardLegacy(beam.DoFn):
    def process(self, element):
        shard_id, data = element
        edge_list = list(data.get("edges", []))
        node_locations = list(data.get("nodes", []))
        boundary_in = set(data.get("boundary_in", []))
        boundary_out = set(data.get("boundary_out", []))

        node_ids = [node.node_id for node in node_locations]
        id_to_idx = {node_id: idx for idx, node_id in enumerate(node_ids)}

        shard_pb = bigtable_storage_pb2.ShardGraph()
        for edge in edge_list:
            pb_edge = shard_pb.edges.add()
            pb_edge.from_node_id = edge.u
            pb_edge.to_node_id = edge.v
            pb_edge.weight = _weight_to_uint32(edge.weight)
            pb_edge.bidirectional = False

        for node in node_locations:
            loc = shard_pb.locations.add()
            loc.node_id = node.node_id
            loc.x = float(node.x)
            loc.y = float(node.y)
            yield beam.pvalue.TaggedOutput("node_index", (node.node_id, shard_id))

        yield beam.pvalue.TaggedOutput(
            "shard_pb", (shard_id, shard_pb.SerializeToString())
        )

        if not boundary_in or not boundary_out or not node_ids or not edge_list:
            return

        import igraph as ig

        source_ids = [n for n in boundary_in if n in id_to_idx]
        target_ids = [n for n in boundary_out if n in id_to_idx]

        if not source_ids or not target_ids:
            return

        source_idx = [id_to_idx[n] for n in source_ids]
        target_idx = [id_to_idx[n] for n in target_ids]

        edges_idx = []
        weights = []
        for edge in edge_list:
            if edge.u not in id_to_idx or edge.v not in id_to_idx:
                continue
            edges_idx.append((id_to_idx[edge.u], id_to_idx[edge.v]))
            weights.append(edge.weight)

        if not edges_idx:
            return

        graph = ig.Graph(n=len(node_ids), edges=edges_idx, directed=True)
        graph.es["weight"] = weights

        distances_matrix = graph.shortest_paths(
            source=source_idx, target=target_idx, weights="weight"
        )

        for src_i, src in enumerate(source_ids):
            row = distances_matrix[src_i]
            paths = graph.get_shortest_paths(
                source_idx[src_i], to=target_idx, weights="weight", output="vpath"
            )
            for dst_i, dst in enumerate(target_ids):
                if src == dst:
                    continue
                dist = row[dst_i]
                if dist == float("inf"):
                    continue
                path_vertices = paths[dst_i]
                if not path_vertices:
                    continue
                path_nodes = [node_ids[idx] for idx in path_vertices]
                weight = _weight_to_uint32(dist)
                yield beam.pvalue.TaggedOutput(
                    "shortcut_edge", ("shortcuts", src, dst, weight)
                )
                shortcut_pb = bigtable_storage_pb2.ShortcutPath()
                shortcut_pb.nodes.extend(path_nodes)
                yield beam.pvalue.TaggedOutput(
                    "shortcut_path", (src, dst, shortcut_pb.SerializeToString())
                )


class MergeOverlayGraphLegacy(beam.CombineFn):
    def create_accumulator(self):
        return {"bridges": [], "shortcuts": []}

    def add_input(self, accumulator, element):
        edge_type, u, v, weight = element
        accumulator[edge_type].append((u, v, weight))
        return accumulator

    def merge_accumulators(self, accumulators):
        merged = {"bridges": [], "shortcuts": []}
        for acc in accumulators:
            merged["bridges"].extend(acc["bridges"])
            merged["shortcuts"].extend(acc["shortcuts"])
        return merged

    def extract_output(self, accumulator):
        overlay_pb = bigtable_storage_pb2.OverlayGraph()
        for u, v, weight in accumulator["bridges"]:
            pb_edge = overlay_pb.bridges.add()
            pb_edge.from_node_id = u
            pb_edge.to_node_id = v
            pb_edge.weight = weight
            pb_edge.bidirectional = False
        for u, v, weight in accumulator["shortcuts"]:
            pb_edge = overlay_pb.shortcuts.add()
            pb_edge.from_node_id = u
            pb_edge.to_node_id = v
            pb_edge.weight = weight
            pb_edge.bidirectional = False
        return overlay_pb.SerializeToString()


def _make_direct_row(row_key, payload, column_family, qualifier):
    key_bytes = row_key.encode("utf-8") if isinstance(row_key, str) else row_key
    qual_bytes = qualifier.encode("utf-8") if isinstance(qualifier, str) else qualifier
    row = bt_row.DirectRow(row_key=key_bytes)
    row.set_cell(column_family, qual_bytes, payload)
    return row


def create_legacy_pipeline(
    project,
    temp_location,
    input_base,
    instance_id,
    setup_file,
    pipeline_args=None,
    shards_table="shards",
    shortcuts_table="shortcuts",
    node_index_table="node_index",
    overlay_graph_table="overlay_graph",
    column_family="cf",
    qualifier="data",
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

    input_base = input_base.rstrip("/")

    nodes_pattern = f"{input_base}/shard_id=*/nodes/*.parquet"
    edges_pattern = f"{input_base}/shard_id=*/edges/*.parquet"
    boundary_in_pattern = f"{input_base}/shard_id=*/boundary_in/*.parquet"
    boundary_out_pattern = f"{input_base}/shard_id=*/boundary_out/*.parquet"
    bridges_pattern = f"{input_base}/bridges/*.parquet"

    with beam.Pipeline(options=options) as p:
        shard_paths = (
            _read_sharded_paths(p, nodes_pattern, "Nodes", "nodes"),
            _read_sharded_paths(p, edges_pattern, "Edges", "edges"),
            _read_sharded_paths(p, boundary_in_pattern, "BoundaryIn", "boundary_in"),
            _read_sharded_paths(p, boundary_out_pattern, "BoundaryOut", "boundary_out"),
        ) | "FlattenShardPaths" >> beam.Flatten()

        shard_data = (
            shard_paths
            | "GroupShardPaths" >> beam.GroupByKey()
            | "ReadShardFiles" >> beam.ParDo(ReadShardFiles())
        )

        shard_results = shard_data | "ProcessShardLegacy" >> beam.ParDo(
            ProcessShardLegacy()
        ).with_outputs("shard_pb", "shortcut_edge", "shortcut_path", "node_index")

        shard_pbs = shard_results.shard_pb
        shortcut_edges = shard_results.shortcut_edge
        shortcut_paths = shard_results.shortcut_path
        node_index = shard_results.node_index

        make_row = lambda row_key, payload: _make_direct_row(
            row_key, payload, column_family, qualifier
        )

        shard_rows = shard_pbs | "ShardToBT" >> beam.Map(
            lambda kv: make_row(f"S#{kv[0]}", kv[1])
        )
        _ = shard_rows | "WriteShardsBT" >> WriteToBT(
            project_id=project, instance_id=instance_id, table_id=shards_table
        )

        node_index_rows = node_index | "NodeIndexToBT" >> beam.Map(
            lambda kv: make_row(
                f"N#{kv[0]}",
                bigtable_storage_pb2.ShardLookup(shard_id=kv[1]).SerializeToString(),
            )
        )
        _ = node_index_rows | "WriteNodeIndexBT" >> WriteToBT(
            project_id=project, instance_id=instance_id, table_id=node_index_table
        )

        shortcut_rows = shortcut_paths | "ShortcutToBT" >> beam.Map(
            lambda element: make_row(f"P#{element[0]}#{element[1]}", element[2])
        )
        _ = shortcut_rows | "WriteShortcutsBT" >> WriteToBT(
            project_id=project, instance_id=instance_id, table_id=shortcuts_table
        )

        bridges = (
            p
            | "ReadBridges" >> ReadFromParquet(bridges_pattern)
            | "NormalizeBridges"
            >> beam.Map(
                lambda row: (
                    "bridges",
                    int(row["u"]),
                    int(row["v"]),
                    _weight_to_uint32(row["weight"]),
                )
            )
        )

        overlay_edges = (bridges, shortcut_edges) | "FlattenOverlayEdges" >> beam.Flatten()
        overlay_pb = overlay_edges | "MergeOverlayGraphLegacy" >> beam.CombineGlobally(
            MergeOverlayGraphLegacy()
        )

        overlay_rows = overlay_pb | "OverlayToBT" >> beam.Map(
            lambda payload: make_row("O#", payload)
        )
        _ = overlay_rows | "WriteOverlayBT" >> WriteToBT(
            project_id=project, instance_id=instance_id, table_id=overlay_graph_table
        )
