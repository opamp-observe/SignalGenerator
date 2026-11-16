# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Trace loading, timestamp shifting, scheduling, and loop identity tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from signal_generator.config.models import (
    TracePushConfig,
    TraceReplayConfig,
    TracesConfig,
    TraceSourceConfig,
)
from signal_generator.traces.replay import TraceReplayControls, replay_traces
from signal_generator.traces.source import TraceDataError, load_trace_records


def _request(start: int, end: int, *, child: bool = False) -> dict:
    """Create a small OTLP request with linked span and event identifiers."""

    span = {
        "traceId": "1" * 32,
        "spanId": ("3" if child else "2") * 16,
        "name": "child" if child else "root",
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
        "events": [{"timeUnixNano": str(start + 2), "name": "event"}],
    }
    if child:
        span["parentSpanId"] = "2" * 16
        span["links"] = [{"traceId": "1" * 32, "spanId": "2" * 16}]
    return {"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}


def _write_source(path: Path) -> None:
    """Write two related OTLP requests as JSON Lines."""

    path.write_text(
        "\n".join((json.dumps(_request(100, 110)), json.dumps(_request(200, 220, child=True))))
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_replay_shifts_all_timestamps_and_remaps_ids_for_each_cycle(tmp_path: Path) -> None:
    """One delta preserves timing while every loop gets consistent fresh identities."""

    source_path = tmp_path / "traces.ndjson"
    _write_source(source_path)
    received: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(200, json={})

    generated = iter(
        ["a" * 32, "b" * 16, "c" * 16, "d" * 32, "e" * 16, "f" * 16]
    )
    sleeps: list[float] = []

    async def sleeper(delay: float) -> None:
        sleeps.append(delay)

    config = TracesConfig(
        True,
        TraceSourceConfig(source_path),
        TraceReplayConfig(cycles=2, acceleration=2, loop_gap_ms=50),
        TracePushConfig("http://collector/v1/traces"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        delivered = await replay_traces(
            config,
            controls=TraceReplayControls(
                sleeper=sleeper,
                clock=iter((1_000, 2_000)).__next__,
                id_generator=lambda _width: next(generated),
            ),
            client=client,
        )

    assert delivered == 4
    assert sleeps == [0.00000005, 0.05, 0.00000005]
    first_span = received[0]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    child_span = received[1]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert (first_span["startTimeUnixNano"], first_span["endTimeUnixNano"]) == ("1000", "1010")
    assert child_span["events"][0]["timeUnixNano"] == "1102"
    assert child_span["traceId"] == first_span["traceId"] == "a" * 32
    assert child_span["parentSpanId"] == first_span["spanId"] == "b" * 16
    assert child_span["links"][0]["spanId"] == "b" * 16
    assert received[2]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"] == "d" * 32


def test_loader_rejects_non_otlp_and_empty_sources(tmp_path: Path) -> None:
    """Source validation rejects documents without resource spans or timestamps."""

    source_path = tmp_path / "bad.ndjson"
    source_path.write_text('{"resourceSpans":[]}\n', encoding="utf-8")
    with pytest.raises(TraceDataError, match="no OTLP span or event timestamps"):
        load_trace_records(TraceSourceConfig(source_path))
