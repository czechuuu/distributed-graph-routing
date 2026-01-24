from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .dijkstra import Adjacency, reverse_adjacency
from shared.protos import gcs_storage_pb2



@dataclass(frozen=True)
class OverlayGraphData:
    adjacency: Adjacency
    rev_adjacency: Adjacency
    boundary_locations: Dict[int, Tuple[float, float]]


def parse_overlay(payload: bytes) -> OverlayGraphData:
    overlay_pb = gcs_storage_pb2.OverlayGraph()
    overlay_pb.ParseFromString(payload)

    adjacency: Adjacency = {}
    for edge in list(overlay_pb.bridges) + list(overlay_pb.shortcuts):
        adjacency.setdefault(edge.from_node_id, []).append((edge.to_node_id, edge.weight))

    boundary_locations: Dict[int, Tuple[float, float]] = {}
    for loc in overlay_pb.boundary_locations:
        boundary_locations[loc.node_id] = (loc.y, loc.x)

    return OverlayGraphData(
        adjacency=adjacency,
        rev_adjacency=reverse_adjacency(adjacency),
        boundary_locations=boundary_locations,
    )

