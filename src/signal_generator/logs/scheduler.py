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
from dataclasses import dataclass

from signal_generator.config.models import LogsConfig, OutputConfig
from signal_generator.logs.formatter import LogFormatter
from signal_generator.logs.models import LogEvent, RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput
from signal_generator.logs.parser import TokenParser
from signal_generator.logs.registry import create_output
from signal_generator.logs.source import read_records

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


async def replay_logs(
    config: LogsConfig,
    *,
    sleeper: Sleeper = asyncio.sleep,
    stop_event: asyncio.Event | None = None,
    outputs: Sequence[LogOutput] | None = None,
) -> int:
    """Parse the source once, replay configured cycles, and return the number of emitted events."""

    records = read_records(config.source)
    parser = TokenParser(config.source, config.defaults)
    events = [parser.parse(record, index) for index, record in enumerate(records, start=1)]
    formatter = LogFormatter(config.format, config.datetime_format)
    output_instances = (
        list(outputs) if outputs is not None else [create_output(item) for item in config.outputs]
    )
    opened = await _open_outputs(output_instances)
    context = _ReplayContext(config, events, formatter, output_instances, sleeper, stop_event)
    try:
        return await _run_cycles(context)
    except Exception as error:
        raise ReplayError(str(error)) from error
    finally:
        await _close_outputs(opened)


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
