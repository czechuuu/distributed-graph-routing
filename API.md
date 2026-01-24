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
- **Segments are identified by their endpoint node IDs**: `(start.node_id, end.node_id)` (directional).
- The client only **draws what the backend returns**.
- Clients MUST treat returned node IDs as opaque tokens and MUST NOT parse/rewrite them.
- **Segment expansion is deterministic** for a given `(start.node_id, end.node_id)` pair.

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

### Segment

```json
{
  "start": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
  "end": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
  "polyline": [
    { "lat": 52.22971, "lng": 21.01218 },
    { "lat": 52.22990, "lng": 21.01280 }
  ],
  "expandable": true
}
```

- `start`, `end`: `NodeRef` endpoints of this segment (also the segment identifier; also used for drawing and shard routing)
- `polyline`: array of `Coordinate`
  - Always present.
  - If the segment has not been expanded yet, `polyline` MUST contain exactly two points: `[start, end]`.
  - If the segment is expanded, intermediate points represent the fully expanded path within that segment.
- `expandable`: boolean
  - `true` means the client MAY request expansion for this segment (using `(start.node_id, end.node_id)`).
  - When a segment is returned in expanded form, `expandable` MUST be `false` (even if `polyline` happens to have only two points).

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
      "start": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
      "end": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
      "polyline": [
        { "lat": 52.22971, "lng": 21.01218 },
        { "lat": 52.22990, "lng": 21.01280 }
      ],
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

- Routing API MUST return `start.node_id` and `end.node_id` for every segment.
- Clients MUST use the returned `(start.node_id, end.node_id)` pair as the identifier when requesting expansion.
- The Routing API SHOULD return `start.lat/lng` and `end.lat/lng` consistent with the returned node IDs.
- For segments that are returned unexpanded, the Routing API MUST return `polyline` as `[start, end]` (two points).

## Endpoint: Expand segments (batch)

### `POST /v1/route/expand`

Expand one or more segments by `(start.node_id, end.node_id)` endpoints. Client always uses the batch form (batch size may be 1).

#### Request

```json
{
  "segments": [
    {
      "start": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
      "end": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 }
    },
    {
      "start": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
      "end": { "node_id": "8963867000", "lat": 52.23010, "lng": 21.01310 }
    }
  ]
}
```

#### Response (200 OK)

```json
{
  "segments": [
    {
      "start": { "node_id": "8963866048", "lat": 52.22971, "lng": 21.01218 },
      "end": { "node_id": "8963866021", "lat": 52.22990, "lng": 21.01280 },
      "polyline": [
        { "lat": 52.22971, "lng": 21.01218 },
        { "lat": 52.22975, "lng": 21.01230 },
        { "lat": 52.22990, "lng": 21.01280 }
      ],
      "expandable": false
    }
  ],
  "errors": []
}
```

#### Semantics

- The expansion key is the directional pair `(start.node_id, end.node_id)`.
- Request `start.lat/lng` and `end.lat/lng` are included for shard routing and may be ignored for expansion lookup.
- Clients SHOULD send the `start`/`end` objects exactly as returned by `POST /v1/route` for the corresponding segment.

#### Error responses

- **400 Bad Request** (e.g., empty `segments`):

```json
{
  "error": { "code": "invalid_request", "message": "segments must be a non-empty array." }
}
```
