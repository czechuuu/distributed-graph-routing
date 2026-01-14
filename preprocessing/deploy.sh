gcloud functions deploy graph-loader-function \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=process_graph_upload \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=raw_graph_data" \
  --memory=512Mi \
  --timeout=300s
  