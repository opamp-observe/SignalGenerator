# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Typed metric configuration and coordinated runtime lifecycle tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from signal_generator.application import run_application
from signal_generator.config.loader import load_configuration
from signal_generator.config.models import (
    AppConfig,
    DeploymentConfig,
    MetricsConfig,
    MetricSourceConfig,
    PullConfig,
    PushConfig,
    RuntimeConfig,
)
from signal_generator.metrics.models import MetricFrame
from signal_generator.metrics.runtime import MetricReplayRuntime


class RuntimePushAdapter:
    """Capture runtime pushes without network access."""

    def __init__(self) -> None:
        """Create empty delivery history."""

        self.frames: list[int | str | None] = []
        self.closed = False

    async def push(self, frame: MetricFrame) -> None:
        """Record a successful delivery."""

        self.frames.append(frame.frame)

    async def close(self) -> None:
        """Record lifecycle cleanup."""

        self.closed = True


def _write_source(path: Path) -> None:
    """Write two stable gauge frames."""

    documents = [
        {
            "frame": identifier,
            "metrics": [
                {
                    "name": "demo",
                    "type": "gauge",
                    "help": "Demo.",
                    "samples": [{"value": identifier}],
                }
            ],
        }
        for identifier in (1, 2)
    ]
    path.write_text("".join(f"{json.dumps(item)}\n" for item in documents), encoding="utf-8")


def test_loader_builds_typed_metrics_and_resolves_paths(tmp_path: Path) -> None:
    """Metric source and CA paths resolve against the configuration directory."""

    _write_source(tmp_path / "frames.jsonl")
    (tmp_path / "ca.pem").write_text("certificate", encoding="utf-8")
    document = {
        "schema_version": 1,
        "metrics": {
            "enabled": True,
            "source": {"path": "frames.jsonl", "eof": "stop"},
            "push": {
                "enabled": True,
                "url": "https://example.test",
                "job": "demo",
                "interval_seconds": 1,
                "tls": {"ca_file": "ca.pem"},
                "retry": {"maximum_attempts": 2, "maximum_backoff_seconds": 4},
            },
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    metrics = load_configuration(config_path).model.metrics
    assert metrics and metrics.source and metrics.source.path == (tmp_path / "frames.jsonl")
    assert metrics.push.tls.ca_file == tmp_path / "ca.pem"
    assert metrics.push.retry.maximum_backoff_seconds == 4


@pytest.mark.asyncio
async def test_runtime_pull_and_push_cursors_are_independent(tmp_path: Path) -> None:
    """Push completion leaves pull at its first frame and lifecycle routes consume nothing."""

    source_path = tmp_path / "frames.jsonl"
    _write_source(source_path)
    adapter = RuntimePushAdapter()
    config = MetricsConfig(
        enabled=True,
        source=MetricSourceConfig(source_path, eof="stop"),
        pull=PullConfig(enabled=True, host="127.0.0.1", port=0),
        push=PushConfig(
            enabled=True,
            url="http://example",
            job="demo",
            interval_seconds=0.001,
        ),
    )
    stop_event = asyncio.Event()
    runtime = MetricReplayRuntime(config, push_adapter=adapter)
    await runtime.start(stop_event)
    assert runtime.ready and runtime.server and runtime.server.bound_port
    assert runtime._push_task  # pylint: disable=protected-access
    await runtime._push_task  # pylint: disable=protected-access
    assert adapter.frames == [1, 2]
    assert runtime.pull_cursor and runtime.pull_cursor.snapshot().delivered == 0
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{runtime.server.bound_port}"
    ) as client:
        await client.get("/healthz")
        await client.get("/readyz")
        assert runtime.pull_cursor.snapshot().delivered == 0
        response = await client.get("/metrics")
        assert "demo 1.0" in response.text
    await runtime.close(stop_event)
    assert adapter.closed and not runtime.ready


@pytest.mark.asyncio
async def test_runtime_rejects_disabled_missing_source_and_transport(tmp_path: Path) -> None:
    """Runtime invariants fail without opening resources."""

    source_path = tmp_path / "frames.jsonl"
    _write_source(source_path)
    with pytest.raises(ValueError, match="enabled"):
        MetricReplayRuntime(MetricsConfig(enabled=False, source=MetricSourceConfig(source_path)))
    with pytest.raises(ValueError, match="source"):
        MetricReplayRuntime(MetricsConfig(enabled=True))
    runtime = MetricReplayRuntime(
        MetricsConfig(enabled=True, source=MetricSourceConfig(source_path))
    )
    with pytest.raises(ValueError, match="pull or push"):
        await runtime.wait(asyncio.Event())


@pytest.mark.asyncio
async def test_application_dispatches_metrics_runtime(monkeypatch, tmp_path: Path) -> None:
    """The application runs a metrics-only model through the shared lifecycle."""

    source_path = tmp_path / "frames.jsonl"
    _write_source(source_path)
    run_metrics = AsyncMock(return_value=2)
    monkeypatch.setattr("signal_generator.application.run_metric_runtime", run_metrics)
    model = AppConfig(
        1,
        RuntimeConfig(),
        DeploymentConfig(),
        None,
        MetricsConfig(enabled=True, source=MetricSourceConfig(source_path), pull=PullConfig(True)),
        None,
    )
    assert await run_application(model) == 2
    run_metrics.assert_awaited_once()
