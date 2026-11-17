# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Pushgateway transport and deterministic scheduled-push tests."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from signal_generator.config.models import (
    BasicAuthConfig,
    PushConfig,
    RetryConfig,
    TlsConfig,
)
from signal_generator.metrics.exposition import ReplaySelfMetrics
from signal_generator.metrics.models import MetricFamily, MetricFrame, MetricSample
from signal_generator.metrics.otlp import metric_frame_to_otlp_json
from signal_generator.metrics.push import (
    OtlpHttpMetricAdapter,
    PushConfigurationError,
    PushgatewayAdapter,
)
from signal_generator.metrics.push_scheduler import PushLoopControl, run_push_loop
from signal_generator.metrics.store import FrameStore


def _frame(identifier: int, seconds: int = 0) -> MetricFrame:
    """Build one pushable frame with an optional source timestamp."""

    family = MetricFamily("demo", "gauge", "Demo.", (MetricSample({}, value=identifier),))
    observed_at = datetime(2026, 1, 1, 0, 0, seconds, tzinfo=timezone.utc)
    return MetricFrame(identifier, (family,), observed_at)


@pytest.mark.asyncio
async def test_pushgateway_url_payload_and_bearer_auth() -> None:
    """Grouping labels are sorted/escaped and a bearer secret is supplied only at runtime."""

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PushgatewayAdapter(
        PushConfig(
            enabled=True,
            url="http://pushgateway:9091/",
            job="nginx demo",
            grouping_key={"zone": "one/two", "instance": "demo"},
            bearer_token_env="PUSH_TOKEN",  # noqa: S106 - environment variable name, not secret
        ),
        {"PUSH_TOKEN": "secret"},
        client,
    )
    await adapter.push(_frame(1))
    await adapter.close()
    await client.aclose()
    request = requests[0]
    assert request.url.raw_path.decode().endswith(
        "/metrics/job/nginx%20demo/instance/demo/zone/one%2Ftwo"
    )
    assert request.headers["Authorization"] == "Bearer secret"
    assert b"demo 1.0" in request.content


@pytest.mark.asyncio
async def test_pushgateway_basic_auth_and_http_failure() -> None:
    """Basic authentication is environment-backed and non-2xx responses fail the push."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Basic ")
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PushgatewayAdapter(
        PushConfig(
            enabled=True,
            url="https://push.example",
            job="demo",
            basic_auth=BasicAuthConfig("user", "PUSH_PASSWORD"),
            tls=TlsConfig(verify=False),
        ),
        {"PUSH_PASSWORD": "pass"},
        client,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.push(_frame(1))
    await client.aclose()


@pytest.mark.asyncio
async def test_otlp_http_adapter_posts_export_request_with_push_timestamp() -> None:
    """OTLP push posts JSON to the exact endpoint and timestamps points at delivery time."""

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OtlpHttpMetricAdapter(
        PushConfig(
            enabled=True,
            protocol="otlp_http_json",
            url="http://collector:4318/v1/metrics",
        ),
        client=client,
        clock=lambda: 123456789,
    )
    await adapter.push(_frame(7))
    await adapter.close()
    await client.aclose()

    request = requests[0]
    payload = json.loads(request.content)
    point = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["gauge"][
        "dataPoints"
    ][0]
    assert request.method == "POST"
    assert str(request.url) == "http://collector:4318/v1/metrics"
    assert request.headers["Content-Type"] == "application/json"
    assert point["asDouble"] == 7
    assert point["timeUnixNano"] == "123456789"


def test_otlp_serializer_maps_metric_data_types() -> None:
    """All source family types map to valid OTLP JSON metric structures."""

    families = (
        MetricFamily(
            "requests",
            "counter",
            "Requests.",
            (MetricSample({"host": "one"}, value=3),),
            "{request}",
        ),
        MetricFamily(
            "latency",
            "histogram",
            "Latency.",
            (
                MetricSample(
                    {},
                    buckets=((0.1, 2), (0.5, 5), ("+Inf", 6)),
                    sum_value=1.2,
                    count=6,
                ),
            ),
            "s",
        ),
        MetricFamily(
            "size",
            "summary",
            "Size.",
            (
                MetricSample(
                    {}, quantiles=((0.5, 4), (0.9, "+Inf")), sum_value=8, count=2
                ),
            ),
        ),
        MetricFamily(
            "build",
            "info",
            "Build.",
            (MetricSample({"host": "one"}, info={"version": "1.2"}),),
        ),
    )
    metrics = metric_frame_to_otlp_json(MetricFrame(1, families), 99)["resourceMetrics"][
        0
    ]["scopeMetrics"][0]["metrics"]

    assert metrics[0]["sum"]["aggregationTemporality"] == 2
    histogram = metrics[1]["histogram"]["dataPoints"][0]
    assert histogram["bucketCounts"] == ["2", "3", "1"]
    assert histogram["explicitBounds"] == [0.1, 0.5]
    assert metrics[2]["summary"]["dataPoints"][0]["quantileValues"][1]["value"] == "Infinity"
    info_point = metrics[3]["gauge"]["dataPoints"][0]
    assert info_point["asDouble"] == 1
    assert [attribute["key"] for attribute in info_point["attributes"]] == ["host", "version"]


def test_pushgateway_requires_configuration_and_secret_environment() -> None:
    """Missing endpoint fields and named secrets are classified before scheduling."""

    with pytest.raises(PushConfigurationError, match="url and job"):
        PushgatewayAdapter(PushConfig(enabled=True))
    with pytest.raises(PushConfigurationError, match="PUSH_PASSWORD"):
        PushgatewayAdapter(
            PushConfig(
                enabled=True,
                url="http://example",
                job="demo",
                basic_auth=BasicAuthConfig("user", "PUSH_PASSWORD"),
            ),
            {},
        )
    with pytest.raises(PushConfigurationError, match="PUSH_TOKEN"):
        PushgatewayAdapter(
            PushConfig(
                enabled=True,
                url="http://example",
                job="demo",
                bearer_token_env="PUSH_TOKEN",  # noqa: S106 - environment variable name
            ),
            {},
        )
    with pytest.raises(PushConfigurationError, match="mutually exclusive"):
        PushgatewayAdapter(
            PushConfig(
                enabled=True,
                url="http://example",
                job="demo",
                basic_auth=BasicAuthConfig("user", "PUSH_PASSWORD"),
                bearer_token_env="PUSH_TOKEN",  # noqa: S106 - environment variable name
            ),
            {"PUSH_PASSWORD": "pass", "PUSH_TOKEN": "token"},
        )
    with pytest.raises(PushConfigurationError, match="metric url"):
        OtlpHttpMetricAdapter(PushConfig(enabled=True, protocol="otlp_http_json"))


class RecordingAdapter:
    """Deterministic adapter that can fail a configured number of attempts."""

    def __init__(self, failures: int = 0) -> None:
        """Create an open adapter and empty attempt history."""

        self.failures = failures
        self.attempts: list[int | str | None] = []
        self.closed = False

    async def push(self, frame: MetricFrame) -> None:
        """Record the frame and raise an I/O failure while failures remain."""

        self.attempts.append(frame.frame)
        if self.failures:
            self.failures -= 1
            raise OSError("injected failure")

    async def close(self) -> None:
        """Record scheduler cleanup."""

        self.closed = True


@pytest.mark.asyncio
async def test_failed_push_retries_same_frame_then_advances_once() -> None:
    """Retries retain a pending frame and a success advances the independent cursor once."""

    store = FrameStore((_frame(1), _frame(2)))
    cursor = store.cursor("stop", "push")
    adapter = RecordingAdapter(failures=2)
    self_metrics = ReplaySelfMetrics()
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    config = PushConfig(
        enabled=True,
        url="http://example",
        job="demo",
        interval_seconds=4,
        retry=RetryConfig(3, 1, 2),
    )
    control = PushLoopControl(self_metrics, asyncio.Event(), fake_sleep)
    successful = await run_push_loop(config, cursor, adapter, control)
    assert successful == 2
    assert adapter.attempts == [1, 1, 1, 2]
    assert delays == [1, 2, 4, 4]
    assert cursor.snapshot().delivered == 2
    assert self_metrics.snapshot().push_failures == 2
    assert adapter.closed


@pytest.mark.asyncio
async def test_exhausted_retries_keep_pending_frame_until_stop() -> None:
    """An exhausted retry batch does not consume a new frame before the next batch."""

    cursor = FrameStore((_frame(1), _frame(2))).cursor("loop", "push")
    adapter = RecordingAdapter(failures=20)
    stop_event = asyncio.Event()
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        if len(adapter.attempts) >= 4:
            stop_event.set()

    config = PushConfig(
        enabled=True,
        url="http://example",
        job="demo",
        interval_seconds=5,
        retry=RetryConfig(2, 1, 1),
    )
    control = PushLoopControl(ReplaySelfMetrics(), stop_event, fake_sleep)
    await run_push_loop(config, cursor, adapter, control)
    assert adapter.attempts == [1, 1, 1, 1]
    assert cursor.snapshot().delivered == 1


@pytest.mark.asyncio
async def test_source_timing_uses_observation_delta() -> None:
    """Source timing waits between observations instead of using the fixed interval."""

    cursor = FrameStore((_frame(1, 0), _frame(2, 7))).cursor("stop", "push")
    adapter = RecordingAdapter()
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    config = PushConfig(
        enabled=True,
        url="http://example",
        job="demo",
        interval_seconds=99,
        use_source_timing=True,
    )
    control = PushLoopControl(ReplaySelfMetrics(), asyncio.Event(), fake_sleep)
    assert await run_push_loop(config, cursor, adapter, control) == 2
    assert delays == [7]
