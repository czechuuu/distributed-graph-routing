#!/usr/bin/env python3
"""
Benchmark runner for the distributed graph routing API.

This script runs a series of benchmark tests against the routing API,
measuring latency for first and cached queries across different categories:
- Small towns (same-shard, small data)
- Large cities (same-shard, large data)
- Cross-shard routes

Usage:
    python run_benchmark.py --url http://localhost --port 8080
    python run_benchmark.py --url http://35.x.x.x --port 80 --runs 5

The results are printed to console and saved to TSV files for later analysis.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .client import RoutingClient
from .config import BenchmarkConfig
from .metrics import MetricsCollector, QueryResult
from .reporter import BenchmarkReporter


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Benchmark the distributed graph routing API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run against local server
  python -m benchmarks.run_benchmark --url http://localhost --port 8080

  # Run against GKE deployment
  python -m benchmarks.run_benchmark --url http://35.123.45.67 --port 80

  # Run with more iterations
  python -m benchmarks.run_benchmark --runs 5
        """,
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost",
        help="Base URL of the routing API (default: http://localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port of the routing API (default: 8080)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to test cases YAML config (default: benchmarks/test_cases.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory for output files (default: benchmarks/results)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per test case (default: 3)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds (default: 60.0)",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Run a warmup query before benchmarking",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        choices=["small_town", "large_city", "cross_shard"],
        help="Only run tests for a specific category",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay between queries in seconds (default: 0.1)",
    )
    return parser.parse_args()


def run_benchmarks(
    client: RoutingClient,
    config: BenchmarkConfig,
    runs: int,
    delay: float,
    category_filter: str | None = None,
) -> MetricsCollector:
    """
    Run benchmark tests and collect metrics.

    Args:
        client: The routing API client
        config: Benchmark configuration with test cases
        runs: Number of runs per test case
        delay: Delay between queries in seconds
        category_filter: Optional category to filter tests

    Returns:
        MetricsCollector with all results
    """
    collector = MetricsCollector()
    test_cases = config.test_cases

    if category_filter:
        test_cases = config.filter_by_category(category_filter)

    total_tests = len(test_cases)
    print(f"\nRunning {total_tests} test cases with {runs} runs each...")
    print(f"Total queries: {total_tests * runs * 2} (first + cached per run)\n")

    for i, tc in enumerate(test_cases, 1):
        print(f"[{i}/{total_tests}] Testing: {tc.name} ({tc.category})")

        for run in range(1, runs + 1):
            # First query (uncached)
            result = client.route(tc.start.lat, tc.start.lng, tc.end.lat, tc.end.lng)
            collector.add_result(
                QueryResult(
                    test_case=tc.name,
                    category=tc.category,
                    query_type="first",
                    run_number=run,
                    latency_ms=result.latency_ms,
                    success=result.success,
                    path_found=result.path_found,
                    distance_m=result.distance_m,
                    segments_count=result.segments_count,
                    error=result.error,
                )
            )

            if delay > 0:
                time.sleep(delay)

            # Second query (cached) - same exact coordinates
            result = client.route(tc.start.lat, tc.start.lng, tc.end.lat, tc.end.lng)
            collector.add_result(
                QueryResult(
                    test_case=tc.name,
                    category=tc.category,
                    query_type="cached",
                    run_number=run,
                    latency_ms=result.latency_ms,
                    success=result.success,
                    path_found=result.path_found,
                    distance_m=result.distance_m,
                    segments_count=result.segments_count,
                    error=result.error,
                )
            )

            if delay > 0:
                time.sleep(delay)

        # Print progress
        first_results = [r for r in collector.results if r.test_case == tc.name and r.query_type == "first" and r.success]
        cached_results = [r for r in collector.results if r.test_case == tc.name and r.query_type == "cached" and r.success]

        if first_results and cached_results:
            first_avg = sum(r.latency_ms for r in first_results) / len(first_results)
            cached_avg = sum(r.latency_ms for r in cached_results) / len(cached_results)
            print(f"   First: {first_avg:.1f}ms avg, Cached: {cached_avg:.1f}ms avg")
        else:
            failed = [r for r in collector.results if r.test_case == tc.name and not r.success]
            if failed:
                print(f"   WARNING: {len(failed)} queries failed - {failed[0].error[:50]}...")

    return collector


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Build base URL
    base_url = f"{args.url.rstrip('/')}:{args.port}"

    # Resolve config path
    script_dir = Path(__file__).parent
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = script_dir / "test_cases.yaml"

    # Resolve output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = script_dir / "results"

    # Load configuration
    print(f"Loading test cases from: {config_path}")
    try:
        config = BenchmarkConfig.from_yaml(config_path)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_path}")
        return 1
    except Exception as e:
        print(f"ERROR: Failed to load config: {e}")
        return 1

    print(f"Loaded {len(config.test_cases)} test cases")
    print(f"Categories: {', '.join(config.categories)}")

    # Create client
    client = RoutingClient(base_url, timeout=args.timeout)

    # Health check
    print(f"\nConnecting to: {base_url}")
    if not client.health_check():
        print("WARNING: Health check failed. The server may not be running.")
        print("Proceeding anyway, but expect errors...\n")
    else:
        print("Health check passed!\n")

    # Optional warmup
    if args.warmup and config.test_cases:
        print("Running warmup query...")
        first_tc = config.test_cases[0]
        client.route(first_tc.start.lat, first_tc.start.lng, first_tc.end.lat, first_tc.end.lng)
        time.sleep(0.5)

    # Run benchmarks
    try:
        collector = run_benchmarks(
            client=client,
            config=config,
            runs=args.runs,
            delay=args.delay,
            category_filter=args.category,
        )
    finally:
        client.close()

    # Generate reports
    reporter = BenchmarkReporter(output_dir, base_url, args.runs)
    reporter.report(collector)

    return 0


if __name__ == "__main__":
    sys.exit(main())
