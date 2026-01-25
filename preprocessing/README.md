# Preprocessing Subsystem

The **Preprocessing** subsystem ingests raw graph data from GCS (parquet or tiled OSM PBF) and processes it with Dataflow jobs.

## Local tiling script (PBF -> osm_tiles)

Use `tile_osm_fast.sh` to download and tile OSM data for Job 0. Uses `osmium-tool` (C++) for fast single-pass extraction.

**Prerequisites:**
```bash
sudo apt install osmium-tool jq
```

**Usage:**
```bash
cd ../scripts
./tile_osm_fast.sh <region> [gcs_path]
```

**Supported regions:** `mazowieckie`, `poland`, `europe`

**Examples:**

```bash
./tile_osm_fast.sh mazowieckie gs://rsp_graph_data_test/v2/osm_tiles

./tile_osm_fast.sh poland gs://rsp_graph_data/v2/osm_tiles

./tile_osm_fast.sh europe gs://rsp_graph_data_massive/v2/osm_tiles
```

## Job 0

1. **Ingestion**:
   * Tiled OSM PBFs: `gs://rsp_graph_data/v2/osm_tiles/*.osm.pbf`
2. **Processing (Dataflow Job 0)**:
   * Parses OSM nodes and driveable ways from PBF tiles.
   * Enriches edges with endpoint coordinates and S2 shard IDs per tile.
   * Computes edge weights as **travel time seconds** using tag heuristics.
   * Deduplicates overlapping tiles.
   * Emits stage‑1 sharded outputs (same layout as Job 1).
3. **Outputs**:
   * Bridges: `gs://rsp_graph_data/v2/processed/bridges/*.parquet`
   * Per shard: `gs://rsp_graph_data/v2/processed/shard_id=x/`
     * `edges/*.parquet`
     * `nodes/*.parquet`
     * `boundary_in/*.parquet`
     * `boundary_out/*.parquet`

### How to Run Job 0

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
  --setup_file=setup.py \
  --input_pbf="gs://rsp_graph_data_test/v2/osm_tiles/*.osm.pbf" \
  --output_base="gs://rsp_graph_data_test/v2/processed" \
  --worker_machine_type=n2-standard-2 \
  --autoscaling_algorithm=THROUGHPUT_BASED \
  --max_num_workers=12
```

You can specify the weight mode with `--weight_mode=time_s|distance_m` (default: `time_s`).

### Job 0 performance notes

- **Tile size matters**: each tile is parsed and enriched in-memory, so smaller tiles reduce per-worker memory pressure. Adjust `TILE_SIZE_DEG` in `scripts/tile_osm_fast.sh` if needed.
- **Worker parallelism**: prefer more workers with fewer concurrent tiles over fewer workers with high concurrency. Tune `--max_num_workers`, `--worker_machine_type`, and autoscaling settings when running on Dataflow.
- **Missing nodes**: missing node references are logged as warnings and the affected edges are skipped to preserve job progress. If warnings are frequent, re-check tile extraction settings or overlap.


## Job 2

Job 2 consumes job 0 outputs and writes protobufs to GCS.

```bash
cd preprocessing
uv run python -m dataflow.job2_main \
  --project=repetitive-shortest-paths \
  --temp_location=gs://shortest_paths_preprocessing_dataflow/temp \
  --staging_location=gs://shortest_paths_preprocessing_dataflow/staging \
  --region=us-central1 \
  --runner=DataflowRunner \
  --setup_file=setup.py \
  --input_base="gs://rsp_graph_data_test/v2/processed" \
  --output_base="gs://rsp_graph_data_test/v2/protos"
```

### Job 2 bucket configuration

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

**Install dependencies using uv** (from `preprocessing/`):

```bash
cd preprocessing
uv sync
```

This creates a valid virtual environment with all pinned dependencies.
    


## Job 1 (Legacy)

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

### How to Run Job 1

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