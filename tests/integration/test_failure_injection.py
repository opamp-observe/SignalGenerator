# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Inject release-critical file, port, network, signal, and data failures."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from prometheus_client import CollectorRegistry

from signal_generator.config.models import MetricSourceConfig, PullConfig, PushConfig
from signal_generator.lifecycle import ShutdownController
from signal_generator.metrics.exposition import ReplaySelfMetrics
from signal_generator.metrics.models import MetricFamily, MetricFrame, MetricSample
from signal_generator.metrics.push import PushgatewayAdapter
from signal_generator.metrics.server import MetricHttpServer
from signal_generator.metrics.source import MetricDataError, load_metric_frames


@pytest.mark.asyncio
async def test_occupied_pull_port_fails_without_leaking_listener() -> None:
    """A bind collision must fail startup and leave both listeners independently closable."""

    occupying_server = await asyncio.start_server(lambda _reader, _writer: None, "127.0.0.1", 0)
    occupied_port = int(occupying_server.sockets[0].getsockname()[1])
    metric_server = MetricHttpServer(
        PullConfig(enabled=True, host="127.0.0.1", port=occupied_port),
        CollectorRegistry(),
        ReplaySelfMetrics(),
        lambda: True,
    )
    with pytest.raises(OSError):
        await metric_server.start()
    assert metric_server.bound_port is None
    await metric_server.close()
    occupying_server.close()
    await occupying_server.wait_closed()


def test_missing_and_malformed_metric_files_fail_with_context(tmp_path: Path) -> None:
    """Missing files and invalid JSON must fail before readiness with actionable context."""

    missing_path = tmp_path / "missing.jsonl"
    with pytest.raises(FileNotFoundError):
        load_metric_frames(MetricSourceConfig(path=missing_path))

    malformed_path = tmp_path / "malformed.jsonl"
    malformed_path.write_text('{"frame":\n', encoding="utf-8")
    with pytest.raises(MetricDataError, match="line 1: invalid JSON"):
        load_metric_frames(MetricSourceConfig(path=malformed_path))


@pytest.mark.asyncio
async def test_push_network_failure_is_propagated_and_adapter_closes() -> None:
    """A transport outage must be visible to retry policy without corrupting the frame."""

    async def fail_connection(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("injected outage", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(fail_connection))
    adapter = PushgatewayAdapter(
        PushConfig(enabled=True, url="http://push.invalid", job="failure-test"), client=client
    )
    frame = MetricFrame(
        1,
        (MetricFamily("nginx_up", "gauge", "Target health.", (MetricSample({}, value=1),)),),
    )
    with pytest.raises(httpx.ConnectError, match="injected outage"):
        await adapter.push(frame)
    assert frame.frame == 1
    await adapter.close()
    await client.aclose()


def test_shutdown_request_sets_cooperative_signal_event() -> None:
    """Signal handling must request cooperative shutdown instead of terminating cleanup."""

    controller = ShutdownController()
    assert not controller.stop_event.is_set()
    controller.request_stop()
    assert controller.stop_event.is_set()
