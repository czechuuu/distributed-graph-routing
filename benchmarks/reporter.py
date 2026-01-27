"""Reporter for benchmark results - console and file output."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from .metrics import AggregatedStats, MetricsCollector


class BenchmarkReporter:
    """Reports benchmark results to console and files."""

    CATEGORY_DISPLAY = {
        "small_town": "Small Town (Same Shard)",
        "large_city": "Large City (Same Shard)",
        "cross_shard": "Cross-Shard Routes",
    }

    def __init__(self, output_dir: Path, base_url: str, runs_per_test: int):
        """
        Initialize the reporter.

        Args:
            output_dir: Directory to write output files
            base_url: The API URL being tested
            runs_per_test: Number of runs per test case
        """
        self.output_dir = output_dir
        self.base_url = base_url
        self.runs_per_test = runs_per_test
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def report(self, collector: MetricsCollector) -> None:
        """Generate all reports."""
        stats = collector.compute_stats()

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate reports
        self._print_console_report(stats)
        self._write_tsv_summary(stats)
        self._write_tsv_raw(collector)

    def _print_console_report(self, stats: List[AggregatedStats]) -> None:
        """Print a formatted report to console."""
        print("\n" + "=" * 80)
        print("BENCHMARK RESULTS")
        print("=" * 80)
        print(f"URL: {self.base_url}")
        print(f"Time: {datetime.now().isoformat()}")
        print(f"Runs per test: {self.runs_per_test}")
        print("=" * 80)

        # Group by category
        categories = sorted(set(s.category for s in stats))

        for category in categories:
            cat_stats = [s for s in stats if s.category == category]
            cat_display = self.CATEGORY_DISPLAY.get(category, category)

            print(f"\n{cat_display}")
            print("-" * 60)

            # Header
            print(f"{'Test Case':<20} {'Type':<8} {'Mean':<10} {'Std':<10} {'Min':<10} {'Max':<10}")
            print("-" * 60)

            # Sort by test case, then query type (first before cached)
            cat_stats.sort(key=lambda x: (x.test_case, 0 if x.query_type == "first" else 1))

            for s in cat_stats:
                if s.success_count == 0:
                    print(f"{s.test_case:<20} {s.query_type:<8} {'FAILED':<10}")
                else:
                    print(
                        f"{s.test_case:<20} {s.query_type:<8} "
                        f"{s.mean_ms:>7.1f}ms {s.std_ms:>7.1f}ms "
                        f"{s.min_ms:>7.1f}ms {s.max_ms:>7.1f}ms"
                    )

        # Summary comparison
        print("\n" + "=" * 80)
        print("CACHING EFFECT SUMMARY")
        print("-" * 60)

        for category in categories:
            cat_stats = [s for s in stats if s.category == category]
            first_stats = {s.test_case: s for s in cat_stats if s.query_type == "first"}
            cached_stats = {s.test_case: s for s in cat_stats if s.query_type == "cached"}

            cat_display = self.CATEGORY_DISPLAY.get(category, category)
            print(f"\n{cat_display}:")

            for test_case in first_stats:
                first = first_stats[test_case]
                cached = cached_stats.get(test_case)

                if first.success_count > 0 and cached and cached.success_count > 0:
                    speedup = first.mean_ms / cached.mean_ms if cached.mean_ms > 0 else 0
                    reduction = ((first.mean_ms - cached.mean_ms) / first.mean_ms * 100) if first.mean_ms > 0 else 0
                    print(f"  {test_case}: {speedup:.1f}x speedup ({reduction:.0f}% reduction)")
                else:
                    print(f"  {test_case}: Unable to compute (failed queries)")

        print("\n" + "=" * 80)

    def _write_tsv_summary(self, stats: List[AggregatedStats]) -> None:
        """Write summary statistics to a TSV file."""
        filepath = self.output_dir / f"benchmark_summary_{self.timestamp}.tsv"

        with open(filepath, "w") as f:
            # Header comments
            f.write(f"# Benchmark Summary Results - {datetime.now().isoformat()}\n")
            f.write(f"# URL: {self.base_url}\n")
            f.write(f"# Runs per test: {self.runs_per_test}\n")
            f.write("#\n")

            # TSV header
            headers = [
                "CATEGORY",
                "TEST_NAME",
                "QUERY_TYPE",
                "COUNT",
                "SUCCESS",
                "MEAN_MS",
                "STD_MS",
                "MIN_MS",
                "MAX_MS",
                "MEDIAN_MS",
                "P95_MS",
                "AVG_DIST_M",
            ]
            f.write("\t".join(headers) + "\n")

            # Data rows
            for s in sorted(stats, key=lambda x: (x.category, x.test_case, x.query_type)):
                row = [
                    s.category,
                    s.test_case,
                    s.query_type,
                    str(s.count),
                    str(s.success_count),
                    f"{s.mean_ms:.2f}",
                    f"{s.std_ms:.2f}",
                    f"{s.min_ms:.2f}",
                    f"{s.max_ms:.2f}",
                    f"{s.median_ms:.2f}",
                    f"{s.p95_ms:.2f}",
                    f"{s.avg_distance_m:.2f}",
                ]
                f.write("\t".join(row) + "\n")

        print(f"\nSummary written to: {filepath}")

    def _write_tsv_raw(self, collector: MetricsCollector) -> None:
        """Write raw results to a TSV file."""
        filepath = self.output_dir / f"benchmark_raw_{self.timestamp}.tsv"
        raw_results = collector.get_raw_results()

        with open(filepath, "w") as f:
            # Header comments
            f.write(f"# Benchmark Raw Results - {datetime.now().isoformat()}\n")
            f.write(f"# URL: {self.base_url}\n")
            f.write(f"# Runs per test: {self.runs_per_test}\n")
            f.write("#\n")

            # TSV header
            headers = [
                "CATEGORY",
                "TEST_NAME",
                "QUERY_TYPE",
                "RUN",
                "LATENCY_MS",
                "SUCCESS",
                "PATH_FOUND",
                "DISTANCE_M",
                "SEGMENTS",
                "ERROR",
            ]
            f.write("\t".join(headers) + "\n")

            # Data rows
            for r in raw_results:
                row = [
                    r["category"],
                    r["test_case"],
                    r["query_type"],
                    str(r["run_number"]),
                    f"{r['latency_ms']:.2f}",
                    str(r["success"]),
                    str(r["path_found"]),
                    f"{r['distance_m']:.2f}",
                    str(r["segments_count"]),
                    r["error"] or "",
                ]
                f.write("\t".join(row) + "\n")

        print(f"Raw data written to: {filepath}")
