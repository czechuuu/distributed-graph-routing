from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    lat: float
    lng: float


class NodeRef(BaseModel):
    node_id: str = Field(..., description="NodeId serialized as string")
    lat: float
    lng: float


class SegmentRef(BaseModel):
    u: NodeRef
    v: NodeRef


class Segment(BaseModel):
    u: NodeRef
    v: NodeRef
    expandable: bool


class ExpandedSegment(BaseModel):
    u: NodeRef
    v: NodeRef
    polyline: List[Coordinate]


class RouteRequest(BaseModel):
    start: Coordinate
    end: Coordinate


class RouteSummary(BaseModel):
    segments_count: int
    distance_m: float


class RouteResponse(BaseModel):
    path_found: bool
    segments: List[Segment]
    summary: RouteSummary


class RouteExpandRequest(BaseModel):
    segments: List[SegmentRef]


class RouteExpandResponse(BaseModel):
    expanded: List[ExpandedSegment]
    errors: List[dict]
