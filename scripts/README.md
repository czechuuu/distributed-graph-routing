To trigger the preprocessing pipeline, first ensure that `graph_data/nodes.csv` and `graph_data/edges.csv` are present in the `raw_graph_data` bucket. Then run the following command:

```
curl -X POST https://us-central1-repetitive-shortest-paths.cloudfunctions.net/graph-loader-function \
-H "Authorization: bearer $(gcloud auth print-identity-token)" \
-H "Content-Type: application/json" \
-d '{"bucket": "raw_graph_data"}'
```