from graph_manager import trigger_pipeline

if __name__ == "__main__":
    # Run this locally to trigger the pipeline if the cloud run trigger acts up.
    # The pipeline will run on Dataflow.
    trigger_pipeline(run_locally=True)