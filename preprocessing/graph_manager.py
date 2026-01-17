import os
import pathlib
from datetime import timedelta
from google.cloud import bigquery
from dataflow.pipeline import create_pipeline

# Set protobuf implementation to python to avoid version conflicts in some environments
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

PROJECT_ID = "repetitive-shortest-paths"
DATASET_ID = "graph_data"

# Constants for Dataflow
TEMP_LOCATION = "gs://repetitive_shortest_paths_contractions_dataflow/temp"
STAGING_LOCATION = "gs://repetitive_shortest_paths_contractions_dataflow/staging"
INSTANCE_ID = "routing-instance"
SHORTCUTS_TABLE = "shortcuts"
SHARDS_TABLE = "shards"
OVERLAY_TABLE = "overlay_graph"
NODE_INDEX_TABLE = "node_index"
REGION = "us-central1"

def handle_file_upload(bucket, file_name):
    """
    Main logic to handle the file upload:
    1. Determines file type (nodes vs edges).
    2. Loads data into BigQuery.
    3. Triggers Dataflow pipeline if conditions are met.
    """
    uri = f"gs://{bucket}/{file_name}"
    client = bigquery.Client(project=PROJECT_ID)

    # Define schemas based ONLY on what is in the CSV
    node_csv_schema = [
        bigquery.SchemaField("id", "INT64"),
        bigquery.SchemaField("y", "FLOAT64"),
        bigquery.SchemaField("x", "FLOAT64"),
    ]

    edge_schema = [
        bigquery.SchemaField("u", "INT64"),
        bigquery.SchemaField("v", "INT64"),
        bigquery.SchemaField("weight", "FLOAT64"),
    ]

    table_name = ""
    if file_name == "graph_data/nodes.csv":
        table_name = "nodes"
        table_id = f"{PROJECT_ID}.{DATASET_ID}.nodes"
        schema = node_csv_schema
    elif file_name == "graph_data/edges.csv":
        table_name = "edges"
        table_id = f"{PROJECT_ID}.{DATASET_ID}.edges"
        schema = edge_schema
    else:
        print(f"Skipping file: {file_name} (only graph_data/nodes.csv and graph_data/edges.csv are supported)")
        return

    # Load the CSV data
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    try:
        load_job = client.load_table_from_uri(uri, table_id, job_config=job_config)
        load_job.result() 
        print(f"Successfully loaded {file_name} into {table_id}.")
    except Exception as e:
        print(f"Load Job Failed: {e}")
        return

    # Add and Update ShardId for the nodes table
    if table_name == "nodes":
        setup_query = f"""
            -- Ensure ShardId column exists if it doesn't
            BEGIN
                ALTER TABLE `{table_id}` ADD COLUMN IF NOT EXISTS ShardId INT64;
            EXCEPTION WHEN ERROR THEN
                -- Column already exists, continue
                SELECT 1;
            END;

            -- Calculate the ShardId
            UPDATE `{table_id}`
            SET ShardId = S2_CELLIDFROMPOINT(ST_GEOGPOINT(x, y), 15)
            WHERE TRUE;
        """
        print(f"Running ShardId update query for {table_id}...")
        client.query(setup_query).result()
        print("ShardId column ensured and values calculated.")

    # Check if we should trigger the contraction pipeline
    check_and_trigger_pipeline(client, table_name)

def check_and_trigger_pipeline(client, current_table_name):
    """
    Checks if both nodes and edges tables have been updated recently.
    Triggers the Dataflow pipeline if so.
    """
    nodes_table_id = f"{PROJECT_ID}.{DATASET_ID}.nodes"
    edges_table_id = f"{PROJECT_ID}.{DATASET_ID}.edges"

    try:
        nodes_table = client.get_table(nodes_table_id)
        edges_table = client.get_table(edges_table_id)
    except Exception as e:
        print(f"Error fetching table metadata: {e}")
        return

    t_nodes = nodes_table.modified
    t_edges = edges_table.modified
    
    # Use current table timestamp reference
    if current_table_name == "nodes":
        t_current = t_nodes
        t_other = t_edges
    else:
        t_current = t_edges
        t_other = t_nodes

    print(f"Nodes modified: {t_nodes}, Edges modified: {t_edges}")

    # Threshold for considering them "triggered together"
    # 30 seconds to prevent triggers from consecutive test runs
    threshold = timedelta(seconds=30)
    
    # Check if they are close in time
    time_diff = abs(t_nodes - t_edges)
    if time_diff > threshold:
        print(f"Time difference {time_diff} > {threshold}. Not triggering pipeline.")
        return

    # Logic to ensure only one specific invocation triggers it.    
    if t_current >= t_other:
        print("Triggering Contraction Pipeline...")
        trigger_pipeline()
    else:
        print(f"Current table ({current_table_name}) is older than other table. Waiting for other trigger (or it already happened).")

def trigger_pipeline():
    current_dir = pathlib.Path(__file__).parent.absolute()
    setup_file_path = str(current_dir / "setup.py")

    pipeline_args = [
        f"--project={PROJECT_ID}",
        f"--runner=DataflowRunner",
        f"--region={REGION}",
        f"--temp_location={TEMP_LOCATION}",
        f"--staging_location={STAGING_LOCATION}",
    ]
    
    create_pipeline(
        project=PROJECT_ID,
        temp_location=TEMP_LOCATION,
        input_nodes=f"{PROJECT_ID}:{DATASET_ID}.nodes",
        input_edges=f"{PROJECT_ID}:{DATASET_ID}.edges",
        instance=INSTANCE_ID,
        shortcuts_table=SHORTCUTS_TABLE,
        shards_table=SHARDS_TABLE,
        overlay_table=OVERLAY_TABLE,
        node_index_table=NODE_INDEX_TABLE,
        setup_file=setup_file_path,
        pipeline_args=pipeline_args
    )
    print("Pipeline triggered successfully.")
