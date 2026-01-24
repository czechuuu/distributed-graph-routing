from __future__ import annotations

import threading
from concurrent import futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List

import grpc

from .config import load_shard_worker_config
from .dijkstra import dijkstra_path, dijkstra_targets
from .gcs import download_shard
from .shard_cache import ShardCache, ShardData, parse_shard
from .storage_types import gcs_storage_pb2
import shard_worker_pb2
import shard_worker_pb2_grpc


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


class ShardWorkerService(shard_worker_pb2_grpc.ShardWorkerServicer):
    def __init__(self, bucket: str, prefix: str, cache: ShardCache):
        self._bucket = bucket
        self._prefix = prefix
        self._cache = cache

    def _load_shard(self, shard_id: int) -> ShardData | None:
        shard = self._cache.get(shard_id)
        if shard is not None:
            return shard
        if not self._bucket:
            return None
        payload = download_shard(self._bucket, self._prefix, shard_id)
        shard = parse_shard(shard_id, payload)
        self._cache.put(shard_id, shard)
        return shard

    def SnapAndBoundaryDists(self, request, context):
        shard = self._load_shard(int(request.shard_id))
        if shard is None:
            return shard_worker_pb2.SnapAndBoundaryDistsResponse(
                ok=False, error="shard_not_loaded"
            )

        node_id = shard.nearest_node(request.lat, request.lng)
        if node_id is None:
            return shard_worker_pb2.SnapAndBoundaryDistsResponse(
                ok=False, error="no_nearby_nodes"
            )

        snapped_lat, snapped_lng = shard.node_locations[node_id]
        snapped = shard_worker_pb2.NodeRef(
            node_id=node_id, lat=snapped_lat, lng=snapped_lng
        )

        if request.mode == shard_worker_pb2.BOUNDARY_IN:
            targets = set(shard.boundary_in)
            adjacency = shard.reverse_adjacency
        else:
            targets = set(shard.boundary_out)
            adjacency = shard.adjacency

        dists = dijkstra_targets(adjacency, node_id, targets)
        dists_int = {key: int(round(value)) for key, value in dists.items()}

        return shard_worker_pb2.SnapAndBoundaryDistsResponse(
            ok=True,
            snapped=snapped,
            boundary_node_ids=list(targets),
            dists=dists_int,
        )

    def ExpandPath(self, request, context):
        shard = self._load_shard(int(request.shard_id))
        if shard is None:
            return shard_worker_pb2.ExpandPathResponse(
                ok=False, error="shard_not_loaded"
            )

        path, total_weight = dijkstra_path(
            shard.adjacency, int(request.u_node_id), int(request.v_node_id)
        )
        if path is None or total_weight is None:
            return shard_worker_pb2.ExpandPathResponse(ok=False, error="path_not_found")

        polyline = []
        for node_id in path:
            lat_lng = shard.node_locations.get(node_id)
            if lat_lng is None:
                continue
            lat, lng = lat_lng
            polyline.append(shard_worker_pb2.Coordinate(lat=lat, lng=lng))

        return shard_worker_pb2.ExpandPathResponse(
            ok=True, polyline=polyline, total_weight=int(round(total_weight))
        )

    def Health(self, request, context):
        return shard_worker_pb2.HealthResponse(ok=True)


def _serve_health(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    server.serve_forever()


def serve() -> None:
    config = load_shard_worker_config()
    cache = ShardCache(max_size=config.max_cached_shards)

    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    shard_worker_pb2_grpc.add_ShardWorkerServicer_to_server(
        ShardWorkerService(config.gcs.bucket, config.gcs.prefix, cache),
        grpc_server,
    )
    grpc_server.add_insecure_port(f"{config.host}:{config.port}")

    health_thread = threading.Thread(
        target=_serve_health, args=(config.health_port,), daemon=True
    )
    health_thread.start()

    grpc_server.start()
    grpc_server.wait_for_termination()


if __name__ == "__main__":
    serve()
