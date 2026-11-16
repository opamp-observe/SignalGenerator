# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Cancellable OTLP/HTTP trace replay with timestamp and identity rewriting."""

from __future__ import annotations

import asyncio
import copy
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from signal_generator.config.models import TracesConfig
from signal_generator.traces.source import TIMESTAMP_KEYS, TraceRecord, load_trace_records

ID_WIDTHS = {"traceId": 32, "spanId": 16, "parentSpanId": 16}
Sleeper = Callable[[float], Awaitable[None]]
Clock = Callable[[], int]
IdGenerator = Callable[[int], str]


def _new_identifier(width: int) -> str:
    """Return a non-zero lower-case hexadecimal OTLP identifier of the requested width."""

    identifier = "0" * width
    while int(identifier, 16) == 0:
        identifier = secrets.token_hex(width // 2)
    return identifier


class TraceReplayError(RuntimeError):
    """Report trace loading, scheduling, transformation, or delivery failure."""


@dataclass(frozen=True, slots=True)
class TraceReplayControls:
    """Injectable timing, identity, and cancellation controls for trace scheduling."""

    sleeper: Sleeper = asyncio.sleep
    clock: Clock = time.time_ns
    id_generator: IdGenerator = _new_identifier
    stop_event: asyncio.Event | None = None


@dataclass(frozen=True, slots=True)
class _ReplayContext:
    """Group immutable cycle dependencies and keep the scheduler interface focused."""

    config: TracesConfig
    records: tuple[TraceRecord, ...]
    client: httpx.AsyncClient
    controls: TraceReplayControls


async def replay_traces(
    config: TracesConfig,
    *,
    controls: TraceReplayControls | None = None,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Replay timestamp-shifted OTLP requests and return the delivered record count."""

    if not config.enabled or config.source is None or config.push is None:
        raise TraceReplayError("trace replay requires enabled source and push configuration")
    records = load_trace_records(config.source)
    http_client = client or httpx.AsyncClient(timeout=config.push.timeout_seconds)
    replay_controls = controls or TraceReplayControls(id_generator=_new_identifier)
    try:
        return await _run_cycles(_ReplayContext(config, records, http_client, replay_controls))
    except Exception as error:
        raise TraceReplayError(str(error)) from error
    finally:
        if client is None:
            await http_client.aclose()


async def _run_cycles(context: _ReplayContext) -> int:
    """Deliver configured cycles with a new timestamp anchor and ID map per cycle."""

    delivered = 0
    cycle = 1
    first_source_timestamp = context.records[0].first_timestamp_unix_nano
    while _cycle_allowed(
        context.config.replay.cycles, cycle, context.controls.stop_event
    ):
        if cycle > 1 and context.config.replay.loop_gap_ms:
            await context.controls.sleeper(context.config.replay.loop_gap_ms / 1000)
        cycle_delta = context.controls.clock() - first_source_timestamp
        identifiers: dict[tuple[str, str], str] = {}
        previous_timestamp = first_source_timestamp
        for record in context.records:
            if context.controls.stop_event is not None and context.controls.stop_event.is_set():
                return delivered
            delay = (record.first_timestamp_unix_nano - previous_timestamp) / 1_000_000_000
            if delay > 0:
                await context.controls.sleeper(delay / context.config.replay.acceleration)
            payload = shifted_trace_payload(
                record.payload,
                cycle_delta,
                identifiers,
                context.controls.id_generator,
            )
            response = await context.client.post(
                context.config.push.url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            delivered += 1
            previous_timestamp = record.first_timestamp_unix_nano
        cycle += 1
    return delivered


def shifted_trace_payload(
    payload: dict[str, Any],
    delta_nanoseconds: int,
    identifiers: dict[tuple[str, str], str],
    id_generator: IdGenerator | None = None,
) -> dict[str, Any]:
    """Deep-copy an OTLP request while shifting timestamps and remapping IDs consistently."""

    shifted = copy.deepcopy(payload)
    _rewrite_values(shifted, delta_nanoseconds, identifiers, id_generator or _new_identifier)
    return shifted


def _rewrite_values(
    value: Any,
    delta_nanoseconds: int,
    identifiers: dict[tuple[str, str], str],
    id_generator: IdGenerator,
) -> None:
    """Rewrite known OTLP timestamp and identifier fields in place."""

    if isinstance(value, dict):
        for key, child in value.items():
            if key in TIMESTAMP_KEYS:
                value[key] = str(int(child) + delta_nanoseconds)
            elif key in ID_WIDTHS and child:
                map_key = (key if key == "traceId" else "spanId", str(child))
                value[key] = _mapped_identifier(
                    identifiers, map_key, ID_WIDTHS[key], id_generator
                )
            else:
                _rewrite_values(child, delta_nanoseconds, identifiers, id_generator)
    elif isinstance(value, list):
        for child in value:
            _rewrite_values(child, delta_nanoseconds, identifiers, id_generator)


def _mapped_identifier(
    identifiers: dict[tuple[str, str], str],
    map_key: tuple[str, str],
    width: int,
    id_generator: IdGenerator,
) -> str:
    """Return one stable replacement within a cycle, creating it only when absent."""

    if map_key not in identifiers:
        identifiers[map_key] = id_generator(width)
    return identifiers[map_key]


def _cycle_allowed(cycles: int | str, cycle: int, stop_event: asyncio.Event | None) -> bool:
    """Return whether another finite or cancellable infinite cycle may start."""

    return not (stop_event and stop_event.is_set()) and (cycles == "forever" or cycle <= cycles)
