from __future__ import annotations

import socket
import threading
import time
from typing import Dict, List, Sequence

import grpc

from .hrw import pick_node
import shard_worker_pb2_grpc


class WorkerPool:
    def __init__(self, host: str, port: int, refresh_seconds: int):
        self._host = host
        self._port = port
        self._refresh_seconds = refresh_seconds
        self._lock = threading.Lock()
        self._last_refresh = 0.0
        self._endpoints: List[str] = []
        self._channels: Dict[str, grpc.Channel] = {}

    def _resolve_endpoints(self) -> List[str]:
        infos = socket.getaddrinfo(self._host, self._port, proto=socket.IPPROTO_TCP)
        ips = sorted({info[4][0] for info in infos})
        return [f"{ip}:{self._port}" for ip in ips]

    def _refresh(self) -> None:
        now = time.time()
        if now - self._last_refresh < self._refresh_seconds:
            return
        endpoints = self._resolve_endpoints()
        self._endpoints = endpoints
        for endpoint in list(self._channels.keys()):
            if endpoint not in endpoints:
                self._channels.pop(endpoint, None)
        self._last_refresh = now

    def _ensure_refreshed(self) -> None:
        with self._lock:
            self._refresh()

    def pick_stub(self, shard_id: int) -> shard_worker_pb2_grpc.ShardWorkerStub:
        self._ensure_refreshed()
        if not self._endpoints:
            raise RuntimeError("no shard-worker endpoints available")
        endpoint = pick_node(str(shard_id), self._endpoints)
        channel = self._channels.get(endpoint)
        if channel is None:
            channel = grpc.insecure_channel(endpoint)
            self._channels[endpoint] = channel
        return shard_worker_pb2_grpc.ShardWorkerStub(channel)
