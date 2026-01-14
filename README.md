# Distributed Graph Routing

Dataflow job for distributed graph routing preprocessing. This pipeline processes graph shards in parallel to compute shortcuts (shortest paths between boundary nodes) and prepares the data for BigTable.

## Prerequisites

-   Python 3.8+
-   Google Cloud SDK (`gcloud`) configured with your project.

## Installation

This project uses `uv` for reproducible dependency management.

1.  **Install uv** (if not already installed):
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Sync dependencies**:
    This command creates the virtual environment (`.venv`) and ensures all dependencies (including `pip` and the correct `protobuf` version) are installed with the exact versions specified in `uv.lock`.
    ```bash
    uv sync
    ```

3.  **Activate the environment**:
    ```bash
    source .venv/bin/activate
    ```

## Running Tests

Once dependencies are installed, you can run the unit tests:

```bash
# Run all tests
python3 -m unittest discover tests

# Run shared component tests
python3 -m unittest tests/common/test_algo.py

# Run contraction pipeline tests
python3 -m unittest tests/pipeline/test_pipeline.py
```

## Running the Pipeline

To run the Dataflow job (requires GCP authentication):

1.  Authenticate locally:
    ```bash
    gcloud auth application-default login
    ```

2.  Run the pipeline script:
    ```bash
  python3 -m contractions.main \
      --project repetitive-shortest-paths \
      --temp_location gs://repetitive_shortest_paths_contractions_dataflow/temp \
      --input_nodes_table repetitive-shortest-paths:graph_data.nodes \
      --input_edges_table repetitive-shortest-paths:graph_data.edges \
      --bt_instance routing-instance \
      --shortcuts_table shortcuts \
      --shards_table shards \
      --overlay_table overlay_graph
    ```

## Deploying to Dataflow

To run the job on the Dataflow service (instead of locally), append the `Runner` and `Region` arguments:

```bash
python3 -m contractions.main \
  --project repetitive-shortest-paths \
  --temp_location gs://repetitive_shortest_paths_contractions_dataflow/temp \
  --staging_location gs://repetitive_shortest_paths_contractions_dataflow/staging \
  --input_nodes_table repetitive-shortest-paths:graph_data.nodes \
  --input_edges_table repetitive-shortest-paths:graph_data.edges \
  --bt_instance routing-instance \
  --shortcuts_table shortcuts \
  --shards_table shards \
  --overlay_table overlay_graph \
  --runner DataflowRunner \
  --region us-central1 \
  --worker_machine_type e2-standard-2 \
  --setup_file ./setup.py
```

Ensure you have:
1.  Enabled the Dataflow API.
2.  Created the GCS buckets for temp/staging.
3.  Authenticated with `gcloud auth application-default login`.

## Project Structure

-   `shared/`: Common code (models, graph algos) usable by both Dataflow and Serving components.
-   `contractions/`: Dataflow-specific code (pipeline, main, IO).
-   `setup.py`: Package configuration.
-   `DESIGN_DOC.md`: High-level system design.
-   `PROJECT_STATEMENT.md`: Problem definition.
