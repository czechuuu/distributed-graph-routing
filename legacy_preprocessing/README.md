# Legacy pipeline

Legacy Dataflow pipeline that reads processed shard data from GCS and writes
routing artifacts to Bigtable using the legacy schema.

## Run legacy pipeline (Dataflow)

```bash
uv run --project legacy_preprocessing python legacy_preprocessing/legacy_main.py \
  --project=repetitive-shortest-paths \
  --temp_location=gs://shortest_paths_preprocessing_dataflow/temp \
  --input_base=gs://rsp_graph_data_test/processed \
  --instance_id=routing-instance \
  --setup_file=legacy_preprocessing/setup.py \
  --runner=DataflowRunner \
  --region=us-central1
```
