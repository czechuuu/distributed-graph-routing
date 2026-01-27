import apache_beam as beam
import heapq
import math
import re
from collections import defaultdict
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

import pyarrow.parquet as pq
from apache_beam.io import fileio
from apache_beam.io.filesystems import FileSystems
from apache_beam.io.parquetio import ReadFromParquet
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions

from .io_wrappers import WriteBytesByDestination
from shared.protos import gcs_storage_pb2

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


def _dijkstra_targets(
    adjacency: Dict[int, List[Tuple[int, float]]],
    source: int,
    targets: Set[int],
) -> Dict[int, float]:
    if not targets:
        return {}

    distances: Dict[int, float] = {source: 0.0}
    heap: List[Tuple[float, int]] = [(0.0, source)]
    remaining = set(targets)
    found: Dict[int, float] = {}

    while heap and remaining:
        dist_u, u = heapq.heappop(heap)
        if dist_u != distances.get(u):
            continue

        if u in remaining:
            found[u] = dist_u
            remaining.remove(u)
            if not remaining:
                break

        for v, weight in adjacency.get(u, []):
            nd = dist_u + weight
            if nd < distances.get(v, math.inf):
                distances[v] = nd
                heapq.heappush(heap, (nd, v))

    return found


class ProcessShard(beam.DoFn):
    def process(self, element):
        shard_id, data = element
        edge_list = list(data.get("edges", []))
        node_locations = list(data.get("nodes", []))
        boundary_in = set(data.get("boundary_in", []))
        boundary_out = set(data.get("boundary_out", []))
        boundary_nodes = boundary_in | boundary_out

        node_ids = [node.node_id for node in node_locations]
        id_to_idx = {node_id: idx for idx, node_id in enumerate(node_ids)}

        shard_pb = gcs_storage_pb2.ShardGraph()
        shard_pb.boundary_in_node_ids.extend(sorted(boundary_in))
        shard_pb.boundary_out_node_ids.extend(sorted(boundary_out))
        for edge in edge_list:
            pb_edge = shard_pb.edges.add()
            pb_edge.from_node_id = edge.u
            pb_edge.to_node_id = edge.v
            pb_edge.weight = _weight_to_uint32(edge.weight)
            pb_edge.bidirectional = False

        node_lookup = {}
        for node in node_locations:
            node_lookup[node.node_id] = node
            loc = shard_pb.locations.add()
            loc.node_id = node.node_id
            loc.x = node.x
            loc.y = node.y

        yield beam.pvalue.TaggedOutput(
            "shard_pb", (shard_id, shard_pb.SerializeToString())
        )

        shortcut_edges: List[Tuple[int, int, int]] = []
        if boundary_in and boundary_out and node_ids and edge_list:
            # Use igraph for faster shortest-paths on each shard.
            import igraph as ig

            source_ids = [n for n in boundary_in if n in id_to_idx]
            target_ids = [n for n in boundary_out if n in id_to_idx]

            if source_ids and target_ids:
                source_idx = [id_to_idx[n] for n in source_ids]
                target_idx = [id_to_idx[n] for n in target_ids]

                edges_idx = []
                weights = []
                for edge in edge_list:
                    if edge.u not in id_to_idx or edge.v not in id_to_idx:
                        continue
                    edges_idx.append((id_to_idx[edge.u], id_to_idx[edge.v]))
                    weights.append(edge.weight)

                graph = ig.Graph(n=len(node_ids), edges=edges_idx, directed=True)
                graph.es["weight"] = weights

                distances_matrix = graph.shortest_paths(
                    source=source_idx, target=target_idx, weights="weight"
                )

                for src_i, src in enumerate(source_ids):
                    row = distances_matrix[src_i]
                    for dst_i, dst in enumerate(target_ids):
                        if src == dst:
                            continue
                        dist = row[dst_i]
                        if dist == float("inf"):
                            continue
                        weight = _weight_to_uint32(dist)
                        shortcut_edges.append((src, dst, weight))
                        yield beam.pvalue.TaggedOutput(
                            "shortcuts_edge", ("shortcuts", src, dst, weight)
                        )

        shortcuts_pb = gcs_storage_pb2.Shortcuts()
        for src, dst, weight in shortcut_edges:
            pb_edge = shortcuts_pb.edges.add()
            pb_edge.from_node_id = src
            pb_edge.to_node_id = dst
            pb_edge.weight = weight
            pb_edge.bidirectional = False

        yield beam.pvalue.TaggedOutput(
            "shortcuts_pb", (shard_id, shortcuts_pb.SerializeToString())
        )

        for node_id in boundary_nodes:
            node = node_lookup.get(node_id)
            if node:
                yield beam.pvalue.TaggedOutput(
                    "boundary_location",
                    ("boundary_location", node.node_id, node.x, node.y),
                )


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

        yield (shard_id, {
            "edges": edges,
            "nodes": nodes,
            "boundary_in": boundary_in,
            "boundary_out": boundary_out,
        })


class MergeOverlayGraph(beam.CombineFn):
    def create_accumulator(self):
        return {"bridges": [], "shortcuts": [], "boundary_locations": {}}

    def add_input(self, accumulator, element):
        edge_type, *rest = element
        if edge_type == "boundary_location":
            node_id, x, y = rest
            if node_id not in accumulator["boundary_locations"]:
                accumulator["boundary_locations"][node_id] = (x, y)
        else:
            u, v, weight = rest
            accumulator[edge_type].append((u, v, weight))
        return accumulator

    def merge_accumulators(self, accumulators):
        merged = {"bridges": [], "shortcuts": [], "boundary_locations": {}}
        for acc in accumulators:
            merged["bridges"].extend(acc["bridges"])
            merged["shortcuts"].extend(acc["shortcuts"])
            merged["boundary_locations"].update(acc["boundary_locations"])
        return merged

    def extract_output(self, accumulator):
        overlay_pb = gcs_storage_pb2.OverlayGraph()

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

        for node_id, (x, y) in accumulator["boundary_locations"].items():
            loc = overlay_pb.boundary_locations.add()
            loc.node_id = node_id
            loc.x = x
            loc.y = y

        return overlay_pb.SerializeToString()


def create_job2_pipeline(
    project,
    temp_location,
    input_base,
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

    input_base = input_base.rstrip("/")
    output_base = output_base.rstrip("/")

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

        shard_results = shard_data | "ProcessShard" >> beam.ParDo(ProcessShard()).with_outputs(
            "shard_pb", "shortcuts_pb", "shortcuts_edge", "boundary_location"
        )

        shard_pbs = shard_results.shard_pb
        shortcuts_pbs = shard_results.shortcuts_pb
        shortcut_edges = shard_results.shortcuts_edge
        boundary_locations = shard_results.boundary_location

        _ = shard_pbs | "WriteShardProtos" >> WriteBytesByDestination(
            base_path=output_base,
            destination_fn=lambda kv: f"shard_id={kv[0]}/shard_graph",
            file_name_suffix=".pb",
            shards=1,
        )

        _ = shortcuts_pbs | "WriteShortcutProtos" >> WriteBytesByDestination(
            base_path=output_base,
            destination_fn=lambda kv: f"shard_id={kv[0]}/shortcuts",
            file_name_suffix=".pb",
            shards=1,
        )

        bridges = (
            p
            | "ReadBridges" >> ReadFromParquet(bridges_pattern)
            | "NormalizeBridges"
            >> beam.Map(lambda row: ("bridges", int(row["u"]), int(row["v"]), _weight_to_uint32(row["weight"])))
        )

        overlay_edges = (
            bridges,
            shortcut_edges,
            boundary_locations,
        ) | "FlattenOverlayEdges" >> beam.Flatten()

        overlay_pb = overlay_edges | "MergeOverlayGraph" >> beam.CombineGlobally(
            MergeOverlayGraph()
        )

        _ = overlay_pb | "WriteOverlay" >> WriteBytesByDestination(
            base_path=output_base,
            destination_fn=lambda _: "overlay_graph",
            file_name_suffix=".pb",
            shards=1,
        )
