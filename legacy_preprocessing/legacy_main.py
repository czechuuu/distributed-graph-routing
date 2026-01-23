import argparse
import logging
import os

from legacy_pipeline import create_legacy_pipeline


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--temp_location", required=True, help="GCS temp location")
    parser.add_argument(
        "--input_base",
        default="gs://rsp_graph_data/processed",
        help="Base GCS path for stage-1 outputs",
    )
    parser.add_argument("--instance_id", required=True, help="Bigtable instance ID")
    parser.add_argument("--setup_file", required=True, help="Setup.py path")
    parser.add_argument("--shards_table", default="shards", help="Bigtable table for shards")
    parser.add_argument(
        "--shortcuts_table", default="shortcuts", help="Bigtable table for shortcuts"
    )
    parser.add_argument(
        "--node_index_table", default="node_index", help="Bigtable table for node index"
    )
    parser.add_argument(
        "--overlay_graph_table",
        default="overlay_graph",
        help="Bigtable table for overlay graph",
    )
    parser.add_argument("--column_family", default="cf", help="Bigtable column family")
    parser.add_argument(
        "--qualifier",
        default="data",
        help="Bigtable column qualifier",
    )

    known_args, pipeline_args = parser.parse_known_args(argv)
    logging.getLogger().setLevel(logging.INFO)

    setup_file = os.path.abspath(known_args.setup_file)
    create_legacy_pipeline(
        project=known_args.project,
        temp_location=known_args.temp_location,
        input_base=known_args.input_base,
        instance_id=known_args.instance_id,
        setup_file=setup_file,
        pipeline_args=pipeline_args,
        shards_table=known_args.shards_table,
        shortcuts_table=known_args.shortcuts_table,
        node_index_table=known_args.node_index_table,
        overlay_graph_table=known_args.overlay_graph_table,
        column_family=known_args.column_family,
        qualifier=known_args.qualifier,
    )


if __name__ == "__main__":
    run()
