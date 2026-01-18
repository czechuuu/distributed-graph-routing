# Preprocessing Subsystem

The **Preprocessing** subsystem is responsible for ingesting raw graph data (CSV), loading it into BigQuery, and processing it via a distributed Dataflow pipeline to prepare it for the Serving Layer.

## Architecture

1.  **Ingestion**:
    *   Users upload files to a Google Cloud Storage (GCS) bucket (e.g., `raw_graph_data`):
        *   `graph_data/nodes.csv`
        *   `graph_data/edges.csv`
    *   A **Google Cloud Function** triggers on the `google.cloud.storage.object.v1.finalized` event.

2.  **Validation & Loading**:
    *   The Cloud Function determines if the file is a valid node or edge list (must be in `graph_data/`).
    *   It effectively enforces a schema and loads the data into **BigQuery** (`graph_data.nodes` and `graph_data.edges`).
    *   It automatically calculates and updates `ShardId` for nodes based on their geospatial coordinates (S2 Cells).

3.  **Pipeline Trigger**:
    *   The function checks timestamps of both tables.
    *   If both `nodes` and `edges` have been updated within a short window (**30 seconds**), it triggers the **Dataflow Pipeline**.

4.  **Processing (Dataflow)**:
    *   The pipeline runs on Google Dataflow (Apache Beam).
    *   It reads the full graph from BigQuery.
    *   It partitions the graph into shards.
    *   It computes detailed contraction hierarchies (shortcuts) and overlay graphs.
    *   **Output**: The processed graph data is written to **BigTable** tables:
        *   `shards`: Intra-shard edges and node locations.
        *   `shortcuts`: Precomputed shortcut paths for optimized routing.
        *   `overlay`: High-level graph connecting boundary nodes.

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
    *   **Trigger**: GCS Object Finalized on `raw_graph_data` bucket.
    *   **Memory**: 512Mi.

## Local Development

To work on this project locally:

1.  **Install dependencies using uv**:
    ```bash
    uv sync
    ```
    This creates a valid virtual environment with all pinned dependencies.
    