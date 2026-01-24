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

# Canonical output location (single source of truth).
OUT_DIR="shared/shared/protos"
mkdir -p "$OUT_DIR"

# gcs_storage.proto (used by preprocessing + serving)
"${PROTOC[@]}" --python_out="$OUT_DIR" \
              protos/gcs_storage.proto

# shard_worker.proto (gRPC service protos used by serving/worker)
"${PROTOC[@]}" --python_out="$OUT_DIR" \
              --grpc_python_out="$OUT_DIR" \
              protos/shard_worker.proto

# Fix grpc_tools generated imports to be package-relative.
# grpcio-tools 1.64.1 emits `import shard_worker_pb2 as ...` which won't work when
# importing as `shared.protos.shard_worker_pb2_grpc`.
"$PY" - <<'PY'
from __future__ import annotations

from pathlib import Path

path = Path("shared/shared/protos/shard_worker_pb2_grpc.py")
txt = path.read_text("utf-8")
txt2 = txt.replace(
    "import shard_worker_pb2 as shard__worker__pb2",
    "from . import shard_worker_pb2 as shard__worker__pb2",
)
if txt2 != txt:
    path.write_text(txt2, "utf-8")
PY

# Verify headers are exactly Protobuf Python Version: 5.26.1
"$PY" - <<'PY'
from __future__ import annotations

from pathlib import Path

root = Path.cwd()
expected = "# Protobuf Python Version: 5.26.1"

pb2_targets = [
    root / "shared/shared/protos/gcs_storage_pb2.py",
    root / "shared/shared/protos/shard_worker_pb2.py",
]

grpc_targets = [
    root / "shared/shared/protos/shard_worker_pb2_grpc.py",
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

