#!/bin/bash
set -e

# Get the repository root directory
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

echo "Regenerating protobuf files..."

# Define the destination directories
DESTINATIONS=(
    "data_domain"
    "preprocessing"
    "serving_layer"
)

# Loop through each destination and generate the protobuf files
for dest in "${DESTINATIONS[@]}"; do
    OUTPUT_DIR="${dest}/storage_types"
    echo "Generating protos for ${OUTPUT_DIR}..."

    # Ensure the directory exists
    mkdir -p "${OUTPUT_DIR}"

    # Use uv to run the grpc_tools.protoc command
    # We include grpcio-tools for the compiler and protobuf for runtime support during generation if needed
    # Pinning grpcio-tools to 1.63.0 to align with Protobuf 5.x support and libprotoc version
    uv run --python 3.11 --with "grpcio-tools==1.63.0" --with "protobuf==5.26.1" python -m grpc_tools.protoc \
        -I protos \
        --python_out="${OUTPUT_DIR}" \
        --grpc_python_out="${OUTPUT_DIR}" \
        protos/*.proto

    # Ensure __init__.py exists to make it a package
    if [ ! -f "${OUTPUT_DIR}/__init__.py" ]; then
        touch "${OUTPUT_DIR}/__init__.py"
    fi
done

echo "Protobuf regeneration complete."
