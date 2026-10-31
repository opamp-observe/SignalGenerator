# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Measure bounded metric-frame loading and exposition throughput."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

from signal_generator.config.models import MetricSourceConfig
from signal_generator.constants import (
    KEY_FRAME,
    KEY_HELP,
    KEY_LABELS,
    KEY_METRIC_FAMILIES,
    KEY_NAME,
    KEY_SAMPLES,
    KEY_TYPE,
    KEY_VALUE,
)
from signal_generator.metrics.exposition import render_frame
from signal_generator.metrics.source import load_metric_frames

DEFAULT_FRAME_COUNT = 2_000
DEFAULT_ITERATIONS = 5
MINIMUM_LOAD_FRAMES_PER_SECOND = 1_000.0
MINIMUM_RENDER_FRAMES_PER_SECOND = 1_000.0
MAXIMUM_PEAK_BYTES_PER_FRAME = 65_536.0
KEY_FRAME_COUNT = "frame_count"
KEY_ITERATIONS = "iterations"
KEY_LOAD_FRAMES_PER_SECOND = "load_frames_per_second"
KEY_RENDER_FRAMES_PER_SECOND = "render_frames_per_second"
KEY_PEAK_BYTES_PER_FRAME = "peak_bytes_per_frame"
KEY_LIMITS = "limits"
KEY_PASSED = "passed"
KEY_PYTHON = "python"
KEY_PLATFORM = "platform"
LABEL_INSTANCE = "instance"


def run_benchmark(frame_count: int, iterations: int) -> dict[str, Any]:
    """Measure replay hot paths with repeated, schema-valid NGINX metric frames."""

    if frame_count < 1 or iterations < 1:
        raise ValueError("frame_count and iterations must be positive")
    source_line = _example_frame_line()
    with tempfile.TemporaryDirectory(prefix="signal-generator-benchmark-") as directory:
        source_path = Path(directory) / "frames.jsonl"
        source_path.write_text(source_line * frame_count, encoding="utf-8")
        config = MetricSourceConfig(path=source_path)
        load_rates, peak_bytes = _measure_loading(config, frame_count, iterations)
        frames = load_metric_frames(config)
        render_rates = _measure_rendering(frames, iterations)
    result = {
        KEY_FRAME_COUNT: frame_count,
        KEY_ITERATIONS: iterations,
        KEY_LOAD_FRAMES_PER_SECOND: round(statistics.median(load_rates), 2),
        KEY_RENDER_FRAMES_PER_SECOND: round(statistics.median(render_rates), 2),
        KEY_PEAK_BYTES_PER_FRAME: round(max(peak_bytes) / frame_count, 2),
        KEY_LIMITS: {
            KEY_LOAD_FRAMES_PER_SECOND: MINIMUM_LOAD_FRAMES_PER_SECOND,
            KEY_RENDER_FRAMES_PER_SECOND: MINIMUM_RENDER_FRAMES_PER_SECOND,
            KEY_PEAK_BYTES_PER_FRAME: MAXIMUM_PEAK_BYTES_PER_FRAME,
        },
        KEY_PYTHON: platform.python_version(),
        KEY_PLATFORM: platform.platform(),
    }
    result[KEY_PASSED] = _within_limits(result)
    return result


def _measure_loading(
    config: MetricSourceConfig, frame_count: int, iterations: int
) -> tuple[list[float], list[int]]:
    """Return per-run load throughput and peak traced allocation."""

    rates: list[float] = []
    peaks: list[int] = []
    for _iteration in range(iterations):
        tracemalloc.start()
        started = time.perf_counter()
        frames = load_metric_frames(config)
        elapsed = time.perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if len(frames) != frame_count:
            raise RuntimeError("benchmark loader returned an unexpected frame count")
        rates.append(frame_count / max(elapsed, sys.float_info.epsilon))
        peaks.append(peak)
    return rates, peaks


def _measure_rendering(frames: tuple[Any, ...], iterations: int) -> list[float]:
    """Return per-run exposition throughput after one untimed warm-up."""

    render_frame(frames[0])
    rates: list[float] = []
    for _iteration in range(iterations):
        started = time.perf_counter()
        for frame in frames:
            render_frame(frame)
        elapsed = time.perf_counter() - started
        rates.append(len(frames) / max(elapsed, sys.float_info.epsilon))
    return rates


def _example_frame_line() -> str:
    """Return one compact frame whose descriptor remains stable when repeated."""

    document = {
        KEY_FRAME: 1,
        KEY_METRIC_FAMILIES: [
            {
                KEY_NAME: "nginx_connections_active",
                KEY_TYPE: "gauge",
                KEY_HELP: "Active NGINX connections.",
                KEY_SAMPLES: [
                    {KEY_LABELS: {LABEL_INSTANCE: "benchmark"}, KEY_VALUE: 4}
                ],
            },
            {
                KEY_NAME: "nginx_http_requests_total",
                KEY_TYPE: "counter",
                KEY_HELP: "Total NGINX requests.",
                KEY_SAMPLES: [
                    {KEY_LABELS: {LABEL_INSTANCE: "benchmark"}, KEY_VALUE: 1200}
                ],
            },
        ],
    }
    return json.dumps(document, separators=(",", ":")) + "\n"


def _within_limits(result: dict[str, Any]) -> bool:
    """Return whether measured medians and peak allocation meet release limits."""

    return bool(
        result[KEY_LOAD_FRAMES_PER_SECOND] >= MINIMUM_LOAD_FRAMES_PER_SECOND
        and result[KEY_RENDER_FRAMES_PER_SECOND] >= MINIMUM_RENDER_FRAMES_PER_SECOND
        and result[KEY_PEAK_BYTES_PER_FRAME] <= MAXIMUM_PEAK_BYTES_PER_FRAME
    )


def main(arguments: list[str] | None = None) -> int:
    """Parse benchmark options, emit JSON evidence, and enforce the documented limits."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAME_COUNT)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(arguments)
    try:
        result = run_benchmark(options.frames, options.iterations)
    except ValueError as error:
        parser.error(str(error))
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result[KEY_PASSED] else 1


if __name__ == "__main__":
    raise SystemExit(main())
