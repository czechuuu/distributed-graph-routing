from dataclasses import dataclass
from typing import Iterable, Optional

_ONEWAY_YES = {"yes", "true", "1"}


@dataclass(frozen=True)
class EdgeTags:
    highway: Optional[str]
    maxspeed: Optional[str]
    maxspeed_forward: Optional[str]
    maxspeed_backward: Optional[str]
    surface: Optional[str]
    tracktype: Optional[str]
    service: Optional[str]


@dataclass(frozen=True)
class DirectedEdgeCandidate:
    u: int
    v: int
    direction: int
    tags: EdgeTags


def _oneway_direction(tags: dict) -> Optional[int]:
    oneway = tags.get("oneway")
    if not oneway:
        return None
    value = str(oneway).lower()
    if value in _ONEWAY_YES:
        return 1
    if value == "-1":
        return -1
    return None


def extract_edge_tags(tags: dict) -> EdgeTags:
    return EdgeTags(
        highway=tags.get("highway"),
        maxspeed=tags.get("maxspeed"),
        maxspeed_forward=tags.get("maxspeed:forward"),
        maxspeed_backward=tags.get("maxspeed:backward"),
        surface=tags.get("surface"),
        tracktype=tags.get("tracktype"),
        service=tags.get("service"),
    )


def expand_way_nodes(node_refs: Iterable[int], tags: dict) -> Iterable[DirectedEdgeCandidate]:
    refs = list(node_refs)
    if len(refs) < 2:
        return []
    direction = _oneway_direction(tags)
    edge_tags = extract_edge_tags(tags)
    edges = []
    if direction == -1:
        for i in range(len(refs) - 1):
            edges.append(
                DirectedEdgeCandidate(
                    u=refs[i + 1], v=refs[i], direction=-1, tags=edge_tags
                )
            )
        return edges
    for i in range(len(refs) - 1):
        edges.append(DirectedEdgeCandidate(u=refs[i], v=refs[i + 1], direction=1, tags=edge_tags))
        if direction is None:
            edges.append(
                DirectedEdgeCandidate(
                    u=refs[i + 1], v=refs[i], direction=-1, tags=edge_tags
                )
            )
    return edges
