import functions_framework
from graph_manager import load_and_process_file, trigger_pipeline

@functions_framework.http
def process_manual_trigger(request):
    """
    HTTP Cloud Function to manually trigger graph processing and Dataflow pipeline.
    Expects a JSON payload with {"bucket": "your-bucket-name"}.
    """
    request_json = request.get_json(silent=True)
    
    if request_json and 'bucket' in request_json:
        bucket = request_json['bucket']
    else:
        return 'Missing "bucket" in request JSON', 400

    skip_load = request_json.get('skip_load', False)

    print(f"Manual trigger received for bucket: {bucket}, skip_load: {skip_load}")

    if not skip_load:
        # Process nodes and edges
        print("Loading nodes...")
        load_and_process_file(bucket, "graph_data/nodes.csv")
        
        print("Loading edges...")
        load_and_process_file(bucket, "graph_data/edges.csv")
    else:
        print("Skipping data load as requested.")
    
    # Trigger the pipeline unconditionally
    print("Triggering pipeline...")
    trigger_pipeline()

    return 'Processing started successfully', 200