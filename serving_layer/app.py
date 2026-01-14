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
    facade: Optional[GraphFacade] = None

state = AppState()
# TODO: We should consider implementing a Bigtable Index Table (NodeID -> ShardID) or sth 
# to allow looking up shards dynamically without memory overhead.
# For now, we require the client to provide the shard ID.
# (At least I don't see any way to get shard ID based on node ID).

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

    if USE_MOCK:
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
    start_node_shard: int
    end_node: int
    end_node_shard: int

class RouteResponse(BaseModel):
    path: List[int]
    status: str
    steps_count: int

# --- Endpoints ---
@app.get("/health")
@app.get("/health")
def health_check():
    return {"status": "ok", "mock": USE_MOCK}

@app.post("/route", response_model=RouteResponse)
def get_route(req: RouteRequest):
    if state.facade is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    u, v = req.start_node, req.end_node
    
    u, v = req.start_node, req.end_node
    shard_u, shard_v = req.start_node_shard, req.end_node_shard
    
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