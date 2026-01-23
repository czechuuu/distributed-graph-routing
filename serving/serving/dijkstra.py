from __future__ import annotations

import heapq
import math
from typing import Dict, Iterable, List, Optional, Set, Tuple

Adjacency = Dict[int, List[Tuple[int, float]]]


def dijkstra_targets(adjacency: Adjacency, source: int, targets: Set[int]) -> Dict[int, float]:
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


def dijkstra_path(adjacency: Adjacency, source: int, target: int) -> Tuple[Optional[List[int]], Optional[float]]:
    distances: Dict[int, float] = {source: 0.0}
    prev: Dict[int, int] = {}
    heap: List[Tuple[float, int]] = [(0.0, source)]

    while heap:
        dist_u, u = heapq.heappop(heap)
        if dist_u != distances.get(u):
            continue
        if u == target:
            break
        for v, weight in adjacency.get(u, []):
            nd = dist_u + weight
            if nd < distances.get(v, math.inf):
                distances[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    if target not in distances:
        return None, None

    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    path.reverse()
    return path, distances[target]


def multi_source_dijkstra(
    adjacency: Adjacency, sources: Dict[int, float]
) -> Tuple[Dict[int, float], Dict[int, int]]:
    distances: Dict[int, float] = dict(sources)
    prev: Dict[int, int] = {}
    heap: List[Tuple[float, int]] = [(dist, node) for node, dist in sources.items()]
    heapq.heapify(heap)

    while heap:
        dist_u, u = heapq.heappop(heap)
        if dist_u != distances.get(u):
            continue
        for v, weight in adjacency.get(u, []):
            nd = dist_u + weight
            if nd < distances.get(v, math.inf):
                distances[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    return distances, prev


def reconstruct_path(prev: Dict[int, int], target: int) -> List[int]:
    path = [target]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    return path
