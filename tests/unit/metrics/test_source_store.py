# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Metric source semantics and atomic cursor tests."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from signal_generator.config.models import MetricSourceConfig
from signal_generator.metrics.models import MetricFamily, MetricFrame, MetricSample
from signal_generator.metrics.source import MetricDataError, load_metric_frames, parse_metric_frame
from signal_generator.metrics.store import FrameExhaustedError, FrameStore


def _family(metric_type: str = "gauge", sample: dict | None = None) -> dict:
    """Build one source family for focused semantic mutations."""

    return {
        "name": "demo_metric",
        "type": metric_type,
        "help": "Demo metric.",
        "samples": [sample or {"labels": {"instance": "one"}, "value": 1}],
    }


def _frame(identifier: int) -> MetricFrame:
    """Build a minimal typed frame for cursor tests."""

    family = MetricFamily("demo", "gauge", "Demo.", (MetricSample({}, value=identifier),))
    return MetricFrame(identifier, (family,))


def test_loads_all_metric_types_and_stable_descriptors(tmp_path: Path) -> None:
    """The loader produces typed scalar, info, histogram, and summary frames."""

    families = [
        _family(),
        {
            "name": "build",
            "type": "info",
            "help": "Build.",
            "samples": [{"labels": {"instance": "one"}, "info": {"version": "1.2"}}],
        },
        {
            "name": "latency_seconds",
            "type": "histogram",
            "help": "Latency.",
            "unit": "seconds",
            "samples": [
                {
                    "labels": {"instance": "one"},
                    "buckets": [
                        {"le": 0.1, "count": 2},
                        {"le": "+Inf", "count": 3},
                    ],
                    "sum": 0.4,
                    "count": 3,
                }
            ],
        },
        {
            "name": "size_bytes",
            "type": "summary",
            "help": "Size.",
            "samples": [
                {
                    "labels": {"instance": "one"},
                    "quantiles": [{"quantile": 0.5, "value": 10}],
                    "sum": 20,
                    "count": 2,
                }
            ],
        },
    ]
    source_path = tmp_path / "frames.jsonl"
    document = {"frame": 1, "observed_at": "2026-01-01T00:00:00Z", "metrics": families}
    source_path.write_text(json.dumps(document) + "\n\n", encoding="utf-8")
    frames = load_metric_frames(MetricSourceConfig(source_path))
    assert frames[0].observed_at is not None
    assert [family.type for family in frames[0].metrics] == [
        "gauge",
        "info",
        "histogram",
        "summary",
    ]


@pytest.mark.parametrize(
    ("family", "message"),
    [
        (
            {"name": "bad-name", "type": "gauge", "help": "x", "samples": [{"value": 1}]},
            "invalid or reserved",
        ),
        (
            {
                "name": "signal_generator_bad",
                "type": "gauge",
                "help": "x",
                "samples": [{"value": 1}],
            },
            "invalid or reserved",
        ),
        (
            {"name": "demo", "type": "unknown", "help": "x", "samples": [{"value": 1}]},
            "unsupported metric type",
        ),
        ({"name": "demo", "type": "gauge", "help": "x", "samples": []}, "non-empty array"),
        (_family(sample={"labels": {"__bad": "x"}, "value": 1}), "invalid label"),
        (_family(sample={"labels": {"good": 2}, "value": 1}), "invalid label"),
        (_family(sample={"value": "12"}), "invalid numeric string"),
        (_family("counter", {"value": -1}), "cannot be negative"),
        (_family("info", {"info": {}}), "labels must be an object"),
        (
            _family("histogram", {"buckets": [{"le": "+Inf", "count": 1}], "sum": 1, "count": 2}),
            r"\+Inf bucket",
        ),
        (
            _family("summary", {"quantiles": [{"quantile": 2, "value": 1}], "sum": 1, "count": 1}),
            "invalid quantile",
        ),
    ],
)
def test_rejects_invalid_metric_semantics(family: dict, message: str) -> None:
    """Semantic failures identify the offending metric contract."""

    with pytest.raises(MetricDataError, match=message):
        parse_metric_frame({"metrics": [family]}, 4, 100)


def test_rejects_frame_and_cross_frame_invariants(tmp_path: Path) -> None:
    """Frame limits, duplicates, timestamps, and descriptor drift fail before readiness."""

    with pytest.raises(MetricDataError, match="non-empty"):
        parse_metric_frame({"metrics": []}, 1, 10)
    with pytest.raises(MetricDataError, match="maximum_samples"):
        parse_metric_frame({"metrics": [_family()]}, 1, 0)
    with pytest.raises(MetricDataError, match="duplicate metric"):
        parse_metric_frame({"metrics": [_family(), _family()]}, 1, 10)
    with pytest.raises(MetricDataError, match="observed_at"):
        parse_metric_frame({"observed_at": "bad", "metrics": [_family()]}, 1, 10)
    duplicate = _family()
    duplicate["samples"] *= 2
    with pytest.raises(MetricDataError, match="duplicate label"):
        parse_metric_frame({"metrics": [duplicate]}, 1, 10)
    source_path = tmp_path / "frames.jsonl"
    first = {"metrics": [_family()]}
    changed = _family()
    changed["help"] = "Changed."
    source_path.write_text(
        f"{json.dumps(first)}\n{json.dumps({'metrics': [changed]})}\n", encoding="utf-8"
    )
    with pytest.raises(MetricDataError, match="descriptor changed"):
        load_metric_frames(MetricSourceConfig(source_path))


def test_source_file_limits_and_json_errors(tmp_path: Path) -> None:
    """Empty, malformed, and oversized JSONL inputs fail with physical-line context."""

    source_path = tmp_path / "frames.jsonl"
    source_path.write_text("\n", encoding="utf-8")
    with pytest.raises(MetricDataError, match="no frames"):
        load_metric_frames(MetricSourceConfig(source_path))
    source_path.write_text("{bad}\n", encoding="utf-8")
    with pytest.raises(MetricDataError, match="line 1: invalid JSON"):
        load_metric_frames(MetricSourceConfig(source_path))
    source_path.write_text(json.dumps({"metrics": [_family()]}), encoding="utf-8")
    with pytest.raises(MetricDataError, match="maximum_line_bytes"):
        load_metric_frames(MetricSourceConfig(source_path, maximum_line_bytes=1))


def test_cursor_eof_policies_and_snapshots() -> None:
    """Loop, hold, stop, and error policies have deterministic independent state."""

    store = FrameStore((_frame(1), _frame(2)))
    loop = store.cursor("loop", "pull")
    hold = store.cursor("hold_last", "hold")
    stop = store.cursor("stop", "stop")
    error = store.cursor("error", "error")
    assert [loop.next_frame().frame for _ in range(3)] == [1, 2, 1]
    assert [hold.next_frame().frame for _ in range(3)] == [1, 2, 2]
    assert [stop.next_frame(), stop.next_frame(), stop.next_frame()][-1] is None
    error.next_frame()
    error.next_frame()
    with pytest.raises(FrameExhaustedError):
        error.next_frame()
    assert loop.snapshot().delivered == 3
    assert stop.snapshot().exhausted


def test_cursor_allocates_frames_atomically_across_threads() -> None:
    """Concurrent scrapes cannot assign the same stop-policy frame twice."""

    frames = tuple(_frame(identifier) for identifier in range(40))
    cursor = FrameStore(frames).cursor("stop", "pull")
    with ThreadPoolExecutor(max_workers=8) as executor:
        delivered = list(executor.map(lambda _: cursor.next_frame(), range(40)))
    assert sorted(frame.frame for frame in delivered if frame) == list(range(40))
    assert cursor.snapshot().delivered == 40


def test_frame_store_rejects_empty_and_unknown_policy() -> None:
    """Store and cursor constructors enforce their invariants."""

    with pytest.raises(ValueError, match="at least one"):
        FrameStore(())
    store = FrameStore((_frame(1),))
    with pytest.raises(ValueError, match="unsupported EOF"):
        store.cursor("bad", "x")
