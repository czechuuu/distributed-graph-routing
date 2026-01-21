gcloud functions deploy graph-loader-function \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=process_manual_trigger \
  --trigger-http \
  --no-allow-unauthenticated \
  --memory=512Mi \
  --timeout=300s
  