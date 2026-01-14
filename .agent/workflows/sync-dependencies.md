---
description: How to keep setup.py and pyproject.toml dependencies in sync
---

# Syncing Dependencies

This project has two dependency files that must be kept in sync:
- `pyproject.toml` - Used by `uv` for local development
- `setup.py` - Used by Dataflow workers during job submission

## When to sync

Sync dependencies whenever you modify either file.

## How to sync

1. Open both `pyproject.toml` and `setup.py`
2. Ensure all packages in `pyproject.toml`'s `dependencies` array are also in `setup.py`'s `install_requires` list
3. Ensure version pins match exactly (e.g., `==2.70.0`, `<1.66.0`, `>=2.5`)
4. After modifying `pyproject.toml`, run:
// turbo
```bash
uv lock
```

## Key dependencies to watch

| Package | Purpose | Notes |
|---------|---------|-------|
| `apache-beam[gcp]` | Dataflow pipeline | Must be pinned to same version |
| `grpcio` | gRPC communication | Pin `<1.66.0` for Beam compatibility |
| `protobuf` | Serialization | Must match version used to generate `*_pb2.py` files |
| `pip` | Beam stager | Required in both for worker installation |
