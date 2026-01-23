# MVP Client ↔ Orchestrator API (Endpoint-Keyed Segments + Lazy Expansion)

This document specifies a **minimal working** HTTP/JSON API between the frontend client and the backend **Orchestrator**.

## Scope and non-goals

- **Scope**:
  - Client requests a route between two geographic points.
  - Orchestrator returns a **compressed route** as a list of **segments** (each segment has endpoints and can be expanded).
  - Client requests **batch expansion** of one or more segments.
- **Non-goals**:
  - Client does **not** handle node IDs or shards.
  - No “preview geometry”, no polyline simplification parameters, no partial streaming.
  - No graph versioning (assume the graph is immutable).

## High-level contract

- **Shards are invisible to the client**. All requests go to the Orchestrator.
- **Segments are identified only by their endpoints**: `(u, v)`.
- The client only **draws what the backend returns**.
- Clients MUST treat returned endpoints as opaque tokens and MUST NOT recompute/round them.
- **Segment expansion is deterministic** for a given `(u, v)` pair.

## Data types

### Coordinate

```json
{ "lat": 52.2297, "lng": 21.0122 }
```

- `lat`: number, degrees (float64)
- `lng`: number, degrees (float64)

#### Coordinate identity / serialization requirements (MVP)

This API uses JSON numbers for coordinates. Segment identity depends on exact float64 equality.

- Clients MUST echo back the exact `u`/`v` coordinate values they received from `/v1/route` when calling `/v1/route/expand`.
- Clients MUST NOT format/round coordinates to a fixed number of decimal places.
- If a client uses a non-standard JSON serializer, it MUST serialize float64 with enough precision to round-trip (rule of thumb: at least 17 significant digits).
- Backends SHOULD compare endpoint coordinates by float64 value (ideally by IEEE-754 bit pattern), not by the textual JSON representation.

### SegmentRef

The minimal reference used to identify a segment for expansion. Directional: `(u, v)` is distinct from `(v, u)`.

```json
{
  "u": { "lat": 52.22971, "lng": 21.01218 },
  "v": { "lat": 52.22990, "lng": 21.01280 }
}
```

### Segment

```json
{
  "u": { "lat": 52.22971, "lng": 21.01218 },
  "v": { "lat": 52.22990, "lng": 21.01280 },
  "expandable": true
}
```

- `u`, `v`: `Coordinate` endpoints of this segment (also the segment identifier)
- `expandable`: boolean

### ExpandedSegment

```json
{
  "u": { "lat": 52.22971, "lng": 21.01218 },
  "v": { "lat": 52.22990, "lng": 21.01280 },
  "polyline": [
    { "lat": 52.22971, "lng": 21.01218 },
    { "lat": 52.22975, "lng": 21.01230 },
    { "lat": 52.22990, "lng": 21.01280 }
  ]
}
```

- `u`, `v`: the `SegmentRef` endpoints being expanded
- `polyline`: array of `Coordinate`
  - The first point SHOULD equal the segment’s `u` and the last point SHOULD equal `v`.
  - Intermediate points represent the fully expanded path within that segment.

## Endpoint: Compute route

### `POST /v1/route`

Compute a route between two geographic points and return a compressed route as segments.

#### Request

```json
{
  "start": { "lat": 52.2297, "lng": 21.0122 },
  "end": { "lat": 52.2400, "lng": 21.0300 }
}
```

#### Response (200 OK)

```json
{
  "path_found": true,
  "segments": [
    {
      "u": { "lat": 52.22971, "lng": 21.01218 },
      "v": { "lat": 52.22990, "lng": 21.01280 },
      "expandable": true
    }
  ],
  "summary": {
    "segments_count": 1,
    "distance_m": 5234.1
  }
}
```

#### Response (200 OK, no route)

```json
{
  "path_found": false,
  "segments": [],
  "summary": { "segments_count": 0, "distance_m": 0 }
}
```

#### Response (422 Unprocessable Entity, unroutable input)

```json
{
  "error": { "code": "no_nearby_nodes", "message": "No routable graph data near start or end point." }
}
```

#### Semantics

- Orchestrator MUST return segment endpoints (`u`, `v`) as canonical stored float64 values.
- Clients MUST use the returned `(u, v)` endpoints as the only identifiers when requesting expansion.

## Endpoint: Expand segments (batch)

### `POST /v1/route/expand`

Expand one or more segments by `(u, v)` endpoints. Client always uses the batch form (batch size may be 1).

#### Request

```json
{
  "segments": [
    {
      "u": { "lat": 52.22971, "lng": 21.01218 },
      "v": { "lat": 52.22990, "lng": 21.01280 }
    },
    {
      "u": { "lat": 52.22990, "lng": 21.01280 },
      "v": { "lat": 52.23010, "lng": 21.01310 }
    }
  ]
}
```

#### Response (200 OK)

```json
{
  "expanded": [
    {
      "u": { "lat": 52.22971, "lng": 21.01218 },
      "v": { "lat": 52.22990, "lng": 21.01280 },
      "polyline": [
        { "lat": 52.22971, "lng": 21.01218 },
        { "lat": 52.22975, "lng": 21.01230 },
        { "lat": 52.22990, "lng": 21.01280 }
      ]
    }
  ],
  "errors": []
}
```

#### Error responses

- **400 Bad Request** (e.g., empty `segments`):

```json
{
  "error": { "code": "invalid_request", "message": "segments must be a non-empty array." }
}
```

#### Semantics

- Orchestrator MUST treat `(u, v)` expansion as deterministic:
  - It MAY return cached results or recompute, but the resulting polyline MUST be stable for a given `(u, v)`.
- Orchestrator MAY return expanded segments in any order; clients MUST match by `(u, v)` endpoints.

## Determinism requirements (MVP)

To make results stable even if recomputed, the system SHOULD define deterministic tie-breaking:

- Neighbor iteration order is stable (e.g., edges sorted by `(weight, to_node_id)`).
- Priority queue tie-break includes a stable key (e.g., `(distance, node_id)`).

## Caching (MVP)

- Caching is backend-internal and best-effort.
- Backends MAY cache expansions keyed by `(u, v) -> polyline` and evict entries at any time.

