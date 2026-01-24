## Quick start

```
cd serving
export GCS_BUCKET="rsp_graph_data"
export GCS_PREFIX="protos"
export WORKER_SERVICE_HOST="127.0.0.1"
export WORKER_SERVICE_PORT="50051"
uv run python -m serving.shard_worker
```

```
cd serving
export GCS_BUCKET="rsp_graph_data"
export GCS_PREFIX="protos"
export WORKER_SERVICE_HOST="127.0.0.1"
export WORKER_SERVICE_PORT="50051"
uv run python -m serving.routing_api
```

```
cd frontend
npm install
VITE_API_TARGET=http://localhost:8080 npm run dev
```