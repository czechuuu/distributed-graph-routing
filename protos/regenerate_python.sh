#!/usr/bin/env bash
set -euo pipefail

# Regenerate all Python protobuf outputs in this repo from /protos/*.proto
# using EXACTLY:
#   Protobuf Python Version: 5.26.1
#
# This script uses uv to create an isolated environment under protos/.venv
# and runs grpc_tools.protoc with pinned dependencies.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found on PATH."
  echo "Install uv first (see https://docs.astral.sh/uv/) and re-run."
  exit 1
fi

# Keep uv caches inside the repo (helps in sandboxed environments and CI).
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$ROOT_DIR/.cache}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$XDG_CACHE_HOME/uv}"

VENV_DIR="$ROOT_DIR/protos/.venv"
PY="$VENV_DIR/bin/python"
DESIRED_PYTHON_VERSION="${DESIRED_PYTHON_VERSION:-3.11}"

if [[ -x "$PY" ]]; then
  current="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [[ "$current" != "$DESIRED_PYTHON_VERSION" ]]; then
    rm -rf "$VENV_DIR"
  fi
fi

if [[ ! -x "$PY" ]]; then
  uv venv "$VENV_DIR" --python "$DESIRED_PYTHON_VERSION"
fi

# Pin versions so generated headers say: Protobuf Python Version: 5.26.1
uv pip install --python "$PY" \
  "protobuf==5.26.1" \
  "grpcio==1.64.1" \
  "grpcio-tools==1.64.1"

PROTOC=( "$PY" -m grpc_tools.protoc -I protos )

# bigtable_storage.proto (Bigtable protos used by legacy pipelines + legacy serving/data-domain)
"${PROTOC[@]}" --python_out=legacy_serving_layer/storage_types \
              --grpc_python_out=legacy_serving_layer/storage_types \
              protos/bigtable_storage.proto
"${PROTOC[@]}" --python_out=legacy_data_domain/storage_types \
              --grpc_python_out=legacy_data_domain/storage_types \
              protos/bigtable_storage.proto
"${PROTOC[@]}" --python_out=legacy_preprocessing/storage_types \
              protos/bigtable_storage.proto
"${PROTOC[@]}" --python_out=scripts/storage_types \
              protos/bigtable_storage.proto

# gcs_storage.proto (GCS protos used by preprocessing + serving)
"${PROTOC[@]}" --python_out=preprocessing/dataflow/storage_types \
              protos/gcs_storage.proto
"${PROTOC[@]}" --python_out=scripts/storage_types \
              protos/gcs_storage.proto
"${PROTOC[@]}" --python_out=serving/serving/storage_types \
              protos/gcs_storage.proto

# shard_worker.proto (gRPC service protos used by serving/worker)
"${PROTOC[@]}" --python_out=serving/serving/protos \
              --grpc_python_out=serving/serving/protos \
              protos/shard_worker.proto

# Verify headers are exactly Protobuf Python Version: 5.26.1
"$PY" - <<'PY'
from __future__ import annotations

from pathlib import Path

root = Path.cwd()
expected = "# Protobuf Python Version: 5.26.1"

pb2_targets = [
    root / "legacy_serving_layer/storage_types/bigtable_storage_pb2.py",
    root / "legacy_data_domain/storage_types/bigtable_storage_pb2.py",
    root / "legacy_preprocessing/storage_types/bigtable_storage_pb2.py",
    root / "scripts/storage_types/bigtable_storage_pb2.py",
    root / "preprocessing/dataflow/storage_types/gcs_storage_pb2.py",
    root / "scripts/storage_types/gcs_storage_pb2.py",
    root / "serving/serving/storage_types/gcs_storage_pb2.py",
    root / "serving/serving/protos/shard_worker_pb2.py",
]

grpc_targets = [
    root / "legacy_serving_layer/storage_types/bigtable_storage_pb2_grpc.py",
    root / "legacy_data_domain/storage_types/bigtable_storage_pb2_grpc.py",
    root / "serving/serving/protos/shard_worker_pb2_grpc.py",
]

bad: list[Path] = []
missing: list[Path] = []

for p in pb2_targets:
    if not p.exists():
        missing.append(p)
        continue
    txt = p.read_text("utf-8", errors="replace")
    if expected not in txt:
        bad.append(p)

for p in grpc_targets:
    if not p.exists():
        missing.append(p)

if missing:
    raise SystemExit("Missing expected generated files:\n- " + "\n- ".join(str(p) for p in missing))
if bad:
    raise SystemExit(
        "Some generated files do not contain the expected header "
        f"({expected!r}):\n- " + "\n- ".join(str(p) for p in bad)
    )

print("OK: regenerated protos with Protobuf Python Version: 5.26.1")
PY

