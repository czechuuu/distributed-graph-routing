import functions_framework
import logging
from datetime import datetime, timedelta, timezone
from google.cloud import bigquery
from contractions.pipeline import create_pipeline

PROJECT_ID = "repetitive-shortest-paths"
DATASET_ID = "graph_data"
# Constants for Dataflow
TEMP_LOCATION = "gs://repetitive_shortest_paths_contractions_dataflow/temp"
STAGING_LOCATION = "gs://repetitive_shortest_paths_contractions_dataflow/staging"
INSTANCE_ID = "routing-instance"
SHORTCUTS_TABLE = "shortcuts"
INTRA_TABLE = "intra_edges"
REGION = "us-central1"

@functions_framework.cloud_event
def process_graph_upload(cloud_event):
    data = cloud_event.data
    bucket = data["bucket"]
    file_name = data["name"]
    uri = f"gs://{bucket}/{file_name}"
    
    client = bigquery.Client(project=PROJECT_ID)

    # 1. Define schemas based ONLY on what is in the CSV
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
    if "nodes" in file_name:
        table_name = "nodes"
        table_id = f"{PROJECT_ID}.{DATASET_ID}.nodes"
        schema = node_csv_schema
    elif "edges" in file_name:
        table_name = "edges"
        table_id = f"{PROJECT_ID}.{DATASET_ID}.edges"
        schema = edge_schema
    else:
        print(f"Unknown file type: {file_name}")
        return

    # 2. Load the CSV data
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

    # 3. Add and Update ShardId for the nodes table
    if "nodes" in file_name:
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

    # 4. Check if we should trigger the contraction pipeline
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
    threshold = timedelta(minutes=10)
    
    # 1. Check if they are close in time
    time_diff = abs(t_nodes - t_edges)
    if time_diff > threshold:
        print(f"Time difference {time_diff} > {threshold}. Not triggering pipeline.")
        return

    # 2. Logic to ensure only one specific invocation triggers it.
    # We trigger if:
    # - This table was modified AFTER the other table
    # - OR This table was modified AT THE SAME TIME (unlikely) and we use a tie-breaker (e.g. prioritize edges)
    #
    # Actually, simpler:
    # If t_current >= t_other, we are the "last" one (or tied), so we trigger.
    # The previous one would have seen t_prev < t_current (because t_current wasn't updated yet or was old).
    #
    # Wait, if t_current (new) is compared to t_other (new), and t_current >= t_other:
    #   We trigger.
    # The other execution (which updated t_other) checked t_current (old).
    #   Old t_current << t_other (new).
    #   Diff was huge. It returned early. 
    #   So checking diff first handles the "I'm the first one" case effectively.
    
    # So if we passed the diff check, it means BOTH are new.
    # So we just need to decide who triggers.
    # trigger if t_current >= t_other
    
    if t_current >= t_other:
        print("Triggering Contraction Pipeline...")
        trigger_pipeline()
    else:
        print(f"Current table ({current_table_name}) is older than other table. Waiting for other trigger (or it already happened).")

def trigger_pipeline():
    pipeline_args = [
        f"--project={PROJECT_ID}",
        f"--runner=DataflowRunner",
        f"--region={REGION}",
        f"--temp_location={TEMP_LOCATION}",
        f"--staging_location={STAGING_LOCATION}",
        f"--setup_file=./setup.py",
        # Optimization: use pre-built SDK container if possible, 
        # but setup.py should handle dependencies.
    ]
    
    # Input/Output arguments
    # Note: contractions/main.py uses argparse which we can bypass or simulate.
    # But contractions/main.py calls create_pipeline directly.
    # We will call create_pipeline directly.
    
    create_pipeline(
        project=PROJECT_ID,
        temp_location=TEMP_LOCATION,
        input_nodes=f"{PROJECT_ID}:{DATASET_ID}.nodes",
        input_edges=f"{PROJECT_ID}:{DATASET_ID}.edges",
        instance=INSTANCE_ID,
        shortcuts_table=SHORTCUTS_TABLE,
        intra_table=INTRA_TABLE,
        pipeline_args=pipeline_args
    )
    print("Pipeline triggered successfully.")