from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Set, Tuple

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


def reverse_adjacency(adjacency: Adjacency) -> Adjacency:
    """Build the reverse graph where all edges point backward."""
    rev: Adjacency = {}
    for u, edges in adjacency.items():
        for v, w in edges:
            rev.setdefault(v, []).append((u, w))
    return rev


def bidirectional_multi_source_dijkstra(
    adjacency: Adjacency,
    rev_adjacency: Adjacency,
    sources: Dict[int, float],
    targets: Dict[int, float],
) -> Tuple[Optional[int], float, Dict[int, int], Dict[int, int]]:
    """
    Bidirectional multi-source Dijkstra from multiple sources to multiple targets.

    Args:
        adjacency: Forward graph (node -> [(neighbor, weight), ...])
        rev_adjacency: Reverse graph for backward search
        sources: Dict of source_node -> initial_distance (out-boundaries)
        targets: Dict of target_node -> initial_distance (in-boundaries)

    Returns:
        (meeting_node, best_cost, prev_forward, prev_backward)
        meeting_node is None if no path exists.
    """
    if not sources or not targets:
        return None, math.inf, {}, {}

    # Forward search state
    dist_fwd: Dict[int, float] = dict(sources)
    prev_fwd: Dict[int, int] = {}
    heap_fwd: List[Tuple[float, int]] = [(d, n) for n, d in sources.items()]
    heapq.heapify(heap_fwd)
    settled_fwd: Set[int] = set()

    # Backward search state
    dist_bwd: Dict[int, float] = dict(targets)
    prev_bwd: Dict[int, int] = {}
    heap_bwd: List[Tuple[float, int]] = [(d, n) for n, d in targets.items()]
    heapq.heapify(heap_bwd)
    settled_bwd: Set[int] = set()

    best_cost = math.inf
    meeting: Optional[int] = None

    while heap_fwd or heap_bwd:
        # Get current top values for stopping criterion
        top_fwd = heap_fwd[0][0] if heap_fwd else math.inf
        top_bwd = heap_bwd[0][0] if heap_bwd else math.inf

        # Early termination: no unsettled node can improve the path
        if top_fwd + top_bwd >= best_cost:
            break

        # Alternate: expand from whichever side has the smaller top
        if top_fwd <= top_bwd:
            # Forward step
            d_u, u = heapq.heappop(heap_fwd)
            if d_u != dist_fwd.get(u):
                continue  # Stale entry
            settled_fwd.add(u)

            # Check if this node is settled in backward search
            if u in settled_bwd:
                cost = d_u + dist_bwd[u]
                if cost < best_cost:
                    best_cost = cost
                    meeting = u

            # Relax forward edges
            for v, w in adjacency.get(u, []):
                nd = d_u + w
                if nd < dist_fwd.get(v, math.inf):
                    dist_fwd[v] = nd
                    prev_fwd[v] = u
                    heapq.heappush(heap_fwd, (nd, v))
        else:
            # Backward step
            d_u, u = heapq.heappop(heap_bwd)
            if d_u != dist_bwd.get(u):
                continue  # Stale entry
            settled_bwd.add(u)

            # Check if this node is settled in forward search
            if u in settled_fwd:
                cost = dist_fwd[u] + d_u
                if cost < best_cost:
                    best_cost = cost
                    meeting = u

            # Relax backward edges (using reverse adjacency)
            for v, w in rev_adjacency.get(u, []):
                nd = d_u + w
                if nd < dist_bwd.get(v, math.inf):
                    dist_bwd[v] = nd
                    prev_bwd[v] = u
                    heapq.heappush(heap_bwd, (nd, v))

    return meeting, best_cost, prev_fwd, prev_bwd


def reconstruct_bidirectional_path(
    meeting: int,
    prev_forward: Dict[int, int],
    prev_backward: Dict[int, int],
) -> List[int]:
    """
    Reconstruct path from bidirectional search results.

    Returns the path as a list of node IDs from source to target.
    """
    # Forward path: from source to meeting
    fwd_path = [meeting]
    while fwd_path[-1] in prev_forward:
        fwd_path.append(prev_forward[fwd_path[-1]])
    fwd_path.reverse()

    # Backward path: from meeting to target
    bwd_path = []
    node = meeting
    while node in prev_backward:
        node = prev_backward[node]
        bwd_path.append(node)

    return fwd_path + bwd_path
