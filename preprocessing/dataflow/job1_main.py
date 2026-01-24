import argparse
import logging
import os

from .job1_pipeline import create_job1_pipeline


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--temp_location", required=True, help="GCS temp location")
    parser.add_argument(
        "--input_nodes",
        default="gs://rsp_graph_data/raw/nodes/*",
        help="GCS path pattern for nodes parquet",
    )
    parser.add_argument(
        "--input_edges",
        default="gs://rsp_graph_data/raw/edges/*",
        help="GCS path pattern for edges parquet",
    )
    parser.add_argument(
        "--output_base",
        default="gs://rsp_graph_data/processed",
        help="Base GCS path for outputs",
    )
    parser.add_argument("--setup_file", required=True, help="Setup.py path")

    known_args, pipeline_args = parser.parse_known_args(argv)
    logging.getLogger().setLevel(logging.INFO)

    setup_file = os.path.abspath(known_args.setup_file)
    create_job1_pipeline(
        project=known_args.project,
        temp_location=known_args.temp_location,
        input_nodes=known_args.input_nodes,
        input_edges=known_args.input_edges,
        output_base=known_args.output_base,
        setup_file=setup_file,
        pipeline_args=pipeline_args,
    )


if __name__ == "__main__":
    run()
