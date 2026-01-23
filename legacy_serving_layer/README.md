# Serving Layer Instructions


## Prerequisites
Before running the deployment or accessing the service, ensure you have:
1.  **Google Cloud Project**: Active project `repetitive-shortest-paths`.
2.  **Google Cloud Bigtable**: An instance named `routing-instance` with tables `shards`, `shortcuts`, `overlay_graph`, and `node_index` already populated with data.
3.  **gcloud CLI**: Installed and authenticated (`gcloud auth login`).

## 1. Running Locally
To run the service locally on your machine:

1.  **Authentication**: Ensure you are authenticated with Google Cloud:
    ```bash
    gcloud auth application-default login
    ```

2.  **Run Script**: Use the helper script to install dependencies and start the server:
    ```bash
    ./run_local.sh
    ```
    Or manually:
    ```bash
    pip install fastapi uvicorn google-cloud-bigtable networkx ujson
    cd ..  # Go to project root (distributed-graph-routing)
    python3 -m uvicorn serving_layer.app:app --reload
    ```
    The service will be available at `http://localhost:8000`.

## 2. Deployment
To deploy the code to the VM:
```bash
./deploy.sh
```
This script packages the code, uploads it to the `routing-backend` VM, and restarts the service.

## 2. Connecting (SSH Tunnel)
To access the API from your local machine (localhost), run:

```bash
gcloud compute ssh routing-backend \
    --zone=us-central1-c \
    --project=repetitive-shortest-paths \
    -- -L 8000:localhost:8000
```
Keep this terminal open. You can now access the API at `http://localhost:8000`.

## 3. Testing (API Usage)

### Basic Route (Intra-Shard)
Nodes in the same shard (Shard `5116266404223385600`).
```bash
curl -X POST "http://localhost:8000/route" \
     -H "Content-Type: application/json" \
     -d '{
           "start_node": 8963866048, 
           "start_node_shard": 5116266404223385600, 
           "end_node": 8963866021, 
           "end_node_shard": 5116266404223385600
         }'
```

### Complex Route (Cross-Shard, Multi-Hop)
Nodes in different shards, requiring a path through a bridge.
```bash
curl -X POST "http://localhost:8000/route" \
     -H "Content-Type: application/json" \
     -d '{
           "start_node": 314450197, 
           "start_node_shard": 5116271626903617536, 
           "end_node": 6700918052, 
           "end_node_shard": 5116271764342571008
         }'
```

## 4. Debugging
View service logs on the VM:
```bash
gcloud compute ssh routing-backend --zone=us-central1-c --command='journalctl -u routing-backend -f'
```
