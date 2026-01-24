import argparse
import logging
import os

from .job2_pipeline import create_job2_pipeline


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--temp_location", required=True, help="GCS temp location")
    parser.add_argument(
        "--input_base",
        default="gs://rsp_graph_data/processed",
        help="Base GCS path for stage-1 outputs",
    )
    parser.add_argument(
        "--output_base",
        default="gs://rsp_graph_data/protos",
        help="Base GCS path for protobuf outputs",
    )
    parser.add_argument("--setup_file", required=True, help="Setup.py path")

    known_args, pipeline_args = parser.parse_known_args(argv)
    logging.getLogger().setLevel(logging.INFO)

    setup_file = os.path.abspath(known_args.setup_file)
    create_job2_pipeline(
        project=known_args.project,
        temp_location=known_args.temp_location,
        input_base=known_args.input_base,
        output_base=known_args.output_base,
        setup_file=setup_file,
        pipeline_args=pipeline_args,
    )


if __name__ == "__main__":
    run()
