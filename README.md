# Distributed Graph Routing

A distributed routing system for large-scale road networks using geographic sharding (S2 cells) and an overlay graph for efficient cross-shard pathfinding.

![Sopot to Zakopane Demo](gif/Sopot-Zakopane.gif)

## Overview

This system partitions road network graphs into geographic shards using S2 cells at level 9. Each shard stores its internal edges, while an overlay graph captures cross-shard connectivity through bridge edges and precomputed shortcuts between boundary nodes.

### Key Components

- **Preprocessing** — Dataflow pipelines that transform OSM road data into sharded protobuf files stored in GCS
- **Serving Layer** — FastAPI routing API + gRPC shard workers that handle distributed shortest-path queries
- **Frontend** — React/Leaflet map interface for interactive route visualization

## Architecture

```
Client → Routing API → Shard Workers (gRPC) → GCS (graph data)
                ↓
         Overlay Graph (in-memory)
```

The Routing API loads the overlay graph at startup and coordinates with shard workers to:
1. Snap user coordinates to nearest road nodes
2. Compute boundary distances within start/end shards
3. Run bidirectional Dijkstra on the overlay graph
4. Expand the compressed route path on demand

## Quick Start

See [quickstart.md](quickstart.md) for local development setup.

## Documentation

- [API.md](API.md) — Client ↔ Routing API specification
- [cluster.md](cluster.md) — Kubernetes deployment architecture
- [preprocessing/README.md](preprocessing/README.md) — Dataflow job documentation
- [tiling/README.md](tiling/README.md) — OSM tiling for large regions

## Project Structure

```
├── frontend/          # React + Leaflet map UI
├── serving/           # Routing API and shard worker services
├── preprocessing/     # Apache Beam/Dataflow pipelines
├── shared/            # Generated protobuf definitions
├── protos/            # Proto source files
├── k8s/               # Kubernetes manifests
├── scripts/           # Utility scripts (tiling, protobuf gen)
├── benchmarks/        # E2E performance testing framework
└── tiling/            # VM-optimized OSM tiling for Europe-scale data
```
