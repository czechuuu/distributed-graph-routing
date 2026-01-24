import os
import tempfile
from typing import Iterable, NamedTuple, Optional, Tuple

import apache_beam as beam
import osmium
import pyarrow as pa
from apache_beam.io import fileio
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions
from s2sphere import CellId, LatLng

from .io_wrappers import WriteParquet, WriteToParquetByDestination
from .osm_edges import expand_way_nodes
from .osm_weights import choose_speed_kph, distance_equirectangular_m, weight_seconds

DRIVEABLE_HIGHWAY_TYPES = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
    "living_street",
    "service",
    "road",
}

S2_LEVEL = 9


class NodeRow(NamedTuple):
    id: int
    x: float
    y: float


class EdgeCandidate(NamedTuple):
    u: int
    v: int
    direction: int
    highway: Optional[str]
    maxspeed: Optional[str]
    maxspeed_forward: Optional[str]
    maxspeed_backward: Optional[str]
    surface: Optional[str]
    tracktype: Optional[str]
    service: Optional[str]


class EdgeWithU(NamedTuple):
    u: int
    v: int
    direction: int
    highway: Optional[str]
    maxspeed: Optional[str]
    maxspeed_forward: Optional[str]
    maxspeed_backward: Optional[str]
    surface: Optional[str]
    tracktype: Optional[str]
    service: Optional[str]
    x_u: float
    y_u: float
    shard_u: int


class EdgeWithShards(NamedTuple):
    u: int
    v: int
    direction: int
    highway: Optional[str]
    maxspeed: Optional[str]
    maxspeed_forward: Optional[str]
    maxspeed_backward: Optional[str]
    surface: Optional[str]
    tracktype: Optional[str]
    service: Optional[str]
    x_u: float
    y_u: float
    x_v: float
    y_v: float
    shard_u: int
    shard_v: int


class EdgeSlim(NamedTuple):
    u: int
    v: int
    weight: int
    shard_u: int
    shard_v: int


class NodeOut(NamedTuple):
    id: int
    x: float
    y: float
    shard_id: int


class BoundaryNode(NamedTuple):
    shard_id: int
    node_id: int


beam.coders.registry.register_coder(NodeRow, beam.coders.RowCoder)
beam.coders.registry.register_coder(EdgeCandidate, beam.coders.RowCoder)
beam.coders.registry.register_coder(EdgeWithU, beam.coders.RowCoder)
beam.coders.registry.register_coder(EdgeWithShards, beam.coders.RowCoder)
beam.coders.registry.register_coder(EdgeSlim, beam.coders.RowCoder)
beam.coders.registry.register_coder(NodeOut, beam.coders.RowCoder)
beam.coders.registry.register_coder(BoundaryNode, beam.coders.RowCoder)


def _compute_shard_id(x: float, y: float) -> int:
    lat_lng = LatLng.from_degrees(y, x)
    return int(CellId.from_lat_lng(lat_lng).parent(S2_LEVEL).id())


def _first_or_none(values: Iterable[NodeRow]) -> Optional[NodeRow]:
    for value in values:
        return value
    return None


def _min_edge_from_iter(values: Iterable[EdgeSlim]) -> Optional[EdgeSlim]:
    best = None
    for value in values:
        if best is None or value.weight < best.weight:
            best = value
    return best


class _PbfHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.nodes: list[NodeRow] = []
        self.edges: list[EdgeCandidate] = []

    def node(self, n):
        if not n.location:
            return
        self.nodes.append(NodeRow(id=int(n.id), x=float(n.location.lon), y=float(n.location.lat)))

    def way(self, w):
        highway = w.tags.get("highway")
        if highway not in DRIVEABLE_HIGHWAY_TYPES:
            return
        tags = dict(w.tags)
        for edge in expand_way_nodes([node.ref for node in w.nodes], tags):
            self.edges.append(
                EdgeCandidate(
                    u=edge.u,
                    v=edge.v,
                    direction=edge.direction,
                    highway=tags.get("highway"),
                    maxspeed=tags.get("maxspeed"),
                    maxspeed_forward=tags.get("maxspeed:forward"),
                    maxspeed_backward=tags.get("maxspeed:backward"),
                    surface=tags.get("surface"),
                    tracktype=tags.get("tracktype"),
                    service=tags.get("service"),
                )
            )


class ParsePbfDoFn(beam.DoFn):
    def process(self, readable_file: fileio.ReadableFile):
        import logging
        tmp_path = None
        try:
            with readable_file.open() as handle, tempfile.NamedTemporaryFile(
                suffix=".osm.pbf", delete=False
            ) as tmp:
                while True:
                    chunk = handle.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
                tmp_path = tmp.name

            handler = _PbfHandler()
            try:
                handler.apply_file(tmp_path, locations=True)
            except RuntimeError as e:
                # Handle empty or corrupted PBF files gracefully
                file_path = getattr(readable_file.metadata, 'path', 'unknown')
                logging.warning(f"Skipping file {file_path}: {e}")
                return  # Skip this file, don't yield any nodes/edges
            
            for node in handler.nodes:
                yield beam.pvalue.TaggedOutput("nodes", node)
            for edge in handler.edges:
                yield beam.pvalue.TaggedOutput("edges", edge)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


def _attach_shard_u(element: Tuple[int, dict]):
    node_id, grouped = element
    node = _first_or_none(grouped["nodes"])
    edges_iter = grouped["edges"]
    saw_edge = False

    for edge in edges_iter:
        saw_edge = True
        if node is None:
            raise ValueError(f"Node {node_id} referenced by edge(s) but not found in nodes input.")
        shard_u = _compute_shard_id(node.x, node.y)
        yield (
            edge.v,
            EdgeWithU(
                u=edge.u,
                v=edge.v,
                direction=edge.direction,
                highway=edge.highway,
                maxspeed=edge.maxspeed,
                maxspeed_forward=edge.maxspeed_forward,
                maxspeed_backward=edge.maxspeed_backward,
                surface=edge.surface,
                tracktype=edge.tracktype,
                service=edge.service,
                x_u=node.x,
                y_u=node.y,
                shard_u=shard_u,
            ),
        )

    if not saw_edge:
        return


def _attach_shard_v(element: Tuple[int, dict]):
    node_id, grouped = element
    node = _first_or_none(grouped["nodes"])
    edges_iter = grouped["edges_with_u"]
    saw_edge = False

    for edge in edges_iter:
        saw_edge = True
        if node is None:
            raise ValueError(
                f"Node {node_id} referenced as edge target but not found in nodes input."
            )
        shard_v = _compute_shard_id(node.x, node.y)
        yield EdgeWithShards(
            u=edge.u,
            v=edge.v,
            direction=edge.direction,
            highway=edge.highway,
            maxspeed=edge.maxspeed,
            maxspeed_forward=edge.maxspeed_forward,
            maxspeed_backward=edge.maxspeed_backward,
            surface=edge.surface,
            tracktype=edge.tracktype,
            service=edge.service,
            x_u=edge.x_u,
            y_u=edge.y_u,
            x_v=node.x,
            y_v=node.y,
            shard_u=edge.shard_u,
            shard_v=shard_v,
        )

    if not saw_edge:
        return


class ComputeWeightAndNodes(beam.DoFn):
    def __init__(self, weight_mode: str):
        self._weight_mode = weight_mode

    def process(self, edge: EdgeWithShards):
        length_m = distance_equirectangular_m(edge.y_u, edge.x_u, edge.y_v, edge.x_v)
        if self._weight_mode == "distance_m":
            weight = int(round(length_m))
        else:
            speed_kph = choose_speed_kph(
                highway=edge.highway,
                maxspeed=edge.maxspeed,
                maxspeed_forward=edge.maxspeed_forward,
                maxspeed_backward=edge.maxspeed_backward,
                surface=edge.surface,
                tracktype=edge.tracktype,
                service=edge.service,
                direction=edge.direction,
            )
            weight = weight_seconds(length_m, speed_kph)
        yield EdgeSlim(
            u=edge.u,
            v=edge.v,
            weight=weight,
            shard_u=edge.shard_u,
            shard_v=edge.shard_v,
        )
        yield beam.pvalue.TaggedOutput(
            "nodes",
            NodeOut(id=edge.u, x=edge.x_u, y=edge.y_u, shard_id=edge.shard_u),
        )
        yield beam.pvalue.TaggedOutput(
            "nodes",
            NodeOut(id=edge.v, x=edge.x_v, y=edge.y_v, shard_id=edge.shard_v),
        )


def _destination_for_shard(prefix: str, shard_id: int) -> str:
    return f"shard_id={shard_id}/{prefix}/part"


def create_job0_pipeline(
    project: str,
    temp_location: str,
    input_pbf: str,
    output_base: str,
    weight_mode: str,
    setup_file: str,
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

    internal_edge_schema = pa.schema(
        [
            ("u", pa.int64()),
            ("v", pa.int64()),
            ("weight", pa.int64()),
        ]
    )
    bridge_edge_schema = pa.schema(
        [
            ("u", pa.int64()),
            ("v", pa.int64()),
            ("weight", pa.int64()),
            ("shard_u", pa.int64()),
            ("shard_v", pa.int64()),
        ]
    )
    node_schema = pa.schema(
        [
            ("id", pa.int64()),
            ("x", pa.float64()),
            ("y", pa.float64()),
        ]
    )
    boundary_schema = pa.schema([("node_id", pa.int64())])

    with beam.Pipeline(options=options) as p:
        parsed = (
            p
            | "MatchPbfFiles" >> fileio.MatchFiles(input_pbf)
            | "ReadPbfMatches" >> fileio.ReadMatches()
            | "ParsePbfFiles" >> beam.ParDo(ParsePbfDoFn()).with_outputs("nodes", "edges")
        )

        nodes = parsed.nodes
        edges = parsed.edges

        node_kv = nodes | "KeyNodesById" >> beam.Map(lambda n: (n.id, n))
        node_dedup = node_kv | "DedupNodesById" >> beam.CombinePerKey(_first_or_none)

        edges_by_u = edges | "KeyEdgesByU" >> beam.Map(lambda e: (e.u, e))
        edges_with_u = (
            {"nodes": node_dedup, "edges": edges_by_u}
            | "JoinEdgesWithU" >> beam.CoGroupByKey()
            | "AttachShardU" >> beam.FlatMap(_attach_shard_u)
        )

        edges_with_shards = (
            {"nodes": node_dedup, "edges_with_u": edges_with_u}
            | "JoinEdgesWithV" >> beam.CoGroupByKey()
            | "AttachShardV" >> beam.FlatMap(_attach_shard_v)
        )

        weighted = edges_with_shards | "ComputeWeightsAndNodes" >> beam.ParDo(
            ComputeWeightAndNodes(weight_mode)
        ).with_outputs("nodes")

        edge_slim = weighted[None]
        node_out = weighted.nodes

        node_out_dedup = (
            node_out
            | "KeyOutputNodes" >> beam.Map(lambda n: (n.id, n))
            | "DedupOutputNodes" >> beam.CombinePerKey(_first_or_none)
            | "DropOutputNodeKeys" >> beam.Map(lambda kv: kv[1])
        )

        edge_kv = edge_slim | "KeyEdgesByUV" >> beam.Map(lambda e: ((e.u, e.v), e))
        edge_dedup = (
            edge_kv
            | "DedupEdgesByUV" >> beam.CombinePerKey(_min_edge_from_iter)
            | "DropEdgeKeys" >> beam.Map(lambda kv: kv[1])
        )

        internal_edges = edge_dedup | "FilterInternalEdges" >> beam.Filter(
            lambda e: e.shard_u == e.shard_v
        )
        bridges = edge_dedup | "FilterBridgeEdges" >> beam.Filter(
            lambda e: e.shard_u != e.shard_v
        )

        boundary_in = (
            bridges
            | "BoundaryInPairs" >> beam.Map(lambda e: (e.shard_v, e.v))
            | "DistinctBoundaryIn" >> beam.Distinct()
            | "BoundaryInRows"
            >> beam.Map(lambda kv: BoundaryNode(shard_id=kv[0], node_id=kv[1]))
        )
        boundary_out = (
            bridges
            | "BoundaryOutPairs" >> beam.Map(lambda e: (e.shard_u, e.u))
            | "DistinctBoundaryOut" >> beam.Distinct()
            | "BoundaryOutRows"
            >> beam.Map(lambda kv: BoundaryNode(shard_id=kv[0], node_id=kv[1]))
        )

        _ = bridges | "WriteBridges" >> WriteParquet(
            file_path_prefix=f"{output_base}/bridges/part", schema=bridge_edge_schema
        )

        _ = internal_edges | "WriteShardEdges" >> WriteToParquetByDestination(
            base_path=output_base,
            schema=internal_edge_schema,
            destination_fn=lambda e: _destination_for_shard("edges", e.shard_u),
        )

        _ = node_out_dedup | "WriteShardNodes" >> WriteToParquetByDestination(
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
