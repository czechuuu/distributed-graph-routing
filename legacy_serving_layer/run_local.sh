#!/bin/bash
# Run the serving layer locally

# Ensure we are in the legacy_serving_layer directory or handle paths correctly
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

echo "Project root: $PROJECT_ROOT"

# Check if dependencies are installed
if python3 -c "import fastapi, uvicorn, google.cloud.bigtable, networkx, ujson" 2>/dev/null; then
    echo "Dependencies found."
else
    echo "Missing dependencies. Installing..."
    pip install fastapi uvicorn google-cloud-bigtable networkx ujson
fi

# Set default env vars if not set
export PROJECT_ID=${PROJECT_ID:-repetitive-shortest-paths}
export INSTANCE_ID=${INSTANCE_ID:-routing-instance}
export PORT=${PORT:-8001}

# Run the app from project root to ensure imports work
cd "$PROJECT_ROOT"
echo "Starting server at http://localhost:${PORT}"
python3 -m uvicorn legacy_serving_layer.app:app --reload --host 0.0.0.0 --port "${PORT}"
