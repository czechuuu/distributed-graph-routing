"""Metrics collection and statistics computation for benchmarks."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class QueryResult:
    """Result from a single query execution."""

    test_case: str
    category: str
    query_type: str  # "first" | "cached"
    run_number: int
    latency_ms: float
    success: bool
    path_found: bool
    distance_m: float
    segments_count: int
    error: Optional[str] = None


@dataclass
class AggregatedStats:
    """Aggregated statistics for a group of query results."""

    category: str
    test_case: str
    query_type: str
    count: int
    success_count: int
    mean_ms: float
    std_ms: float
    min_ms: float
    max_ms: float
    median_ms: float
    p95_ms: float
    avg_distance_m: float

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "category": self.category,
            "test_case": self.test_case,
            "query_type": self.query_type,
            "count": self.count,
            "success_count": self.success_count,
            "mean_ms": round(self.mean_ms, 2),
            "std_ms": round(self.std_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "median_ms": round(self.median_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "avg_distance_m": round(self.avg_distance_m, 2),
        }


@dataclass
class MetricsCollector:
    """Collects and computes statistics from benchmark results."""

    results: List[QueryResult] = field(default_factory=list)

    def add_result(self, result: QueryResult) -> None:
        """Add a query result to the collection."""
        self.results.append(result)

    def compute_stats(self) -> List[AggregatedStats]:
        """Compute aggregated statistics grouped by category, test_case, and query_type."""
        # Group results
        groups: Dict[tuple, List[QueryResult]] = {}
        for r in self.results:
            key = (r.category, r.test_case, r.query_type)
            if key not in groups:
                groups[key] = []
            groups[key].append(r)

        stats_list = []
        for (category, test_case, query_type), group_results in sorted(groups.items()):
            # Only consider successful queries for latency stats
            successful = [r for r in group_results if r.success]
            latencies = [r.latency_ms for r in successful]
            distances = [r.distance_m for r in successful if r.path_found]

            if latencies:
                sorted_latencies = sorted(latencies)
                p95_idx = int(len(sorted_latencies) * 0.95)
                p95_idx = min(p95_idx, len(sorted_latencies) - 1)

                stats = AggregatedStats(
                    category=category,
                    test_case=test_case,
                    query_type=query_type,
                    count=len(group_results),
                    success_count=len(successful),
                    mean_ms=statistics.mean(latencies),
                    std_ms=statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
                    min_ms=min(latencies),
                    max_ms=max(latencies),
                    median_ms=statistics.median(latencies),
                    p95_ms=sorted_latencies[p95_idx],
                    avg_distance_m=statistics.mean(distances) if distances else 0.0,
                )
            else:
                # All queries failed
                stats = AggregatedStats(
                    category=category,
                    test_case=test_case,
                    query_type=query_type,
                    count=len(group_results),
                    success_count=0,
                    mean_ms=0.0,
                    std_ms=0.0,
                    min_ms=0.0,
                    max_ms=0.0,
                    median_ms=0.0,
                    p95_ms=0.0,
                    avg_distance_m=0.0,
                )
            stats_list.append(stats)

        return stats_list

    def get_raw_results(self) -> List[Dict]:
        """Get all raw results as dictionaries."""
        return [
            {
                "test_case": r.test_case,
                "category": r.category,
                "query_type": r.query_type,
                "run_number": r.run_number,
                "latency_ms": round(r.latency_ms, 2),
                "success": r.success,
                "path_found": r.path_found,
                "distance_m": round(r.distance_m, 2),
                "segments_count": r.segments_count,
                "error": r.error,
            }
            for r in self.results
        ]

    def get_summary_by_category(self) -> Dict[str, Dict]:
        """Get summary statistics grouped by category."""
        stats = self.compute_stats()
        summary: Dict[str, Dict] = {}

        for s in stats:
            if s.category not in summary:
                summary[s.category] = {"first": [], "cached": []}
            summary[s.category][s.query_type].append(s.to_dict())

        return summary
