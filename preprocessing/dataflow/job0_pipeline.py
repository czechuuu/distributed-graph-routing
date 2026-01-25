import logging
import os
import re
import tempfile
from typing import Iterable, NamedTuple, Optional, Tuple

import apache_beam as beam
import osmium
import pyarrow as pa
from apache_beam.io import fileio
from apache_beam.metrics import Metrics
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
TILE_OVERLAP_KM = 2.0
KM_PER_DEG_LAT = 111.32
TILE_OVERLAP_DEG = TILE_OVERLAP_KM / KM_PER_DEG_LAT
_TILE_FILENAME_RE = re.compile(r"tile_(.+)\.osm\.pbf$")


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


def _decode_coord(token: str) -> float:
    is_negative = token.startswith("m")
    if is_negative:
        token = token[1:]
    token = token.replace("_", ".")
    value = float(token)
    return -value if is_negative else value


def _parse_tile_bbox(path: str) -> Tuple[float, float, float, float]:
    filename = path.rsplit("/", 1)[-1]
    match = _TILE_FILENAME_RE.match(filename)
    if not match:
        raise ValueError(f"Unrecognized tile filename: {path}")
    coords_str = match.group(1)
    parts = re.findall(r"m?\d+(?:_\d+)?", coords_str)
    if len(parts) != 4:
        raise ValueError(f"Expected 4 coords in tile filename: {path}")
    min_lat, min_lon, max_lat, max_lon = (_decode_coord(part) for part in parts)
    return min_lon, min_lat, max_lon, max_lat


def _core_bbox_from_tile(path: str) -> Tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = _parse_tile_bbox(path)
    return (
        min_lon + TILE_OVERLAP_DEG,
        min_lat + TILE_OVERLAP_DEG,
        max_lon - TILE_OVERLAP_DEG,
        max_lat - TILE_OVERLAP_DEG,
    )


def _is_in_core(lon: float, lat: float, core_bbox: Tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = core_bbox
    return min_lon <= lon < max_lon and min_lat <= lat < max_lat


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
                file_path = getattr(readable_file.metadata, "path", "unknown")
                logging.warning("Skipping file %s: %s", file_path, e)
                return  # Skip this file, don't yield any nodes/edges
            
            for node in handler.nodes:
                yield beam.pvalue.TaggedOutput("nodes", node)
            for edge in handler.edges:
                yield beam.pvalue.TaggedOutput("edges", edge)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


class ParseAndEnrichTileDoFn(beam.DoFn):
    def process(self, readable_file: fileio.ReadableFile):
        tmp_path = None
        file_path = getattr(readable_file.metadata, "path", "unknown")
        try:
            core_bbox = _core_bbox_from_tile(file_path)
        except ValueError as exc:
            logging.error("Failed to parse tile bbox from %s: %s", file_path, exc)
            raise
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
                logging.warning("Skipping file %s: %s", file_path, e)
                return

            node_map: dict[int, tuple[float, float, int]] = {}
            for node in handler.nodes:
                shard_id = _compute_shard_id(node.x, node.y)
                node_map[node.id] = (node.x, node.y, shard_id)

            Metrics.counter("job0", "tile_nodes_total").inc(len(node_map))
            Metrics.distribution("job0", "tile_nodes_count").update(len(node_map))
            owned_nodes = 0
            for node_id, (x, y, shard_id) in node_map.items():
                if not _is_in_core(x, y, core_bbox):
                    continue
                owned_nodes += 1
                Metrics.counter("job0", "owned_nodes_emitted").inc()
                yield beam.pvalue.TaggedOutput(
                    "nodes", NodeOut(id=node_id, x=x, y=y, shard_id=shard_id)
                )
            Metrics.distribution("job0", "tile_owned_nodes").update(owned_nodes)

            missing_u = 0
            missing_v = 0
            missing_u_samples: list[int] = []
            missing_v_samples: list[int] = []
            owned_edges = 0

            for edge in handler.edges:
                Metrics.counter("job0", "tile_edges_total").inc()
                node_u = node_map.get(edge.u)
                node_v = node_map.get(edge.v)
                if node_u is None:
                    missing_u += 1
                    Metrics.counter("job0", "missing_u_nodes").inc()
                    Metrics.counter("job0", "missing_u_edges_dropped").inc()
                    if len(missing_u_samples) < 5:
                        missing_u_samples.append(edge.u)
                if node_v is None:
                    missing_v += 1
                    Metrics.counter("job0", "missing_v_nodes").inc()
                    Metrics.counter("job0", "missing_v_edges_dropped").inc()
                    if len(missing_v_samples) < 5:
                        missing_v_samples.append(edge.v)
                if node_u is None or node_v is None:
                    continue

                x_u, y_u, shard_u = node_u
                if not _is_in_core(x_u, y_u, core_bbox):
                    continue

                Metrics.counter("job0", "tile_edges_emitted").inc()
                x_v, y_v, shard_v = node_v
                owned_edges += 1
                Metrics.counter("job0", "owned_edges_emitted").inc()
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
                    x_u=x_u,
                    y_u=y_u,
                    x_v=x_v,
                    y_v=y_v,
                    shard_u=shard_u,
                    shard_v=shard_v,
                )

            Metrics.distribution("job0", "tile_owned_edges").update(owned_edges)
            if missing_u or missing_v:
                logging.warning(
                    "Missing nodes in tile %s: missing_u=%s missing_v=%s "
                    "sample_u=%s sample_v=%s",
                    file_path,
                    missing_u,
                    missing_v,
                    missing_u_samples,
                    missing_v_samples,
                )
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
            Metrics.counter("job0", "missing_u_nodes").inc()
            logging.warning(
                "Node %s referenced as edge source but not found in nodes input.",
                node_id,
            )
            Metrics.counter("job0", "missing_u_edges_dropped").inc()
            for _ in edges_iter:
                Metrics.counter("job0", "missing_u_edges_dropped").inc()
            return
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
            Metrics.counter("job0", "missing_v_nodes").inc()
            logging.warning(
                "Node %s referenced as edge target but not found in nodes input.",
                node_id,
            )
            Metrics.counter("job0", "missing_v_edges_dropped").inc()
            for _ in edges_iter:
                Metrics.counter("job0", "missing_v_edges_dropped").inc()
            return
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
            | "ParseAndEnrichTiles" >> beam.ParDo(ParseAndEnrichTileDoFn()).with_outputs("nodes")
        )
        edges_with_shards = parsed[None]
        node_out = parsed.nodes

        edge_slim = edges_with_shards | "ComputeWeights" >> beam.ParDo(
            ComputeWeightAndNodes(weight_mode)
        )

        internal_edges = edge_slim | "FilterInternalEdges" >> beam.Filter(
            lambda e: e.shard_u == e.shard_v
        )
        bridges = edge_slim | "FilterBridgeEdges" >> beam.Filter(
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

        _ = node_out | "WriteShardNodes" >> WriteToParquetByDestination(
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
