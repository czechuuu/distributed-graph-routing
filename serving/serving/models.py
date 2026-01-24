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


class Segment(BaseModel):
    start: NodeRef
    end: NodeRef
    polyline: List[Coordinate]
    expandable: bool


class SegmentEndpoints(BaseModel):
    start: NodeRef
    end: NodeRef


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
    segments: List[SegmentEndpoints]


class RouteExpandResponse(BaseModel):
    segments: List[Segment]
    errors: List[dict]
