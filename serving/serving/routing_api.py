from __future__ import annotations

import math
from typing import Dict, List

from fastapi import FastAPI, HTTPException

from .config import load_routing_api_config
from .dijkstra import multi_source_dijkstra, reconstruct_path
from .gcs import download_overlay
from .models import (
    Coordinate,
    RouteExpandRequest,
    RouteExpandResponse,
    RouteRequest,
    RouteResponse,
    RouteSummary,
    Segment,
)
from .overlay import OverlayGraphData, parse_overlay
import shard_worker_pb2
from .s2 import shard_id_for_lat_lng
from .worker_pool import WorkerPool


app = FastAPI()

overlay_graph: OverlayGraphData | None = None
worker_pool: WorkerPool | None = None


def _node_ref(node_id: int, lat: float, lng: float) -> Dict[str, object]:
    return {"node_id": str(node_id), "lat": lat, "lng": lng}


def _segment(start: Dict[str, object], end: Dict[str, object], expandable: bool) -> Segment:
    return Segment(
        start=start,
        end=end,
        polyline=[Coordinate(lat=start["lat"], lng=start["lng"]), Coordinate(lat=end["lat"], lng=end["lng"])],
        expandable=expandable,
    )


@app.on_event("startup")
def _startup() -> None:
    config = load_routing_api_config()
    if not config.gcs.bucket:
        raise RuntimeError("GCS_BUCKET must be set")
    payload = download_overlay(config.gcs.bucket, config.gcs.prefix)
    global overlay_graph, worker_pool
    overlay_graph = parse_overlay(payload)
    worker_pool = WorkerPool(
        config.worker_service_host,
        config.worker_service_port,
        config.worker_refresh_seconds,
    )


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


def _fetch_worker_dists(shard_id: int, lat: float, lng: float, mode: int):
    if worker_pool is None:
        raise RuntimeError("worker pool not initialized")
    stub = worker_pool.pick_stub(shard_id)
    request = shard_worker_pb2.SnapAndBoundaryDistsRequest(
        shard_id=shard_id, lat=lat, lng=lng, mode=mode
    )
    return stub.SnapAndBoundaryDists(request, timeout=10.0)


def _expand_path(shard_id: int, u_node_id: int, v_node_id: int):
    if worker_pool is None:
        raise RuntimeError("worker pool not initialized")
    stub = worker_pool.pick_stub(shard_id)
    request = shard_worker_pb2.ExpandPathRequest(
        shard_id=shard_id, u_node_id=u_node_id, v_node_id=v_node_id
    )
    return stub.ExpandPath(request, timeout=20.0)


def _route_same_shard(
    shard_id: int, start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> RouteResponse:
    """Find a route when both start and end are within the same shard."""
    try:
        start_resp = _fetch_worker_dists(
            shard_id, start_lat, start_lng, shard_worker_pb2.BOUNDARY_OUT
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not start_resp.ok:
        raise HTTPException(status_code=422, detail=start_resp.error)

    try:
        end_resp = _fetch_worker_dists(
            shard_id, end_lat, end_lng, shard_worker_pb2.BOUNDARY_IN
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not end_resp.ok:
        raise HTTPException(status_code=422, detail=end_resp.error)

    try:
        expand = _expand_path(
            shard_id, start_resp.snapped.node_id, end_resp.snapped.node_id
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not expand.ok:
        return RouteResponse(
            path_found=False, segments=[], summary=RouteSummary(segments_count=0, distance_m=0)
        )

    start_node = _node_ref(start_resp.snapped.node_id, start_resp.snapped.lat, start_resp.snapped.lng)
    end_node = _node_ref(end_resp.snapped.node_id, end_resp.snapped.lat, end_resp.snapped.lng)
    return RouteResponse(
        path_found=True,
        segments=[_segment(start_node, end_node, expandable=True)],
        summary=RouteSummary(segments_count=1, distance_m=float(expand.total_weight)),
    )


def _route_different_shards(
    start_shard: int,
    end_shard: int,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> RouteResponse:
    """Find a route when start and end are in different shards, using the overlay graph."""
    if overlay_graph is None:
        raise HTTPException(status_code=500, detail="overlay_graph_not_loaded")

    try:
        start_resp = _fetch_worker_dists(
            start_shard, start_lat, start_lng, shard_worker_pb2.BOUNDARY_OUT
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not start_resp.ok:
        raise HTTPException(status_code=422, detail=start_resp.error)

    try:
        end_resp = _fetch_worker_dists(
            end_shard, end_lat, end_lng, shard_worker_pb2.BOUNDARY_IN
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not end_resp.ok:
        raise HTTPException(status_code=422, detail=end_resp.error)

    dist_start_to_out = {int(k): float(v) for k, v in start_resp.dists.items()}
    dist_in_to_end = {int(k): float(v) for k, v in end_resp.dists.items()}

    distances, prev = multi_source_dijkstra(overlay_graph.adjacency, dist_start_to_out)
    best_boundary = None
    best_cost = math.inf
    for node_id in end_resp.boundary_node_ids:
        node_id = int(node_id)
        cost = distances.get(node_id, math.inf) + dist_in_to_end.get(node_id, math.inf)
        if cost < best_cost:
            best_cost = cost
            best_boundary = node_id

    if best_boundary is None or best_cost == math.inf:
        return RouteResponse(
            path_found=False,
            segments=[],
            summary=RouteSummary(segments_count=0, distance_m=0),
        )

    overlay_path = reconstruct_path(prev, best_boundary)
    nodes: List[Dict[str, object]] = []
    start_node = _node_ref(start_resp.snapped.node_id, start_resp.snapped.lat, start_resp.snapped.lng)
    nodes.append(start_node)

    for node_id in overlay_path:
        loc = overlay_graph.boundary_locations.get(node_id)
        if loc is None:
            continue
        lat, lng = loc
        nodes.append(_node_ref(node_id, lat, lng))

    end_node = _node_ref(end_resp.snapped.node_id, end_resp.snapped.lat, end_resp.snapped.lng)
    nodes.append(end_node)

    segments: List[Segment] = []
    for i in range(len(nodes) - 1):
        seg_start = nodes[i]
        seg_end = nodes[i + 1]
        same_shard = shard_id_for_lat_lng(seg_start["lat"], seg_start["lng"]) == shard_id_for_lat_lng(
            seg_end["lat"], seg_end["lng"]
        )
        segments.append(_segment(seg_start, seg_end, expandable=same_shard))

    return RouteResponse(
        path_found=True,
        segments=segments,
        summary=RouteSummary(segments_count=len(segments), distance_m=float(best_cost)),
    )


@app.post("/v1/route", response_model=RouteResponse)
def route(request: RouteRequest) -> RouteResponse:
    if overlay_graph is None:
        raise HTTPException(status_code=500, detail="overlay_graph_not_loaded")

    start_shard = shard_id_for_lat_lng(request.start.lat, request.start.lng)
    end_shard = shard_id_for_lat_lng(request.end.lat, request.end.lng)

    if start_shard == end_shard:
        return _route_same_shard(
            start_shard,
            request.start.lat,
            request.start.lng,
            request.end.lat,
            request.end.lng,
        )

    return _route_different_shards(
        start_shard,
        end_shard,
        request.start.lat,
        request.start.lng,
        request.end.lat,
        request.end.lng,
    )


@app.post("/v1/route/expand", response_model=RouteExpandResponse)
def route_expand(request: RouteExpandRequest) -> RouteExpandResponse:
    if not request.segments:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": "segments must be a non-empty array."},
        )
    segments: List[Segment] = []
    errors: List[dict] = []

    for idx, segment in enumerate(request.segments):
        start = segment.start
        end = segment.end
        shard_start = shard_id_for_lat_lng(start.lat, start.lng)
        shard_end = shard_id_for_lat_lng(end.lat, end.lng)
        if shard_start != shard_end:
            segments.append(
                Segment(
                    start=start,
                    end=end,
                    polyline=[Coordinate(lat=start.lat, lng=start.lng), Coordinate(lat=end.lat, lng=end.lng)],
                    expandable=False,
                )
            )
            continue

        try:
            response = _expand_path(shard_start, int(start.node_id), int(end.node_id))
        except Exception as exc:
            errors.append({"index": idx, "error": str(exc)})
            continue
        if not response.ok:
            errors.append({"index": idx, "error": response.error})
            continue

        polyline = [Coordinate(lat=pt.lat, lng=pt.lng) for pt in response.polyline]
        segments.append(
            Segment(start=start, end=end, polyline=polyline, expandable=False)
        )

    return RouteExpandResponse(segments=segments, errors=errors)


def main() -> None:
    import uvicorn

    config = load_routing_api_config()
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
