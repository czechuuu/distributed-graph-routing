# Serving Subsystem

This package contains the serving layer for the routing system:

- `routing-api`: public HTTP API (`/v1/route`, `/v1/route/expand`)
- `shard-worker`: internal gRPC service for shard-local operations

## Quick start (local)

Set env vars (example):

- `GCS_BUCKET=<bucket>`
- `GCS_PREFIX=<prefix>` (e.g. `protos`)

Then run:

```bash
uv run python -m serving.routing_api
uv run python -m serving.shard_worker
```

Both services default to localhost ports and can be overridden via env.

## Docker (local)

Build:

```bash
docker build -f serving/Dockerfile.routing-api -t routing-api .
docker build -f serving/Dockerfile.shard-worker -t shard-worker .
```

Run (example):

```bash
docker run --rm -p 8080:8080 \
  -e GCS_BUCKET=<bucket> -e GCS_PREFIX=protos \
  routing-api

docker run --rm -p 50051:50051 -p 8081:8081 \
  -e GCS_BUCKET=<bucket> -e GCS_PREFIX=protos \
  shard-worker
```

## Minimal integration test (manual)

1. Ensure the Job 2 protobufs exist in GCS:
   - `gs://<bucket>/<prefix>/overlay_graph.pb`
   - `gs://<bucket>/<prefix>/shard_id=<id>/shard_graph.pb`

2. Start `shard-worker` and `routing-api` (locally or via Docker).

3. Call the API:

```bash
curl -s -X POST http://localhost:8080/v1/route \
  -H "Content-Type: application/json" \
  -d '{"start":{"lat":52.2297,"lng":21.0122},"end":{"lat":52.2400,"lng":21.0300}}'
```

4. Expand returned segments:

```bash
curl -s -X POST http://localhost:8080/v1/route/expand \
  -H "Content-Type: application/json" \
  -d '{"segments":[{"u":{"node_id":"8963866048","lat":52.22971,"lng":21.01218},"v":{"node_id":"8963866021","lat":52.22990,"lng":21.01280}}]}'
```
