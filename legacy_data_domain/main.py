from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
try:
    # When run as a package: `python -m uvicorn legacy_data_domain.main:app ...`
    from .bigtable_client import BigtableClient
except ImportError:
    # When run from inside this directory: `python -m uvicorn main:app ...`
    from bigtable_client import BigtableClient
from google.protobuf.json_format import MessageToDict
import os
from pydantic import BaseModel

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = None

@app.on_event("startup")
def startup_event():
    global client
    # Credentials are implicit from GOOGLE_APPLICATION_CREDENTIALS
    client = BigtableClient()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/overlay")
def get_overlay():
    overlay = client.get_overlay()
    # Convert protobuf to JSON-compatible dict
    return MessageToDict(overlay)

@app.get("/shard/{shard_id}")
def get_shard(shard_id: str):
    shard = client.get_shard(shard_id)
    if not shard:
        raise HTTPException(status_code=404, detail="Shard not found")
    return MessageToDict(shard)

@app.get("/shortcut/{from_node}/{to_node}")
def get_shortcut(from_node: str, to_node: str):
    # IDs are fixed64 in proto, likely passed as strings or numbers. 
    # Proto uses fixed64.
    path = client.get_shortcut(int(from_node), int(to_node))
    if not path:
        raise HTTPException(status_code=404, detail="Shortcut not found")
    return MessageToDict(path)

@app.get("/node-shard/{node_id}")
def get_node_shard(node_id: str):
    shard_id = client.get_node_shard(node_id)
    if shard_id is None:
        raise HTTPException(status_code=404, detail="Node not found in index")
    return {"shard_id": str(shard_id)}


class NodeList(BaseModel):
    node_ids: list[str]

@app.post("/node-shards/batch")
def get_node_shards_batch(body: NodeList):
    mapping = client.get_node_shards_batch(body.node_ids)
    # Convert ints to strings for safety/consistency
    return {k: str(v) for k, v in mapping.items()}
