import functions_framework
from graph_manager import handle_file_upload

@functions_framework.cloud_event
def process_graph_upload(cloud_event):
    """
    Entry point for the Cloud Function.
    Extracts event data and delegates processing to the graph manager.
    """
    data = cloud_event.data
    bucket = data["bucket"]
    file_name = data["name"]
    
    print(f"Received event for file: {file_name} in bucket: {bucket}")
    handle_file_upload(bucket, file_name)