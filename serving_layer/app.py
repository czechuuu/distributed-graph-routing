import os
import sys
import logging
import contextlib
from typing import Dict, Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.cloud import bigquery

from serving_layer.graph_facade import GraphFacade
from serving_layer.engine import find_shortest_path

# --- Configuration ---
PROJECT_ID = os.getenv("PROJECT_ID", "repetitive-shortest-paths")
INSTANCE_ID = os.getenv("INSTANCE_ID", "routing-instance")
# Use --mock to run in mock mode
USE_MOCK = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ServingLayer")

# --- Global State ---
class AppState:
    facade: Optional[GraphFacade] = None
    node_index: Dict[int, int] = {}

state = AppState()

# --- Helpers ---
def load_node_index(project_id: str) -> Dict[int, int]:
    """Loads NodeID -> ShardID mapping from BigQuery."""
    logger.info("Loading Node Index from BigQuery...")
    client = bigquery.Client(project=project_id)
    
    query = f"""
        SELECT id, ShardId 
        FROM `{project_id}.graph_data.nodes`
    """
    
    try:
        query_job = client.query(query)
        results = query_job.result()
        index = {row.id: row.ShardId for row in results}
        logger.info(f"Loaded index for {len(index)} nodes.")
        return index
    except Exception as e:
        logger.error(f"Failed to load index from BigQuery: {e}")
        return {}

# --- Lifespan ---
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting Server (Mock={USE_MOCK})...")
    
    try:
        state.facade = GraphFacade(
            PROJECT_ID, INSTANCE_ID, "shortcuts", "intra_edges", use_mock=USE_MOCK
        )
        logger.info("GraphFacade Initialized")
    except Exception as e:
        logger.critical(f"Failed to connect to Bigtable: {e}")
        sys.exit(1)

    if not USE_MOCK:
        state.node_index = load_node_index(PROJECT_ID)
    else:
        logger.info("Mock mode: Skipping BigQuery index load. Injecting mock data...")
        state.node_index = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2}
        
        # Inject Topology
        # Shard 1: 1 -> 2 -> 3 (Exit)
        # Overlay: 3 -> 4 (Bridge)
        # Shard 2: 4 (Entry) -> 5
        # Shortcut: 1 -> 3
        if state.facade:
            state.facade.overlay.add_edge(3, 4, weight=1.0)
            state.facade.overlay.add_edge(1, 3, weight=1.5)
            state.facade.shortcut_expansions[(1, 3)] = [1, 2, 3]

            state.facade.overlay.add_edge(1, 2, weight=1.0)
            state.facade.overlay.add_edge(2, 3, weight=1.0)
            state.facade.overlay.add_edge(4, 5, weight=1.0)

    yield
    # Shutdown
    logger.info("Shutting down...")

# --- App Definition ---
app = FastAPI(title="Distributed Graph Routing API", lifespan=lifespan)

# --- Models ---
class RouteRequest(BaseModel):
    start_node: int
    end_node: int

class RouteResponse(BaseModel):
    path: List[int]
    status: str
    steps_count: int

# --- Endpoints ---
@app.get("/health")
def health_check():
    return {"status": "ok", "mock": USE_MOCK, "nodes_indexed": len(state.node_index)}

@app.post("/route", response_model=RouteResponse)
def get_route(req: RouteRequest):
    if state.facade is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    u, v = req.start_node, req.end_node
    
    # Resolve Shards
    shard_u = state.node_index.get(u)
    shard_v = state.node_index.get(v)
    
    if (shard_u is None or shard_v is None) and not USE_MOCK:
        raise HTTPException(status_code=404, detail=f"Nodes {u} or {v} not found in index")
    
    node_map = {u: shard_u, v: shard_v} # Engine expects this dict for involved nodes

    try:
        path = find_shortest_path(state.facade, u, v, node_map)
    except Exception as e:
        logger.error(f"Routing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if not path:
        return RouteResponse(path=[], status="no_path_found", steps_count=0)

    return RouteResponse(path=path, status="success", steps_count=len(path))

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Start the serving layer.")
    parser.add_argument("--mock", action="store_true", help="Enable mock mode")
    args = parser.parse_args()

    if args.mock:
        USE_MOCK = True
        logger.info("Mock mode enabled via CLI flag.")

    uvicorn.run(app, host="0.0.0.0", port=8000)