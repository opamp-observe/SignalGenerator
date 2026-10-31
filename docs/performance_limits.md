# Performance limits and measurement

## Supported operating envelope

SignalGenerator validates and loads metric JSON Lines into memory before becoming ready. Version
0.1.0 therefore targets deterministic test and demonstration workloads rather than unbounded
production-cardinality streams.

The supported initial envelope is:

| Limit | Supported value | Enforcement |
|---|---:|---|
| Bytes per JSONL record | 1 MiB by default | `maximum_line_bytes` validation |
| Samples per frame | 10,000 by default | `maximum_samples_per_frame` validation |
| Loaded frames | 100,000 when the process has sufficient memory | Operational limit; validate in the target container |
| Pull replicas sharing one sequence | 1 | Each process intentionally owns an independent cursor |
| Quart workers per unified deployment | 1 | Adapter startup contract |
| Load throughput release floor | 1,000 frames/second | `scripts/benchmark_replay.py` |
| Render throughput release floor | 1,000 frames/second | `scripts/benchmark_replay.py` |
| Peak traced allocation | 64 KiB per loaded frame | `scripts/benchmark_replay.py` |

The frame-count limit is not a hard parser cap because record size and metric cardinality determine
the real memory cost. Operators should leave at least twice the benchmarked peak allocation as
container headroom. Larger sources should be split into scenarios; indexed streaming storage is a
future, explicitly deferred feature.

## Reproducible benchmark

Run the benchmark with the project virtual environment:

```text
.venv/Scripts/python scripts/benchmark_replay.py --output test-results/performance.json
```

On Bash, use `.venv/bin/python`. The command creates a temporary, descriptor-stable NGINX-style
source, measures loading under `tracemalloc`, warms exposition once, and reports median throughput
over five runs. It returns non-zero if a release floor is missed. The JSON records Python and OS
information so results from unlike runners are not compared as if they were identical.

Release CI retains this JSON as evidence. Performance regressions are evaluated on the same runner
class; workstation results are diagnostic and do not redefine the baseline.

## Scaling characteristics

- Startup time and retained memory grow approximately linearly with frame count and samples per
  frame because all frames are validated before readiness.
- A pull scrape renders one frame and advances one atomic cursor assignment.
- Push cadence is bounded by the configured interval, network timeout, and retry backoff. Failed
  delivery retains the same frame.
- Multiple embedded runtimes have isolated registries and stores, so memory is additive.
- Multiple Quart workers duplicate cursors and agents; unified mode deliberately requires one.
