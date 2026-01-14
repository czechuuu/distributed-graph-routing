
import argparse
import logging
from preprocessing.dataflow.pipeline import create_pipeline

def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True, help='GCP Project ID')
    parser.add_argument('--temp_location', required=True, help='GCS Temp Location')
    parser.add_argument('--input_nodes_table', required=True, help='BigQuery table for nodes')
    parser.add_argument('--input_edges_table', required=True, help='BigQuery table for edges')
    parser.add_argument('--bt_instance', required=True, help='BigTable Instance ID')
    parser.add_argument('--shortcuts_table', required=True, help='BigTable table for shortcuts')
    parser.add_argument('--shards_table', required=True, help='BigTable table for shards (intra-shard edges)')
    parser.add_argument('--overlay_table', required=True, help='BigTable table for overlay graph')
    
    known_args, pipeline_args = parser.parse_known_args(argv)
    
    logging.getLogger().setLevel(logging.INFO)
    
    create_pipeline(
        project=known_args.project,
        temp_location=known_args.temp_location,
        input_nodes=known_args.input_nodes_table,
        input_edges=known_args.input_edges_table,
        instance=known_args.bt_instance,
        shortcuts_table=known_args.shortcuts_table,
        shards_table=known_args.shards_table,
        overlay_table=known_args.overlay_table,
        pipeline_args=pipeline_args
    )

if __name__ == '__main__':
    run()
