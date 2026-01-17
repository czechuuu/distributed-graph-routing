# Routing Data Domain Service

This is a FastAPI service that wraps Google Cloud Bigtable access for the frontend.

## Prerequisites
- Python 3.8+
- Google Cloud Credentials (json key) with Bigtable Reader access.

## Installation

```bash
cd distributed_graph_routing # Root of the repo (where setup.py is)
pip install -r distributed_graph_routing/data_domain/requirements.txt
```

## Running the Server

1. Set your Google Cloud Credentials:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/key.json" # e.g. /home/{USER}/.config/gcloud/application_default_credentials.json
   export GOOGLE_CLOUD_PROJECT="your-project-id" # Required if not in credentials
   export BIGTABLE_INSTANCE="routing-instance" # Default is routing-instance
   ```
   Or rely on default credentials if running in GCP.

2. Run the server (from the root directory):
   ```bash
   uvicorn distributed_graph_routing.data_domain.main:app --reload --port 8000
   ```

## API
- `GET /overlay`: Returns the Overlay Graph
- `GET /shard/{shard_id}`: Returns a specific shard
- `GET /shortcut/{from}/{to}`: Returns the path for a shortcut
