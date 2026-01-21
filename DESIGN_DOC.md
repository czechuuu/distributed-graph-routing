# Distributed Graph Routing System: Design Document

## Context and Scope

### Problem Statement

This project addresses the challenge of **finding shortest paths in a large, distributed graph** where the graph is too large to fit on a single machine. The system is designed to support **repetitive queries** — scalably serving path-finding requests between arbitrary node pairs after an initial preprocessing phase.

The graph represents a **road network** with the following properties:
- **Sparse**: Edge count is O(|V|) — typical of road networks
- **Weighted**: Edges have associated costs (distances/travel times)
- **Planar**: The graph can be embedded in 2D without edge crossings
- **Geospatially Located**: Each node has (latitude, longitude) coordinates, enabling geographic-aware sharding

### Why Distributed?

The graph we are working with — the road network of Europe — is too large to fit into the memory of a single machine. The raw CSV representation alone is **TODO_SIZE**, and the in-memory graph structure would be even larger.

This constraint drives our entire architecture:

| Challenge | Our Solution |
|-----------|--------------|
| **Storage** | Shard and store the graph in Google Cloud Bigtable |
| **Preprocessing** | Process shards in parallel using Apache Beam on Dataflow |
| **Query Serving** | Minimize shard fetches by precomputing an overlay graph that captures inter-shard connectivity |

### Chosen Focus Areas

Given the broad scope of the problem, we chose to focus primarily on the following areas (as recommended in the project statement):

1. **Expressing the shortest-paths problem in a scalable way**: Using overlay graphs and hierarchical contraction to reduce the effective graph size at query time
2. **Sharding state without data duplication**: Using S2 geometry cells for geographic partitioning that guarantees each node belongs to exactly one shard
3. **Designing distributed algorithms**: Implementing a two-phase approach with heavy preprocessing and lightweight query serving
4. **Utilizing existing tools provided by GCP**: We tried not to reinvent the wheel and instead use the tools provided by GCP to the fullest extent possible to see how their capabilities and performance in real world applications

### Scope Boundaries — What We Are Solving

Our system addresses the following:

| Concern | Our Approach |
|---------|--------------|
| **Large graph storage** | Distributed storage in Google Cloud Bigtable, sharded by S2 cell ID |
| **Efficient pathfinding** | Overlay graph with precomputed shortcuts between shard boundary nodes |
| **Scalable query serving** | Serving layer loads only the overlay graph at startup; fetches individual shards on-demand |
| **Preprocessing scalability** | Dataflow-based parallel pipeline that processes each shard independently |
| **Visualization & debugging** | React frontend with OpenStreetMap integration to display shards, paths, and routing results |
| **Fault tolerance / State recreation** | All the state is stored in BigTable, so if a serving node crashes, it can be easily restarted with the same state |
TODO: not yet implemented but i suppose could easily be done
| **Dynamic horizontal scaling** | We could make the serving layer autoscale and put a load balancer in front of it |


### Scope Boundaries — What We Are NOT Solving

To maintain focus, we explicitly chose **not to address** the following possible extensions:

| Out of Scope | Reason |
|--------------|--------|
| **Dynamic graph changes** (add/remove nodes/edges) | Requires complex invalidation of precomputed shortcuts |
| **Density-sensitive sharding** | S2 cell-based sharding provides consistent geographic partitioning regardless of node density |
| **Data redundancy / Replication** | We do not implement application-level replication for the serving layer - we assume that BigTable provides enough durability |

### System Constraints

The following constraints guided our design decisions:

1. **Memory Limits**: The total memory usage across the serving cluster must remain below a predefined threshold after the system stabilizes (preprocessing complete, ready to serve queries). This drove our decision to:
   - Store the full graph in Bigtable (not in-memory)
   - Load only the overlay graph into memory at startup
   - Fetch individual shards on-demand during query processing

2. **Preprocessing Once, Query Many Times**: We optimize for the common case where the graph is static and queries are frequent. This justifies expensive preprocessing (shortcut computation via Dijkstra from every boundary node) to enable fast query response times.

---

## Architecture and Design

### Key Terminology

Before diving into the architecture, here are the key terms used throughout this document:

| Term | Definition |
|------|------------|
| **Shard** | A geographic partition of the graph, defined by an S2 cell ID (level 9). Contains all nodes within that cell and all edges between them. |
| **Boundary Node** | A node that has at least one edge crossing into a different shard. These are the "interface" nodes used to connect shards. |
| **Bridge Edge** | An edge that connects two nodes in different shards (crosses shard boundaries). |
| **Shortcut** | A precomputed path between two boundary nodes within the same shard, representing the shortest path between them through that shard's internal nodes. |
| **Overlay Graph** | The graph containing only boundary nodes, shortcuts, and bridge edges. This is the "compressed" view of the entire graph. |
| **Intra-Shard Edge** | An edge where both endpoints belong to the same shard. |

### System Diagram

The system consists of four main layers:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          DATA INGESTION LAYER                              │
├────────────────────────────────────────────────────────────────────────────┤
│  CSV Files (nodes.csv, edges.csv)                                          │
│       │                                                                    │
│       ▼                                                                    │
│  Google Cloud Storage → Cloud Function → BigQuery (with S2 ShardId)       │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         PREPROCESSING LAYER                                │
├────────────────────────────────────────────────────────────────────────────┤
│  Apache Beam / Dataflow                                                    │
│       │                                                                    │
│       ├── Partition edges by shard                                         │
│       ├── Identify boundary nodes for each shard                          │
│       ├── Compute shortcuts (Dijkstra from each boundary node)            │
│       └── Build overlay graph                                             │
│       │                                                                    │
│       ▼                                                                    │
│  Bigtable: shards, shortcuts, overlay_graph, node_index                   │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          SERVING LAYER                                     │
├────────────────────────────────────────────────────────────────────────────┤
│  GraphFacade + Routing Engine                                              │
│       │                                                                    │
│       ├── On startup: Load overlay graph (shortcuts + bridges)            │
│       ├── On query: Fetch source/destination shards on-demand             │
│       ├── Merge overlay + shards into query-specific graph                │
│       └── Bidirectional Dijkstra → Expand shortcuts → Return path         │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           DATA DOMAIN + FRONTEND                           │
├────────────────────────────────────────────────────────────────────────────┤
│  FastAPI Data Domain (wraps Bigtable for frontend)                        │
│       │                                                                    │
│       ▼                                                                    │
│  React + Leaflet Frontend (visualization, debugging, path queries)        │
└────────────────────────────────────────────────────────────────────────────┘
```

### Why This Architecture?

The core insight driving our design is the **overlay graph approach**:

1. **Sharding alone is not enough**: If we simply shard the graph and run Dijkstra across shards, every query would need to fetch potentially many shards as the search expands. This defeats the purpose of sharding.

2. **Precompute cross-shard connectivity**: By running Dijkstra from every boundary node within each shard, we can precompute the shortest paths between all pairs of boundary nodes. These become "shortcuts" that allow us to skip the internal nodes entirely.

3. **Two-level hierarchy**: At query time, we only need:
   - The **overlay graph** (always in memory) — contains all boundary nodes and shortcuts
   - The **source shard** — to connect the start node to boundary nodes
   - The **destination shard** — to connect the end node to boundary nodes

This reduces a query from potentially touching the entire graph to touching at most **2 shards + the overlay**.

### Component Deep Dive

#### 1. Data Ingestion Layer

**Purpose**: Transform raw CSV data into a sharded, queryable format in BigQuery.

**Flow**:
1. User uploads `nodes.csv` (id, latitude, longitude) and `edges.csv` (u, v, weight) to a GCS bucket
2. A Cloud Function triggers on file upload
3. The function loads data into BigQuery tables
4. For the nodes table, it computes `ShardId` using BigQuery's built-in S2 functions: `S2_CELLIDFROMPOINT(ST_GEOGPOINT(x, y), 9)`

**Key Design Decision**: We use S2 cells at level 9 for sharding. This provides a good balance between:
- Shard size (not too many nodes per shard, keeping preprocessing tractable)
- Number of shards (not too many, keeping overlay graph manageable)
- Geographic coherence (nearby nodes are in the same or adjacent shards)

#### 2. Preprocessing Layer (Dataflow Pipeline)

**Purpose**: Transform the raw graph into the overlay graph structure stored in Bigtable.

**Pipeline Steps**:

```
Read Nodes & Edges from BigQuery
         │
         ▼
    Attach ShardId to each edge endpoint
         │
         ▼
    Group edges by shard → (shard_id, [edges])
         │
         ▼
    For each shard, in parallel:
    ├── Build local NetworkX graph
    ├── Identify boundary nodes (nodes with cross-shard edges)
    ├── Run Dijkstra from each boundary node to all other boundary nodes
    ├── Extract shortcuts (boundary-to-boundary paths)
    └── Emit: intra-shard edges, shortcuts, bridge edges
         │
         ▼
    Merge all shortcuts + bridges → Overlay Graph
         │
         ▼
    Write to Bigtable:
    ├── `shards` table: Full intra-shard graph for each shard
    ├── `shortcuts` table: Path expansions (node sequences) for each shortcut
    ├── `overlay_graph` table: Single row with all shortcuts + bridges
    └── `node_index` table: node_id → shard_id mapping
```

**Key Design Decision**: We chose to store shortcut **expansions** (the full path of nodes) in a separate table. This allows the serving layer to:
- Use shortcuts for fast pathfinding (just weight, no path details)
- Fetch the actual path only when needed for the final result

#### 3. Serving Layer

**Purpose**: Answer shortest-path queries efficiently by combining the overlay graph with on-demand shard fetching.

**Components**:
- **GraphFacade**: Manages access to Bigtable, caches fetched shards and shortcut expansions
- **Routing Engine**: Implements the pathfinding algorithm

**Query Flow**:

```
1. Receive query: (start_node, start_shard, end_node, end_shard)
         │
         ▼
2. Build query graph:
   ├── Start with overlay graph (already in memory)
   ├── Fetch and merge source shard from Bigtable
   └── Fetch and merge destination shard from Bigtable
         │
         ▼
3. Run Dijkstra on merged graph
   (shortcuts appear as single edges with precomputed weights)
         │
         ▼
4. Expand shortcuts in the result path:
   ├── For each shortcut edge (u, v) in path
   └── Fetch expansion from shortcuts table → [u, n1, n2, ..., v]
         │
         ▼
5. Return full path with node coordinates
```

**Key Design Decision**: We load the **entire overlay graph** into memory at startup. This is acceptable because:
- The overlay only contains boundary nodes (small fraction of total nodes)
- Each shard contributes O(boundary²) shortcuts, but boundary nodes are typically O(√n) of shard nodes
- For road networks, this keeps the overlay manageable (tested with Europe graph)

#### 4. Data Domain + Frontend

**Purpose**: Provide visualization and debugging capabilities for the distributed graph system.

**Data Domain** (FastAPI service):
- Wraps Bigtable access with a REST API
- Endpoints: `/overlay`, `/shard/{shard_id}`, `/shortcut/{from}/{to}`, `/node/{node_id}/shard`
- Used by the frontend for visualization (separate from the serving layer's routing API)

**Frontend** (React + Leaflet):
- Displays the graph overlaid on OpenStreetMap
- Allows loading individual shards by ID or by clicking on the map
- Visualizes routing results with path highlighting
- Shows shard boundaries, boundary nodes, and bridge edges

### Trade-offs and Alternatives Considered

| Decision | Alternative | Why We Chose This |
|----------|-------------|-------------------|
| **S2 cell sharding** | k-means clustering, METIS partitioning | S2 is simple, deterministic, and has native BigQuery support. No need for a separate partitioning step. |
| **Full shortcut precomputation** | On-demand shortcut computation | Memory is cheaper than latency. Precomputing allows O(1) edge weight lookups at query time. |
| **Store overlay in single Bigtable row** | Store overlay as separate edges | Single row allows atomic loading at startup. Overlay is small enough to serialize as one protobuf. |
| **NetworkX for in-memory graphs** | Custom graph implementation | NetworkX is well-tested and sufficient for our scale. Optimization would be premature. |
| **Bidirectional Dijkstra** | A* with geographic heuristic | Our graph includes shortcuts that may not respect geographic distance, making A* heuristics unreliable. |

