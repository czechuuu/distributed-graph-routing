# MVP Client ↔ Routing API

This document specifies a **minimal working** HTTP/JSON API between the frontend client and the backend **Routing API**.

## Scope and non-goals

- **Scope**:
  - Client requests a route between two geographic points.
  - Routing API returns a **compressed route** as a list of **segments** (each segment has endpoints and can be expanded).
  - Client requests **batch expansion** of one or more segments.
- **Non-goals**:
  - Client does **not interpret** node IDs or shards (IDs are opaque tokens that must be echoed back).
  - No “preview geometry”, no polyline simplification parameters, no partial streaming.
  - No graph versioning (assume the graph is immutable).

## High-level contract

- **Shards are invisible to the client**. All requests go to the Routing API.
- **Segments are identified by their endpoint node IDs**: `(u.node_id, v.node_id)` (directional).
- The client only **draws what the backend returns**.
- Clients MUST treat returned node IDs as opaque tokens and MUST NOT parse/rewrite them.
- **Segment expansion is deterministic** for a given `(u.node_id, v.node_id)` pair.

## Data types

### NodeId

`NodeId` is a 64-bit node identifier serialized as a JSON string (decimal) to avoid precision loss in JavaScript.

```json
"8963866048"
```

### NodeRef

Node reference used throughout the API. It is both:
- a stable identifier (`node_id`) and
- a display-friendly coordinate (`lat`, `lng`)

```json
{ "node_id": "8963866048", "lat": 52.2297, "lng": 21.0122 }
```

- `node_id`: `NodeId` (string)
- `lat`: number, degrees (float64)
- `lng`: number, degrees (float64)

### Coordinate

Used only for inputs that are not yet snapped to a graph node.

```json
{ "lat": 52.2297, "lng": 21.0122 }
```

- `lat`: number, degrees (float64)
- `lng`: number, degrees (float64)

### SegmentRef

The minimal reference used to identify a segment for expansion.

Directional: `(u.node_id, v.node_id)` is distinct from `(v.node_id, u.node_id)`.

```json
{
  "u": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
  "v": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 }
}
```

### Segment

```json
{
  "u": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
  "v": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
  "expandable": true
}
```

- `u`, `v`: `NodeRef` endpoints of this segment (also the segment identifier; also used for drawing and shard routing)
- `expandable`: boolean

### ExpandedSegment

```json
{
  "u": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
  "v": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
  "polyline": [
    { "lat": 52.22971, "lng": 21.01218 },
    { "lat": 52.22975, "lng": 21.01230 },
    { "lat": 52.22990, "lng": 21.01280 }
  ]
}
```

- `u`, `v`: the `NodeRef` endpoints being expanded
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
      "u": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
      "v": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
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

- Routing API MUST return `u.node_id` and `v.node_id` for every segment.
- Clients MUST use the returned `(u.node_id, v.node_id)` pair as the identifier when requesting expansion.
- The Routing API SHOULD return `u.lat/lng` and `v.lat/lng` consistent with the returned node IDs.

## Endpoint: Expand segments (batch)

### `POST /v1/route/expand`

Expand one or more segments by `(u.node_id, v.node_id)` endpoints. Client always uses the batch form (batch size may be 1).

#### Request

```json
{
  "segments": [
    {
      "u": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
      "v": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 }
    },
    {
      "u": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
      "v": { "node_id": "8963867000", "lat": 52.23010, "lng": 21.01310 }
    }
  ]
}
```

#### Response (200 OK)

```json
{
  "expanded": [
    {
      "u": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
      "v": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
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
