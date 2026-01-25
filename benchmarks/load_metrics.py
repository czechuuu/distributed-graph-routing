"""Metrics and data structures for load testing."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LoadTestResult:
    """Result from a single request during load testing."""

    request_id: int
    start_time: float  # Unix timestamp when request started
    latency_ms: float
    success: bool
    path_found: bool
    error: Optional[str] = None


@dataclass
class LoadTestSummary:
    """Aggregated statistics from a load test run."""

    test_case: str
    concurrency: int
    total_requests: int
    successful: int
    failed: int
    duration_seconds: float
    throughput_rps: float  # requests per second
    latency_mean_ms: float
    latency_std_ms: float
    latency_min_ms: float
    latency_max_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    error_rate: float

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "test_case": self.test_case,
            "concurrency": self.concurrency,
            "total_requests": self.total_requests,
            "successful": self.successful,
            "failed": self.failed,
            "duration_seconds": round(self.duration_seconds, 2),
            "throughput_rps": round(self.throughput_rps, 2),
            "latency_mean_ms": round(self.latency_mean_ms, 2),
            "latency_std_ms": round(self.latency_std_ms, 2),
            "latency_min_ms": round(self.latency_min_ms, 2),
            "latency_max_ms": round(self.latency_max_ms, 2),
            "latency_p50_ms": round(self.latency_p50_ms, 2),
            "latency_p95_ms": round(self.latency_p95_ms, 2),
            "latency_p99_ms": round(self.latency_p99_ms, 2),
            "error_rate": round(self.error_rate, 4),
        }


@dataclass
class LoadTestCollector:
    """Collects results from load testing."""

    results: List[LoadTestResult] = field(default_factory=list)
    test_start_time: float = 0.0
    test_end_time: float = 0.0

    def add_result(self, result: LoadTestResult) -> None:
        """Add a result to the collection."""
        self.results.append(result)

    def compute_summary(self, test_case: str, concurrency: int) -> LoadTestSummary:
        """Compute summary statistics from collected results."""
        successful_results = [r for r in self.results if r.success]
        failed_results = [r for r in self.results if not r.success]

        latencies = [r.latency_ms for r in successful_results]
        duration = self.test_end_time - self.test_start_time if self.test_end_time > self.test_start_time else 1.0

        if latencies:
            sorted_latencies = sorted(latencies)
            n = len(sorted_latencies)

            def percentile(p: float) -> float:
                idx = int(n * p)
                return sorted_latencies[min(idx, n - 1)]

            return LoadTestSummary(
                test_case=test_case,
                concurrency=concurrency,
                total_requests=len(self.results),
                successful=len(successful_results),
                failed=len(failed_results),
                duration_seconds=duration,
                throughput_rps=len(self.results) / duration,
                latency_mean_ms=statistics.mean(latencies),
                latency_std_ms=statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
                latency_min_ms=min(latencies),
                latency_max_ms=max(latencies),
                latency_p50_ms=percentile(0.50),
                latency_p95_ms=percentile(0.95),
                latency_p99_ms=percentile(0.99),
                error_rate=len(failed_results) / len(self.results) if self.results else 0.0,
            )
        else:
            # All requests failed
            return LoadTestSummary(
                test_case=test_case,
                concurrency=concurrency,
                total_requests=len(self.results),
                successful=0,
                failed=len(failed_results),
                duration_seconds=duration,
                throughput_rps=len(self.results) / duration,
                latency_mean_ms=0.0,
                latency_std_ms=0.0,
                latency_min_ms=0.0,
                latency_max_ms=0.0,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                latency_p99_ms=0.0,
                error_rate=1.0,
            )

    def get_timeline_data(self) -> List[dict]:
        """Get timeline data for graphing."""
        return [
            {
                "request_id": r.request_id,
                "start_time": r.start_time,
                "latency_ms": round(r.latency_ms, 2),
                "success": r.success,
                "error": r.error,
            }
            for r in sorted(self.results, key=lambda x: x.start_time)
        ]
