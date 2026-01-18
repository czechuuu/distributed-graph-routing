import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import contextlib

from .graph_facade import GraphFacade
from .engine import find_shortest_path

# --- Configuration ---
PROJECT_ID = os.getenv("PROJECT_ID", "repetitive-shortest-paths")
INSTANCE_ID = os.getenv("INSTANCE_ID", "routing-instance")
# Change to False in production environment
USE_MOCK = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ServingLayer")

class AppState:
    facade: Optional[GraphFacade] = None

state = AppState()

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing GraphFacade...")
    try:
        # Initialize connection to Bigtable
        state.facade = GraphFacade(
            project_id=PROJECT_ID, 
            instance_id=INSTANCE_ID, 

            overlay_table_id="overlay_graph", 
            shortcuts_table_id="shortcuts",
            intra_table_id="shards", 
            use_mock=USE_MOCK
        )
    except Exception as e:
        logger.error(f"Failed to init Bigtable: {e}")
    yield
    logger.info("Shutting down...")

app = FastAPI(lifespan=lifespan)

# --- Data Models ---
class RouteRequest(BaseModel):
    start_node: int
    start_node_shard: int
    end_node: int
    end_node_shard: int

class Coordinate(BaseModel):
    lat: float
    lng: float

class RouteResponse(BaseModel):
    path: List[int]
    coordinates: List[Optional[Coordinate]]
    status: str
    steps_count: int

# --- API Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok", "mock": USE_MOCK}

@app.post("/route", response_model=RouteResponse)
def calculate_route(req: RouteRequest):
    if not state.facade:
        raise HTTPException(503, "Service not ready")
    
    node_map = {req.start_node: req.start_node_shard, req.end_node: req.end_node_shard}
    path = find_shortest_path(state.facade, req.start_node, req.end_node, node_map)
    
    if not path:
        return RouteResponse(path=[], coordinates=[], status="no_path", steps_count=0)

    # Retrieve coordinates for the path
    coords = []
    for n in path:
        c = state.facade.get_node_coords(n)
        coords.append(Coordinate(lat=c[0], lng=c[1]) if c else None)

    return RouteResponse(path=path, coordinates=coords, status="success", steps_count=len(path))

# --- Static File Serving (React Frontend) ---
static_dir = os.path.join(os.path.dirname(__file__), "static")

if os.path.exists(static_dir):
    # Serve assets (JS, CSS, Images)
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    # Catch-all route for React SPA (Single Page Application)
    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        # Do not intercept API calls
        if full_path.startswith("route") or full_path.startswith("health"):
            return {"status": "not_found_in_api"}
        
        # Return index.html for any other path to let React Router handle it
        return FileResponse(os.path.join(static_dir, "index.html"))