from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True)
class GcsConfig:
    bucket: str
    prefix: str


@dataclass(frozen=True)
class RoutingApiConfig:
    host: str
    port: int
    worker_service_host: str
    worker_service_port: int
    worker_refresh_seconds: int
    gcs: GcsConfig


@dataclass(frozen=True)
class ShardWorkerConfig:
    host: str
    port: int
    health_port: int
    max_cached_shards: int
    gcs: GcsConfig


def load_routing_api_config() -> RoutingApiConfig:
    bucket = _env("GCS_BUCKET", "")
    prefix = _env("GCS_PREFIX", "protos").strip("/")
    return RoutingApiConfig(
        host=_env("ROUTING_API_HOST", "0.0.0.0"),
        port=_env_int("ROUTING_API_PORT", 8080),
        worker_service_host=_env("WORKER_SERVICE_HOST", "shard-worker.default.svc.cluster.local"),
        worker_service_port=_env_int("WORKER_SERVICE_PORT", 50051),
        worker_refresh_seconds=_env_int("WORKER_REFRESH_SECONDS", 15),
        gcs=GcsConfig(bucket=bucket, prefix=prefix),
    )


def load_shard_worker_config() -> ShardWorkerConfig:
    bucket = _env("GCS_BUCKET", "")
    prefix = _env("GCS_PREFIX", "protos").strip("/")
    return ShardWorkerConfig(
        host=_env("SHARD_WORKER_HOST", "0.0.0.0"),
        port=_env_int("SHARD_WORKER_PORT", 50051),
        health_port=_env_int("SHARD_WORKER_HEALTH_PORT", 8081),
        max_cached_shards=_env_int("MAX_CACHED_SHARDS", 64),
        gcs=GcsConfig(bucket=bucket, prefix=prefix),
    )
