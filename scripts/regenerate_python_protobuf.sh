#!/usr/bin/env bash
set -euo pipefail

# Run relative to this script (expects to live in `scripts/`).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Validate generator versions for reproducibility.
uv run python - <<'PY'
from __future__ import annotations

import sys

import google.protobuf

try:
    import importlib.metadata as md
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Failed to import importlib.metadata: {exc}") from exc

WANT_PROTOBUF = "5.26.1"
WANT_GRPC_TOOLS = "1.64.1"
WANT_GRPCIO = "1.64.1"

have_protobuf = getattr(google.protobuf, "__version__", "unknown")
have_grpc_tools = md.version("grpcio-tools")
have_grpcio = md.version("grpcio")

errors: list[str] = []
if have_protobuf != WANT_PROTOBUF:
    errors.append(f"protobuf=={WANT_PROTOBUF} required (have {have_protobuf})")
if have_grpc_tools != WANT_GRPC_TOOLS:
    errors.append(f"grpcio-tools=={WANT_GRPC_TOOLS} required (have {have_grpc_tools})")
if have_grpcio != WANT_GRPCIO:
    errors.append(f"grpcio=={WANT_GRPCIO} required (have {have_grpcio})")

if errors:
    raise SystemExit(
        "Protobuf generator environment mismatch:\n- " + "\n- ".join(errors) + "\n\n"
        "Fix by syncing scripts venv (from repo root):\n"
        "  cd scripts && uv sync\n"
    )

print("OK: generator versions match.")
PY

PROTOC=( uv run python -m grpc_tools.protoc -I ../protos )

# Canonical output location (single source of truth).
OUT_DIR="../shared/shared/protos"
mkdir -p "$OUT_DIR"

# gcs_storage.proto (used by preprocessing + serving)
"${PROTOC[@]}" --python_out="$OUT_DIR" \
              ../protos/gcs_storage.proto

# shard_worker.proto (gRPC service protos used by serving/worker)
"${PROTOC[@]}" --python_out="$OUT_DIR" \
              --grpc_python_out="$OUT_DIR" \
              ../protos/shard_worker.proto

# Fix grpc_tools generated imports to be package-relative.
# grpcio-tools 1.64.1 emits `import shard_worker_pb2 as ...` which won't work when
# importing as `shared.protos.shard_worker_pb2_grpc`.
uv run python - <<'PY'
from __future__ import annotations

from pathlib import Path

path = Path("../shared/shared/protos/shard_worker_pb2_grpc.py")
txt = path.read_text("utf-8")
txt2 = txt.replace(
    "import shard_worker_pb2 as shard__worker__pb2",
    "from . import shard_worker_pb2 as shard__worker__pb2",
)
if txt2 != txt:
    path.write_text(txt2, "utf-8")
PY
