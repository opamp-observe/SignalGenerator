# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Monotonic, cancellable log replay with bounded output failure policies."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from signal_generator.config.models import (
    LogsConfig,
    LogSourceConfig,
    OutputConfig,
    ScheduledLogSourceConfig,
)
from signal_generator.logs.formatter import LogFormatter
from signal_generator.logs.models import LogEvent, RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput
from signal_generator.logs.parser import TokenParser
from signal_generator.logs.registry import create_output
from signal_generator.logs.source import read_records
from signal_generator.scheduling import (
    ScheduledSource,
    ScheduledSourceEvent,
    SignalEnvelope,
    create_cycle_envelopes,
    merge_envelope_streams,
    normalize_sources,
)

LOGGER = logging.getLogger(__name__)
Sleeper = Callable[[float], Awaitable[None]]


class OutputStartupError(RuntimeError):
    """Report that one or more outputs could not acquire their startup resources."""


class ReplayError(RuntimeError):
    """Report an event parsing, scheduling, or output write failure."""


@dataclass(frozen=True, slots=True)
class _ReplayContext:
    """Group immutable cycle dependencies to keep scheduling helpers focused."""

    config: LogsConfig
    events: Sequence[LogEvent]
    formatter: LogFormatter
    outputs: Sequence[LogOutput]
    sleeper: Sleeper
    stop_event: asyncio.Event | None


@dataclass(frozen=True, slots=True)
class _ScheduledReplayContext:
    """Group normalized multi-source replay dependencies and output state."""

    config: LogsConfig
    base_envelopes: tuple[SignalEnvelope, ...]
    formatter: LogFormatter
    outputs: Sequence[LogOutput]
    sleeper: Sleeper
    stop_event: asyncio.Event | None
    scenario_start: datetime | None


async def replay_logs(
    config: LogsConfig,
    *,
    sleeper: Sleeper = asyncio.sleep,
    stop_event: asyncio.Event | None = None,
    outputs: Sequence[LogOutput] | None = None,
) -> int:
    """Parse the source once, replay configured cycles, and return the number of emitted events."""

    formatter = LogFormatter(config.format, config.datetime_format)
    output_instances = (
        list(outputs) if outputs is not None else [create_output(item) for item in config.outputs]
    )
    scheduled_context = _build_scheduled_context(
        config,
        formatter,
        output_instances,
        sleeper,
        stop_event,
    )
    legacy_context = (
        None
        if scheduled_context is not None
        else _build_legacy_context(config, formatter, output_instances, sleeper, stop_event)
    )
    opened = await _open_outputs(output_instances)
    try:
        if scheduled_context is not None:
            return await _run_scheduled_cycles(scheduled_context)
        if legacy_context is None:  # pragma: no cover - guarded by model validation
            raise ReplayError("log replay has no configured source")
        return await _run_cycles(legacy_context)
    except Exception as error:
        raise ReplayError(str(error)) from error
    finally:
        await _close_outputs(opened)


def _build_legacy_context(
    config: LogsConfig,
    formatter: LogFormatter,
    outputs: Sequence[LogOutput],
    sleeper: Sleeper,
    stop_event: asyncio.Event | None,
) -> _ReplayContext:
    """Build the unchanged single-source path used by legacy configurations."""

    if config.source is None:
        raise ReplayError("log replay has no configured source")
    events = _parse_source(config.source, config)
    return _ReplayContext(config, events, formatter, outputs, sleeper, stop_event)


def _build_scheduled_context(
    config: LogsConfig,
    formatter: LogFormatter,
    outputs: Sequence[LogOutput],
    sleeper: Sleeper,
    stop_event: asyncio.Event | None,
) -> _ScheduledReplayContext | None:
    """Normalize explicitly scheduled or multi-source logs into one replay plan."""

    if not config.sources and config.replay.start_at is None:
        return None
    scheduled_sources = _scheduled_log_sources(config)
    streams = normalize_sources(
        scheduled_sources,
        default_interval_ms=config.replay.default_interval_ms,
    )
    return _ScheduledReplayContext(
        config,
        merge_envelope_streams(streams),
        formatter,
        outputs,
        sleeper,
        stop_event,
        _scenario_start(config.replay.start_at),
    )


def _scheduled_log_sources(config: LogsConfig) -> tuple[ScheduledSource, ...]:
    """Adapt typed legacy or multi-source log configuration to scheduler inputs."""

    configured_sources = config.sources or _legacy_scheduled_source(config)
    return tuple(
        ScheduledSource(
            source_id=source_config.source_id,
            signal_type="log",
            priority=source_config.priority,
            source_ordinal=source_ordinal,
            events=tuple(
                ScheduledSourceEvent(
                    payload=event,
                    timestamp=event.timestamp,
                    relative_delay_ms=event.relative_delay_ms,
                )
                for event in _parse_source(source_config.source, config)
            ),
        )
        for source_ordinal, source_config in enumerate(configured_sources)
    )


def _legacy_scheduled_source(config: LogsConfig) -> tuple[ScheduledLogSourceConfig, ...]:
    """Wrap an explicitly time-shifted legacy source without changing its file contract."""

    if config.source is None:
        raise ReplayError("log replay has no configured source")
    return (
        ScheduledLogSourceConfig(
            source_id="legacy",
            priority=config.replay.source_priority,
            source=config.source,
        ),
    )


def _parse_source(source: LogSourceConfig, config: LogsConfig) -> tuple[LogEvent, ...]:
    """Read and parse one source completely before opening any output resources."""

    parser = TokenParser(source, config.defaults)
    return tuple(
        parser.parse(record, source_index)
        for source_index, record in enumerate(read_records(source), start=1)
    )


def _scenario_start(configured_start: str | None) -> datetime | None:
    """Resolve one explicit output timestamp epoch for the complete scenario."""

    if configured_start is None:
        return None
    if configured_start == "now":
        return datetime.now(UTC)
    return datetime.fromisoformat(configured_start.replace("Z", "+00:00"))


async def _run_scheduled_cycles(context: _ScheduledReplayContext) -> int:
    """Emit normalized cycles in globally merged order with monotonic loop epochs."""

    emitted = 0
    cycle = 1
    previous_offset_ns: int | None = None
    if context.config.replay.start_delay_ms:
        await context.sleeper(context.config.replay.start_delay_ms / 1000)
    while _cycle_allowed(context.config.replay.cycles, cycle, context.stop_event):
        cycle_envelopes = create_cycle_envelopes(
            context.base_envelopes,
            cycle=cycle,
            previous_final_offset_ns=previous_offset_ns,
            loop_gap_ms=context.config.replay.loop_gap_ms,
        )
        emitted_in_cycle, previous_offset_ns = await _run_scheduled_cycle(
            context,
            cycle_envelopes,
            previous_offset_ns,
        )
        emitted += emitted_in_cycle
        await _flush_outputs(context.outputs)
        cycle += 1
    return emitted


async def _run_scheduled_cycle(
    context: _ScheduledReplayContext,
    envelopes: tuple[SignalEnvelope, ...],
    previous_offset_ns: int | None,
) -> tuple[int, int | None]:
    """Emit one merged cycle and return its count and final normalized offset."""

    emitted = 0
    for record_number, envelope in enumerate(envelopes, start=1):
        if context.stop_event is not None and context.stop_event.is_set():
            break
        delay_seconds = _envelope_delay_seconds(
            envelope,
            previous_offset_ns,
            context.config.replay.acceleration,
        )
        if delay_seconds:
            await context.sleeper(delay_seconds)
        event = _event_for_envelope(envelope, context.scenario_start)
        rendered = context.formatter.render(event, envelope.cycle, record_number)
        await _write_outputs(
            rendered,
            context.config.outputs,
            context.outputs,
            context.sleeper,
        )
        emitted += 1
        previous_offset_ns = envelope.scenario_offset_ns
    return emitted, previous_offset_ns


def _envelope_delay_seconds(
    envelope: SignalEnvelope,
    previous_offset_ns: int | None,
    acceleration: float,
) -> float:
    """Convert an absolute scenario offset into the next accelerated relative wait."""

    if previous_offset_ns is None:
        return 0.0
    delay_ns = max(0, envelope.scenario_offset_ns - previous_offset_ns)
    return delay_ns / 1_000_000_000 / acceleration


def _event_for_envelope(
    envelope: SignalEnvelope, scenario_start: datetime | None
) -> LogEvent:
    """Return the log payload with an explicit shifted timestamp when requested."""

    if not isinstance(envelope.payload, LogEvent):  # pragma: no cover - adapter invariant
        raise ReplayError("log schedule contains a non-log payload")
    if scenario_start is None:
        return envelope.payload
    shifted_timestamp = scenario_start + timedelta(
        microseconds=envelope.scenario_offset_ns // 1_000
    )
    return replace(envelope.payload, timestamp=shifted_timestamp)


async def _run_cycles(context: _ReplayContext) -> int:
    """Emit configured cycles after parsing and output startup have completed."""

    emitted = 0
    cycle = 1
    while _cycle_allowed(context.config.replay.cycles, cycle, context.stop_event):
        if cycle == 1 and context.config.replay.start_delay_ms:
            await context.sleeper(context.config.replay.start_delay_ms / 1000)
        emitted += await _run_cycle(context, cycle)
        await _flush_outputs(context.outputs)
        if _needs_loop_gap(context, cycle):
            await context.sleeper(context.config.replay.loop_gap_ms / 1000)
        cycle += 1
    return emitted


async def _run_cycle(context: _ReplayContext, cycle: int) -> int:
    """Emit one cycle and return early when cooperative shutdown is requested."""

    emitted = 0
    previous: LogEvent | None = None
    for record_number, event in enumerate(context.events, start=1):
        if context.stop_event is not None and context.stop_event.is_set():
            break
        delay_seconds = _delay_seconds(event, previous, record_number, context.config)
        if delay_seconds:
            await context.sleeper(delay_seconds)
        rendered = context.formatter.render(event, cycle, record_number)
        await _write_outputs(rendered, context.config.outputs, context.outputs, context.sleeper)
        emitted += 1
        previous = event
    return emitted


def _needs_loop_gap(context: _ReplayContext, cycle: int) -> bool:
    """Return true only when another cycle is allowed and a loop gap is configured."""

    return bool(
        context.config.replay.loop_gap_ms
        and _cycle_allowed(context.config.replay.cycles, cycle + 1, context.stop_event)
    )


def _cycle_allowed(cycles: int | str, cycle: int, stop_event: asyncio.Event | None) -> bool:
    """Determine whether a cycle should start, including explicit infinite replay cancellation."""

    if stop_event is not None and stop_event.is_set():
        return False
    return cycles == "forever" or cycle <= cycles


def _delay_seconds(
    event: LogEvent, previous: LogEvent | None, record_number: int, config: LogsConfig
) -> float:
    """Derive accelerated spacing from relative, absolute, or default timing."""

    if record_number == 1:
        return 0.0
    if event.relative_delay_ms is not None:
        milliseconds = event.relative_delay_ms
    elif event.timestamp is not None and previous is not None and previous.timestamp is not None:
        milliseconds = max(0.0, (event.timestamp - previous.timestamp).total_seconds() * 1000)
    else:
        milliseconds = config.replay.default_interval_ms
    return milliseconds / 1000 / config.replay.acceleration


async def _open_outputs(outputs: Sequence[LogOutput]) -> list[LogOutput]:
    """Open outputs in order and unwind previously opened outputs when startup fails."""

    opened: list[LogOutput] = []
    try:
        for output in outputs:
            await output.open()
            opened.append(output)
    except Exception as error:
        await _close_outputs(opened)
        raise OutputStartupError(str(error)) from error
    return opened


async def _write_outputs(
    event: RenderedLogEvent,
    configs: Sequence[OutputConfig],
    outputs: Sequence[LogOutput],
    sleeper: Sleeper,
) -> None:
    """Apply each output's fail, retry, or continue policy independently."""

    for config, output in zip(configs, outputs, strict=True):
        attempts = config.retry.maximum_attempts if config.failure_policy == "retry" else 1
        for attempt in range(1, attempts + 1):
            try:
                await output.write(event)
                break
            except Exception as error:
                if config.failure_policy == "continue":
                    LOGGER.exception("log output %s failed; continuing", config.type)
                    break
                if attempt == attempts:
                    raise error
                await sleeper(config.retry.initial_backoff_seconds)


async def _flush_outputs(outputs: Sequence[LogOutput]) -> None:
    """Flush all opened outputs after a completed cycle."""

    for output in outputs:
        await output.flush()


async def _close_outputs(outputs: Sequence[LogOutput]) -> None:
    """Close outputs in reverse acquisition order while preserving the first close attempt."""

    for output in reversed(outputs):
        try:
            await output.close()
        except Exception:
            LOGGER.exception("log output close failed")
