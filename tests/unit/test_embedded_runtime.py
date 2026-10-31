# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Host-independent runtime and optional Quart attachment tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from quart import Quart

from signal_generator.config.models import (
    AppConfig,
    DeploymentConfig,
    MetricsConfig,
    MetricSourceConfig,
    PullConfig,
    RuntimeConfig,
)
from signal_generator.embedding.quart import (
    EXTENSION_KEY,
    attach_signal_generator_runtime,
)
from signal_generator.runtime import SignalGeneratorRuntime


def _config(source_path: Path) -> AppConfig:
    """Build one embedded metric-only configuration."""

    metrics = MetricsConfig(
        enabled=True,
        source=MetricSourceConfig(source_path, eof="loop"),
        pull=PullConfig(enabled=True),
    )
    deployment = DeploymentConfig(
        mode="embedded_quart",
        failure_policy="isolate",
        route_prefix="/ignored",
        runtime_id="ignored",
    )
    return AppConfig(1, RuntimeConfig(), deployment, None, metrics, None)


def _write_frames(path: Path, prefix: str) -> None:
    """Write two frames whose values identify the owning runtime."""

    documents = [
        {
            "frame": frame,
            "metrics": [
                {
                    "name": f"{prefix}_active",
                    "type": "gauge",
                    "help": "Active.",
                    "samples": [{"value": value}],
                }
            ],
        }
        for frame, value in ((1, 4), (2, 7))
    ]
    path.write_text("".join(f"{json.dumps(item)}\n" for item in documents), encoding="utf-8")


@pytest.mark.asyncio
async def test_runtime_health_does_not_consume_and_apply_rolls_back(tmp_path: Path) -> None:
    """Health is passive and an invalid logical restart restores the running scenario."""

    source_path = tmp_path / "frames.jsonl"
    _write_frames(source_path, "nginx")
    runtime = SignalGeneratorRuntime("nginx", _config(source_path))
    await runtime.start()
    assert runtime.health().ready
    assert runtime.metric_runtime and runtime.metric_runtime.pull_cursor
    assert runtime.metric_runtime.pull_cursor.snapshot().delivered == 0
    runtime.health()
    assert runtime.metric_runtime.pull_cursor.snapshot().delivered == 0
    assert b"nginx_active 4.0" in runtime.render_metrics()
    invalid = AppConfig(
        1,
        RuntimeConfig(),
        DeploymentConfig(mode="embedded_quart"),
        None,
        MetricsConfig(enabled=True, source=None, pull=PullConfig(enabled=True)),
        None,
    )
    with pytest.raises(ValueError, match="source"):
        await runtime.apply_config(invalid)
    assert (
        runtime.config.metrics
        and runtime.config.metrics.source
        and runtime.config.metrics.source.path == source_path
    )
    assert runtime.health().ready and runtime.health().restart_count == 1
    await runtime.stop()
    assert not runtime.health().running


@pytest.mark.asyncio
async def test_quart_hosts_multiple_prefixed_runtimes_and_cleans_up(tmp_path: Path) -> None:
    """Two replay registries share one Quart listener without route or cursor collision."""

    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"
    _write_frames(first_path, "nginx_a")
    _write_frames(second_path, "nginx_b")
    app = Quart(__name__)
    first = attach_signal_generator_runtime(
        app,
        runtime_id="nginx-a",
        config=_config(first_path),
        route_prefix="/signal-generator/nginx-a",
    )
    second = attach_signal_generator_runtime(
        app,
        runtime_id="nginx-b",
        config=_config(second_path),
        route_prefix="/signal-generator/nginx-b",
    )
    async with app.test_app():
        client = app.test_client()
        assert (await client.get("/signal-generator/nginx-a/healthz")).status_code == 200
        assert first.metric_runtime and first.metric_runtime.pull_cursor
        assert first.metric_runtime.pull_cursor.snapshot().delivered == 0
        first_metrics = await client.get("/signal-generator/nginx-a/metrics")
        second_metrics = await client.get("/signal-generator/nginx-b/metrics")
        assert b"nginx_a_active 4.0" in await first_metrics.get_data()
        assert b"nginx_b_active 4.0" in await second_metrics.get_data()
        assert len(app.extensions[EXTENSION_KEY]) == 2
    assert not first.health().running and not second.health().running
    assert first.metric_runtime is None and second.metric_runtime is None


def test_quart_attachment_rejects_duplicate_ids_prefixes_and_reserved_prefix(
    tmp_path: Path,
) -> None:
    """Attachment rejects ambiguous route ownership before Quart starts."""

    source_path = tmp_path / "frames.jsonl"
    _write_frames(source_path, "nginx")
    app = Quart(__name__)
    attach_signal_generator_runtime(
        app, runtime_id="one", config=_config(source_path), route_prefix="/one"
    )
    with pytest.raises(ValueError, match="runtime_id"):
        attach_signal_generator_runtime(
            app, runtime_id="one", config=_config(source_path), route_prefix="/two"
        )
    with pytest.raises(ValueError, match="route_prefix"):
        attach_signal_generator_runtime(
            app, runtime_id="two", config=_config(source_path), route_prefix="/one"
        )
    with pytest.raises(ValueError, match="route_prefix"):
        attach_signal_generator_runtime(
            Quart("reserved"),
            runtime_id="two",
            config=_config(source_path),
            route_prefix="/",
        )


@pytest.mark.asyncio
async def test_quart_attachment_can_delegate_lifecycle_to_composition_host(tmp_path: Path) -> None:
    """Unified hosts can attach routes while retaining explicit ordered lifecycle ownership."""

    source_path = tmp_path / "frames.jsonl"
    _write_frames(source_path, "nginx")
    app = Quart("delegated")
    runtime = attach_signal_generator_runtime(
        app,
        runtime_id="delegated",
        config=_config(source_path),
        route_prefix="/delegated",
        manage_lifecycle=False,
    )
    async with app.test_app():
        assert not runtime.health().running
        await runtime.start()
        assert (await app.test_client().get("/delegated/readyz")).status_code == 200
        await runtime.stop()
    assert not runtime.health().running
