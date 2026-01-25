#!/usr/bin/env python3
"""
Load test runner for the distributed graph routing API.

Sends concurrent requests to stress test the server and measure
throughput, latency distribution, and error rates under load.

Usage:
    python -m benchmarks.run_load_test --concurrency 10 --total-requests 50
    python -m benchmarks.run_load_test --scenario medium --warmup

Results are printed to console and saved to TSV files for analysis.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import yaml

from .client import RoutingClient
from .config import BenchmarkConfig, TestCase
from .load_metrics import LoadTestCollector, LoadTestResult
from .load_reporter import LoadTestReporter


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Load test the distributed graph routing API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic load test with 10 concurrent requests
  python -m benchmarks.run_load_test --concurrency 10 --total-requests 50

  # Use a pre-defined scenario
  python -m benchmarks.run_load_test --scenario medium --warmup

  # Test against GKE deployment
  python -m benchmarks.run_load_test --url http://35.x.x.x --port 80 --scenario heavy
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
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent requests (default: 10)",
    )
    parser.add_argument(
        "--total-requests",
        type=int,
        default=50,
        help="Total number of requests to send (default: 50)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        choices=["light", "medium", "heavy", "burst"],
        help="Use a pre-defined load scenario (overrides --concurrency and --total-requests)",
    )
    parser.add_argument(
        "--test-case",
        type=str,
        default="Warsaw-Gdansk",
        help="Test case name from test_cases.yaml (default: Warsaw-Gdansk)",
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
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds (default: 60.0)",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Send a warmup request before load testing",
    )
    return parser.parse_args()


def load_scenario(script_dir: Path, scenario_name: str) -> tuple[int, int]:
    """Load scenario configuration from YAML."""
    scenarios_path = script_dir / "load_test_scenarios.yaml"
    with open(scenarios_path, "r") as f:
        data = yaml.safe_load(f)

    for scenario in data.get("scenarios", []):
        if scenario["name"] == scenario_name:
            return scenario["concurrency"], scenario["total_requests"]

    raise ValueError(f"Unknown scenario: {scenario_name}")


def find_test_case(config: BenchmarkConfig, name: str) -> Optional[TestCase]:
    """Find a test case by name."""
    for tc in config.test_cases:
        if tc.name == name:
            return tc
    return None


def run_load_test(
    client: RoutingClient,
    test_case: TestCase,
    concurrency: int,
    total_requests: int,
) -> LoadTestCollector:
    """
    Run concurrent load test.

    Args:
        client: The routing API client
        test_case: Test case with start/end coordinates
        concurrency: Number of parallel workers
        total_requests: Total requests to send

    Returns:
        LoadTestCollector with all results
    """
    collector = LoadTestCollector()

    def make_request(request_id: int) -> LoadTestResult:
        """Execute a single request and return result."""
        start_time = time.time()
        result = client.route(
            test_case.start.lat,
            test_case.start.lng,
            test_case.end.lat,
            test_case.end.lng,
        )
        return LoadTestResult(
            request_id=request_id,
            start_time=start_time,
            latency_ms=result.latency_ms,
            success=result.success,
            path_found=result.path_found,
            error=result.error,
        )

    print(f"\nStarting load test:")
    print(f"  Concurrency: {concurrency}")
    print(f"  Total requests: {total_requests}")
    print(f"  Test case: {test_case.name}")
    print()

    collector.test_start_time = time.time()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(make_request, i): i
            for i in range(total_requests)
        }

        completed = 0
        for future in as_completed(futures):
            result = future.result()
            collector.add_result(result)
            completed += 1

            # Progress indicator every 10 requests or at least every 10%
            if completed % max(1, total_requests // 10) == 0 or completed == total_requests:
                pct = completed / total_requests * 100
                success_count = sum(1 for r in collector.results if r.success)
                print(f"  Progress: {completed}/{total_requests} ({pct:.0f}%) - {success_count} successful")

    collector.test_end_time = time.time()

    return collector


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Build base URL
    base_url = f"{args.url.rstrip('/')}:{args.port}"

    # Resolve paths
    script_dir = Path(__file__).parent
    config_path = Path(args.config) if args.config else script_dir / "test_cases.yaml"
    output_dir = Path(args.output_dir) if args.output_dir else script_dir / "results"

    # Load test cases config
    print(f"Loading test cases from: {config_path}")
    try:
        config = BenchmarkConfig.from_yaml(config_path)
    except Exception as e:
        print(f"ERROR: Failed to load config: {e}")
        return 1

    # Find the specified test case
    test_case = find_test_case(config, args.test_case)
    if not test_case:
        print(f"ERROR: Test case not found: {args.test_case}")
        print(f"Available: {', '.join(tc.name for tc in config.test_cases)}")
        return 1

    # Get concurrency and total_requests (from scenario or args)
    if args.scenario:
        try:
            concurrency, total_requests = load_scenario(script_dir, args.scenario)
            print(f"Using scenario '{args.scenario}': concurrency={concurrency}, requests={total_requests}")
        except Exception as e:
            print(f"ERROR: {e}")
            return 1
    else:
        concurrency = args.concurrency
        total_requests = args.total_requests

    # Create client
    client = RoutingClient(base_url, timeout=args.timeout)

    # Health check
    print(f"\nConnecting to: {base_url}")
    if not client.health_check():
        print("WARNING: Health check failed. The server may not be running.")
        print("Proceeding anyway, but expect errors...\n")
    else:
        print("Health check passed!")

    # Optional warmup
    if args.warmup:
        print("\nSending warmup request...")
        warmup_result = client.route(
            test_case.start.lat,
            test_case.start.lng,
            test_case.end.lat,
            test_case.end.lng,
        )
        if warmup_result.success:
            print(f"Warmup completed: {warmup_result.latency_ms:.1f}ms")
        else:
            print(f"Warmup failed: {warmup_result.error}")
        time.sleep(0.5)

    # Run load test
    try:
        collector = run_load_test(
            client=client,
            test_case=test_case,
            concurrency=concurrency,
            total_requests=total_requests,
        )
    finally:
        client.close()

    # Compute and report results
    summary = collector.compute_summary(args.test_case, concurrency)
    reporter = LoadTestReporter(output_dir, base_url)
    reporter.report(collector, summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
