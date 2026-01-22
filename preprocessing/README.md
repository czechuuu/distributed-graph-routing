# Preprocessing Subsystem

The **Preprocessing** subsystem is responsible for ingesting raw graph data (CSV), loading it into BigQuery, and processing it via a distributed Dataflow pipeline to prepare it for the Serving Layer.

## Architecture

1.  **Ingestion**:
    *   Users upload files to a Google Cloud Storage (GCS) bucket (e.g., `raw_graph_data`):
        *   `graph_data/nodes.csv`
        *   `graph_data/edges.csv`

2.  **Triggering**:
    *   A **Google Cloud Function** (`graph-loader-function`) is triggered manually via HTTP request to process the files.

3.  **Validation & Loading**:
    *   The Cloud Function determines if the file is a valid node or edge list (must be in `graph_data/`).
    *   It effectively enforces a schema and loads the data into **BigQuery** (`graph_data.nodes` and `graph_data.edges`).
    *   It automatically calculates and updates `ShardId` for nodes based on their geospatial coordinates (S2 Cells).
    *   **Skip Loading**: The loading step can be optionally skipped if the data is already in BigQuery.

4.  **Pipeline Trigger**:
    *   After processing (or skipping), the function unconditionally triggers the **Dataflow Pipeline**.

5.  **Processing (Dataflow)**:
    *   The pipeline runs on Google Dataflow (Apache Beam).
    *   It reads the full graph from BigQuery.
    *   It partitions the graph into shards.
    *   It computes detailed contraction hierarchies (shortcuts) and overlay graphs.
    *   **Output**: The processed graph data is written to **BigTable** tables:
        *   `shards`: Intra-shard edges and node locations.
        *   `shortcuts`: Precomputed shortcut paths for optimized routing.
        *   `overlay`: High-level graph connecting boundary nodes.

## How to Trigger

To trigger the preprocessing pipeline, first ensure that `graph_data/nodes.csv` and `graph_data/edges.csv` are present in the `raw_graph_data` bucket.

### Standard Trigger (Load Data + Run Pipeline)
Run the following command to load data from GCS to BigQuery and then start the Dataflow pipeline:

```bash
curl -X POST https://us-central1-repetitive-shortest-paths.cloudfunctions.net/graph-loader-function \
-H "Authorization: bearer $(gcloud auth print-identity-token)" \
-H "Content-Type: application/json" \
-d '{"bucket": "raw_graph_data"}'
```

### Pipeline Only (Skip Data Loading)
To trigger the pipeline **without** reloading data from GCS to BigQuery (e.g., for retries/debugging), add `"skip_load": true` to the JSON body:

```bash
curl -X POST https://us-central1-repetitive-shortest-paths.cloudfunctions.net/graph-loader-function \
-H "Authorization: bearer $(gcloud auth print-identity-token)" \
-H "Content-Type: application/json" \
-d '{"bucket": "raw_graph_data", "skip_load": true}'
```

## Deployment

We use a helper script to deploy the Cloud Function with the correct configuration.

1.  **Prerequisites**:
    *   `gcloud` CLI installed and authenticated.
    *   Appropriate permissions (Cloud Functions Developer, Service Account User, etc.).

2.  **Deploy**:
    Run the deployment script from this directory:

    ```bash
    ./deploy.sh
    ```

    This command deploys a **Gen2 Cloud Function** (`graph-loader-function`) with:
    *   **Runtime**: Python 3.11
    *   **Trigger**: HTTP (Authenticated)
    *   **Entry Point**: `process_manual_trigger`
    *   **Memory**: 512Mi.

## Local Development

To work on this project locally:

1.  **Install dependencies using uv**:
    ```bash
    uv sync
    ```
    This creates a valid virtual environment with all pinned dependencies.
    