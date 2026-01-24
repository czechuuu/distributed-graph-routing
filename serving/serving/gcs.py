from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from google.cloud import storage


@dataclass(frozen=True)
class GcsPath:
    bucket: str
    blob: str


def download_bytes(bucket: str, blob: str) -> bytes:
    client = storage.Client()
    bucket_ref = client.bucket(bucket)
    blob_ref = bucket_ref.blob(blob)
    return blob_ref.download_as_bytes()


def download_overlay(bucket: str, prefix: str) -> bytes:
    return download_bytes(bucket, f"{prefix}/overlay_graph.pb")


def download_shard(bucket: str, prefix: str, shard_id: int) -> bytes:
    return download_bytes(bucket, f"{prefix}/shard_id={shard_id}/shard_graph.pb")
