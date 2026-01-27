"""Reporter for load test results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .load_metrics import LoadTestCollector, LoadTestSummary


class LoadTestReporter:
    """Reports load test results to console and files."""

    def __init__(self, output_dir: Path, base_url: str):
        """Initialize the reporter."""
        self.output_dir = output_dir
        self.base_url = base_url
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def report(self, collector: LoadTestCollector, summary: LoadTestSummary) -> None:
        """Generate all reports."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._print_console_report(summary)
        self._write_summary_tsv(summary)
        self._write_timeline_tsv(collector)

    def _print_console_report(self, summary: LoadTestSummary) -> None:
        """Print formatted report to console."""
        print("\n" + "=" * 70)
        print("LOAD TEST RESULTS")
        print("=" * 70)
        print(f"URL: {self.base_url}")
        print(f"Time: {datetime.now().isoformat()}")
        print(f"Test Case: {summary.test_case}")
        print("=" * 70)

        print(f"\n{'Configuration':-^50}")
        print(f"  Concurrency:      {summary.concurrency}")
        print(f"  Total Requests:   {summary.total_requests}")

        print(f"\n{'Results':-^50}")
        print(f"  Duration:         {summary.duration_seconds:.2f}s")
        print(f"  Successful:       {summary.successful}")
        print(f"  Failed:           {summary.failed}")
        print(f"  Error Rate:       {summary.error_rate * 100:.1f}%")
        print(f"  Throughput:       {summary.throughput_rps:.2f} req/s")

        print(f"\n{'Latency (successful requests)':-^50}")
        print(f"  Mean:             {summary.latency_mean_ms:.1f}ms")
        print(f"  Std Dev:          {summary.latency_std_ms:.1f}ms")
        print(f"  Min:              {summary.latency_min_ms:.1f}ms")
        print(f"  Max:              {summary.latency_max_ms:.1f}ms")
        print(f"  p50 (median):     {summary.latency_p50_ms:.1f}ms")
        print(f"  p95:              {summary.latency_p95_ms:.1f}ms")
        print(f"  p99:              {summary.latency_p99_ms:.1f}ms")

        print("\n" + "=" * 70)

    def _write_summary_tsv(self, summary: LoadTestSummary) -> None:
        """Write summary to TSV file."""
        filepath = self.output_dir / f"load_test_summary_{self.timestamp}.tsv"

        with open(filepath, "w") as f:
            f.write(f"# Load Test Summary - {datetime.now().isoformat()}\n")
            f.write(f"# URL: {self.base_url}\n")
            f.write("#\n")

            headers = [
                "TEST_CASE", "CONCURRENCY", "TOTAL_REQS", "SUCCESSFUL", "FAILED",
                "DURATION_S", "THROUGHPUT_RPS", "ERROR_RATE",
                "MEAN_MS", "STD_MS", "MIN_MS", "MAX_MS", "P50_MS", "P95_MS", "P99_MS"
            ]
            f.write("\t".join(headers) + "\n")

            row = [
                summary.test_case,
                str(summary.concurrency),
                str(summary.total_requests),
                str(summary.successful),
                str(summary.failed),
                f"{summary.duration_seconds:.2f}",
                f"{summary.throughput_rps:.2f}",
                f"{summary.error_rate:.4f}",
                f"{summary.latency_mean_ms:.2f}",
                f"{summary.latency_std_ms:.2f}",
                f"{summary.latency_min_ms:.2f}",
                f"{summary.latency_max_ms:.2f}",
                f"{summary.latency_p50_ms:.2f}",
                f"{summary.latency_p95_ms:.2f}",
                f"{summary.latency_p99_ms:.2f}",
            ]
            f.write("\t".join(row) + "\n")

        print(f"\nSummary written to: {filepath}")

    def _write_timeline_tsv(self, collector: LoadTestCollector) -> None:
        """Write timeline data to TSV file (for graphing)."""
        filepath = self.output_dir / f"load_test_timeline_{self.timestamp}.tsv"
        timeline = collector.get_timeline_data()

        with open(filepath, "w") as f:
            f.write(f"# Load Test Timeline - {datetime.now().isoformat()}\n")
            f.write(f"# URL: {self.base_url}\n")
            f.write("#\n")

            headers = ["REQUEST_ID", "START_TIME", "LATENCY_MS", "SUCCESS", "ERROR"]
            f.write("\t".join(headers) + "\n")

            for entry in timeline:
                row = [
                    str(entry["request_id"]),
                    f"{entry['start_time']:.6f}",
                    f"{entry['latency_ms']:.2f}",
                    str(entry["success"]),
                    entry["error"] or "",
                ]
                f.write("\t".join(row) + "\n")

        print(f"Timeline written to: {filepath}")
