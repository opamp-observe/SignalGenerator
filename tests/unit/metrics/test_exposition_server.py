# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Prometheus rendering and standalone pull route tests."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from prometheus_client.parser import text_string_to_metric_families

from signal_generator.config.models import PullConfig
from signal_generator.metrics.exposition import (
    ReplaySelfMetrics,
    create_pull_registry,
    render_frame,
    render_registry,
)
from signal_generator.metrics.server import MetricHttpServer
from signal_generator.metrics.source import parse_metric_frame
from signal_generator.metrics.store import FrameStore


def _complete_frame(identifier: int = 1):
    """Build a frame containing every supported Prometheus family type."""

    return parse_metric_frame(
        {
            "frame": identifier,
            "metrics": [
                {
                    "name": "demo_gauge",
                    "type": "gauge",
                    "help": "Gauge.",
                    "samples": [{"labels": {"host": "one"}, "value": identifier}],
                },
                {
                    "name": "demo_total",
                    "type": "counter",
                    "help": "Counter.",
                    "samples": [{"labels": {"host": "one"}, "value": identifier}],
                },
                {
                    "name": "demo_unknown",
                    "type": "untyped",
                    "help": "Untyped.",
                    "samples": [{"value": "NaN"}],
                },
                {
                    "name": "demo_build",
                    "type": "info",
                    "help": "Build.",
                    "samples": [{"labels": {"host": "one"}, "info": {"version": "1"}}],
                },
                {
                    "name": "demo_latency_seconds",
                    "type": "histogram",
                    "help": "Latency.",
                    "samples": [
                        {
                            "labels": {"host": "one"},
                            "buckets": [{"le": 0.5, "count": 1}, {"le": "+Inf", "count": 2}],
                            "sum": 0.7,
                            "count": 2,
                        }
                    ],
                },
                {
                    "name": "demo_size_bytes",
                    "type": "summary",
                    "help": "Size.",
                    "samples": [
                        {
                            "labels": {"host": "one"},
                            "quantiles": [{"quantile": 0.5, "value": 3}],
                            "sum": 6,
                            "count": 2,
                        }
                    ],
                },
            ],
        },
        1,
        100,
    )


def test_all_metric_families_render_as_parseable_prometheus_text() -> None:
    """Scalar and compound families produce valid Prometheus exposition text."""

    rendered = render_frame(_complete_frame()).decode()
    parsed = list(text_string_to_metric_families(rendered))
    sample_names = {sample.name for family in parsed for sample in family.samples}
    assert {
        "demo_gauge",
        "demo_total",
        "demo_build_info",
        "demo_latency_seconds_bucket",
        "demo_latency_seconds_sum",
        "demo_size_bytes",
        "demo_size_bytes_count",
    }.issubset(sample_names)


def test_pull_registry_advances_once_and_can_exclude_self_metrics() -> None:
    """Each collection advances exactly one frame and self metrics are optional."""

    store = FrameStore((_complete_frame(1), _complete_frame(2)))
    cursor = store.cursor("loop", "pull")
    self_metrics = ReplaySelfMetrics()
    registry = create_pull_registry(cursor, self_metrics, include_self_metrics=False)
    assert 'demo_gauge{host="one"} 1.0' in render_registry(registry).decode()
    assert 'demo_gauge{host="one"} 2.0' in render_registry(registry).decode()
    assert "signal_generator_" not in render_registry(registry).decode()
    assert cursor.snapshot().delivered == 3


@pytest.mark.asyncio
async def test_health_readiness_and_root_do_not_advance_frames() -> None:
    """Only the configured metrics route consumes a frame."""

    cursor = FrameStore((_complete_frame(),)).cursor("loop", "pull")
    self_metrics = ReplaySelfMetrics()
    readiness = {"value": False}
    server = MetricHttpServer(
        PullConfig(enabled=True, host="127.0.0.1", port=0, path="/custom"),
        create_pull_registry(cursor, self_metrics),
        self_metrics,
        lambda: readiness["value"],
    )
    await server.start()
    assert server.bound_port
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{server.bound_port}") as client:
            assert (await client.get("/healthz")).status_code == 200
            assert (await client.get("/")).json()["metrics"] == "/custom"
            assert (await client.get("/readyz")).status_code == 503
            assert cursor.snapshot().delivered == 0
            readiness["value"] = True
            assert (await client.get("/readyz")).status_code == 200
            assert (await client.get("/missing")).status_code == 404
            assert (await client.post("/custom")).status_code == 405
            metrics_response = await client.get("/custom")
            assert metrics_response.status_code == 200
            assert "demo_gauge" in metrics_response.text
            assert cursor.snapshot().delivered == 1
    finally:
        await server.close()
    assert server.bound_port is None


@pytest.mark.asyncio
async def test_concurrent_scrapes_are_atomic_without_sleep_races() -> None:
    """Concurrent HTTP scrapes allocate exactly one frame each."""

    frames = tuple(_complete_frame(identifier) for identifier in range(1, 11))
    cursor = FrameStore(frames).cursor("stop", "pull")
    self_metrics = ReplaySelfMetrics()
    server = MetricHttpServer(
        PullConfig(enabled=True, host="127.0.0.1", port=0),
        create_pull_registry(cursor, self_metrics, include_self_metrics=False),
        self_metrics,
        lambda: True,
    )
    await server.start()
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{server.bound_port}") as client:
            responses = await asyncio.gather(*(client.get("/metrics") for _ in range(10)))
        values = sorted(
            int(response.text.split('demo_gauge{host="one"} ')[1].split(".", maxsplit=1)[0])
            for response in responses
        )
        assert values == list(range(1, 11))
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_error_eof_returns_failure_without_crashing_server() -> None:
    """An error-policy cursor reports an HTTP failure after its last frame."""

    cursor = FrameStore((_complete_frame(),)).cursor("error", "pull")
    self_metrics = ReplaySelfMetrics()
    server = MetricHttpServer(
        PullConfig(enabled=True, host="127.0.0.1", port=0),
        create_pull_registry(cursor, self_metrics),
        self_metrics,
        lambda: True,
    )
    await server.start()
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{server.bound_port}") as client:
            assert (await client.get("/metrics")).status_code == 200
            assert (await client.get("/metrics")).status_code == 500
        assert self_metrics.snapshot().pull_failures == 1
    finally:
        await server.close()
