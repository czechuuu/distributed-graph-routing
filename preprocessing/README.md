# Preprocessing Subsystem

The **Preprocessing** subsystem ingests raw graph data from GCS (parquet or tiled OSM PBF) and processes it with Dataflow jobs.

## Architecture (Job 0)

1. **Ingestion**:
   * Tiled OSM PBFs: `gs://rsp_graph_data/osm_tiles/*.osm.pbf`
2. **Processing (Dataflow Job 0)**:
   * Parses OSM nodes and driveable ways from PBF tiles.
   * Joins ways to nodes to compute endpoint coordinates and S2 shard IDs.
   * Computes edge weights as **travel time seconds** using tag heuristics.
   * Deduplicates overlapping tiles.
   * Emits stage‑1 sharded outputs (same layout as Job 1).
3. **Outputs**:
   * Bridges: `gs://rsp_graph_data/processed/bridges/*.parquet`
   * Per shard: `gs://rsp_graph_data/processed/shard_id=x/`
     * `edges/*.parquet`
     * `nodes/*.parquet`
     * `boundary_in/*.parquet`
     * `boundary_out/*.parquet`

## How to Run Job 0

From the `preprocessing/` directory, use `uv` to run the job (DataflowRunner):

```bash
cd preprocessing
uv sync
uv run python -m dataflow.job0_main \
  --project=repetitive-shortest-paths \
  --temp_location=gs://shortest_paths_preprocessing_dataflow/temp \
  --staging_location=gs://shortest_paths_preprocessing_dataflow/staging \
  --region=us-central1 \
  --runner=DataflowRunner \
  --setup_file=setup.py
```

### Job 0 bucket configuration

You can override the source bucket and output bucket with:
* `--input_pbf="gs://<bucket>/osm_tiles/*.osm.pbf"`
* `--output_base=gs://<bucket>/processed`
* `--weight_mode=time_s|distance_m` (default: `time_s`)

### Job 0 Dataflow worker container

Job 0 parses `.osm.pbf` files using `pyosmium`, which requires native `libosmium` libraries. Run Job 0 with a custom Dataflow SDK container image that includes `pyosmium` and its native deps.

Example outline:
1. Build a custom image based on the Beam Python SDK image that installs `pyosmium` and system packages (`libosmium`, `zlib`, etc.).
2. Pass it via `--sdk_container_image=...` when running Job 0.

## Architecture (Job 1)

1. **Ingestion**:
   * Nodes parquet: `gs://rsp_graph_data/raw/nodes/*`
   * Edges parquet: `gs://rsp_graph_data/raw/edges/*`

2. **Processing (Dataflow Job 1)**:
   * Assigns S2 shard IDs at level 9 to nodes (distributed).
   * Joins edges to node shard IDs (distributed CoGroupByKey).
   * Splits bridge edges vs internal edges.
   * Derives in-boundary and out-boundary node lists.

3. **Outputs**:
   * Bridges: `gs://rsp_graph_data/processed/bridges/*.parquet`
   * Per shard: `gs://rsp_graph_data/processed/shard_id=x/`
     * `edges/*.parquet`
     * `nodes/*.parquet`
     * `boundary_in/*.parquet`
     * `boundary_out/*.parquet`

## How to Run Job 1

From the `preprocessing/` directory, use `uv` to run the job (DataflowRunner):

```bash
cd preprocessing
uv sync
uv run python -m dataflow.job1_main \
  --project=repetitive-shortest-paths \
  --temp_location=gs://shortest_paths_preprocessing_dataflow/temp \
  --staging_location=gs://shortest_paths_preprocessing_dataflow/staging \
  --region=us-central1 \
  --runner=DataflowRunner \
  --setup_file=setup.py
```

### Job 1 bucket configuration

You can override the source bucket and output bucket with:
* `--input_nodes="gs://<bucket>/raw/nodes/*"`
* `--input_edges="gs://<bucket>/raw/edges/*"`
* `--output_base=gs://<bucket>/processed`

Example test run (using `rsp_graph_data_test`):

```bash
cd preprocessing
uv run python -m dataflow.job1_main \
  --project=repetitive-shortest-paths \
  --temp_location=gs://shortest_paths_preprocessing_dataflow/temp \
  --staging_location=gs://shortest_paths_preprocessing_dataflow/staging \
  --region=us-central1 \
  --runner=DataflowRunner \
  --setup_file=setup.py \
  --input_nodes="gs://rsp_graph_data_test/raw/nodes/*" \
  --input_edges="gs://rsp_graph_data_test/raw/edges/*" \
  --output_base=gs://rsp_graph_data_test/processed
```

## How to Run Job 2

Job 2 consumes stage‑1 outputs and writes protobufs to GCS.

```bash
cd preprocessing
uv run python -m dataflow.job2_main \
  --project=repetitive-shortest-paths \
  --temp_location=gs://shortest_paths_preprocessing_dataflow/temp \
  --staging_location=gs://shortest_paths_preprocessing_dataflow/staging \
  --region=us-central1 \
  --runner=DataflowRunner \
  --setup_file=setup.py
```

### Job 2 bucket configuration

You can override the source and output bucket with:
* `--input_base="gs://<bucket>/processed"`
* `--output_base="gs://<bucket>/protos"`

Example test run (using `rsp_graph_data_test`):

```bash
cd preprocessing
uv run python -m dataflow.job2_main \
  --project=repetitive-shortest-paths \
  --temp_location=gs://shortest_paths_preprocessing_dataflow/temp \
  --staging_location=gs://shortest_paths_preprocessing_dataflow/staging \
  --region=us-central1 \
  --runner=DataflowRunner \
  --setup_file=setup.py \
  --input_base="gs://rsp_graph_data_test/processed" \
  --output_base="gs://rsp_graph_data_test/protos"
```

## Local Development

To work on this project locally:

1.  **Install dependencies using uv** (from `preprocessing/`):
    ```bash
    cd preprocessing
    uv sync
    ```
    This creates a valid virtual environment with all pinned dependencies.
    