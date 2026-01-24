from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .dijkstra import Adjacency
from .storage_types import gcs_storage_pb2


@dataclass(frozen=True)
class ShardData:
    shard_id: int
    adjacency: Adjacency
    reverse_adjacency: Adjacency
    node_locations: Dict[int, Tuple[float, float]]
    boundary_in: set[int]
    boundary_out: set[int]

    def nearest_node(self, lat: float, lng: float) -> Optional[int]:
        best_node = None
        best_dist = None
        for node_id, (node_lat, node_lng) in self.node_locations.items():
            dx = node_lat - lat
            dy = node_lng - lng
            dist = dx * dx + dy * dy
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_node = node_id
        return best_node


def parse_shard(shard_id: int, payload: bytes) -> ShardData:
    shard_pb = gcs_storage_pb2.ShardGraph()
    shard_pb.ParseFromString(payload)

    adjacency: Adjacency = {}
    reverse: Adjacency = {}
    for edge in shard_pb.edges:
        adjacency.setdefault(edge.from_node_id, []).append((edge.to_node_id, edge.weight))
        reverse.setdefault(edge.to_node_id, []).append((edge.from_node_id, edge.weight))

    node_locations: Dict[int, Tuple[float, float]] = {}
    for loc in shard_pb.locations:
        node_locations[loc.node_id] = (loc.y, loc.x)

    boundary_in = set(int(node_id) for node_id in shard_pb.boundary_in_node_ids)
    boundary_out = set(int(node_id) for node_id in shard_pb.boundary_out_node_ids)

    return ShardData(
        shard_id=shard_id,
        adjacency=adjacency,
        reverse_adjacency=reverse,
        node_locations=node_locations,
        boundary_in=boundary_in,
        boundary_out=boundary_out,
    )


class ShardCache:
    def __init__(self, max_size: int):
        self._max_size = max_size
        self._cache: OrderedDict[int, ShardData] = OrderedDict()

    def get(self, shard_id: int) -> Optional[ShardData]:
        shard = self._cache.get(shard_id)
        if shard is None:
            return None
        self._cache.move_to_end(shard_id)
        return shard

    def put(self, shard_id: int, shard: ShardData) -> None:
        self._cache[shard_id] = shard
        self._cache.move_to_end(shard_id)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
