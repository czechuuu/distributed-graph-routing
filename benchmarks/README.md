# E2E Benchmark Framework

A modular benchmark framework for testing the distributed graph routing API's latency and caching behavior.

## Installation

```bash
cd benchmarks
pip install -e .
# Or just install dependencies:
pip install requests pyyaml
```

## Usage

### Basic Usage

```bash
# Run against local server (default: http://localhost:8080)
python -m benchmarks.run_benchmark

# Specify custom URL and port
python -m benchmarks.run_benchmark --url http://localhost --port 8080

# Run against GKE deployment
python -m benchmarks.run_benchmark --url http://35.123.45.67 --port 80
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--url` | `http://localhost` | Base URL of the routing API |
| `--port` | `8080` | Port of the routing API |
| `--config` | `test_cases.yaml` | Path to test cases config |
| `--output-dir` | `results/` | Output directory for results |
| `--runs` | `3` | Number of runs per test case |
| `--timeout` | `60.0` | Request timeout in seconds |
| `--warmup` | `False` | Run warmup query first |
| `--category` | `None` | Filter: `small_town`, `large_city`, `cross_shard` |
| `--delay` | `0.1` | Delay between queries (seconds) |

### Examples

```bash
# Run only cross-shard tests with 5 iterations
python -m benchmarks.run_benchmark --category cross_shard --runs 5

# Run with warmup and longer timeout
python -m benchmarks.run_benchmark --warmup --timeout 120
```

## Output

Results are saved to `results/` in two formats:

### Summary TSV (`benchmark_summary_*.tsv`)
Aggregated statistics per test case:
```
CATEGORY    TEST_NAME       QUERY_TYPE  MEAN_MS  STD_MS  MIN_MS  MAX_MS  ...
small_town  Pabianice       first       45.20    3.10    42.00   48.50
small_town  Pabianice       cached      12.30    1.50    10.80   13.80
```

### Raw TSV (`benchmark_raw_*.tsv`)
Individual query results:
```
CATEGORY    TEST_NAME  QUERY_TYPE  RUN  LATENCY_MS  SUCCESS  PATH_FOUND  ...
small_town  Pabianice  first       1    45.00       True     True        ...
```

## Test Cases Configuration

Edit `test_cases.yaml` to add/modify test cases:

```yaml
test_cases:
  - name: "My-Town"
    category: "small_town"
    description: "Optional description"
    start: {lat: 52.0, lng: 21.0}
    end: {lat: 52.1, lng: 21.1}
```

### Categories

| Category | Description |
|----------|-------------|
| `small_town` | Same-shard routing in small areas |
| `large_city` | Same-shard routing in large urban areas |
| `cross_shard` | Routes spanning multiple shards |

## Extending the Framework

### Adding New Test Cases
Add entries to `test_cases.yaml` - no code changes needed.

### Adding New Metrics
Extend `metrics.py:QueryResult` and `MetricsCollector`.

### Custom Reporters
Implement a new reporter in `reporter.py` or create a new module.

### Future: Stress Testing
The architecture supports adding a `--concurrent` flag for parallel requests.
