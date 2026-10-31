# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Cancellable scheduled push loop with bounded exponential retry."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from signal_generator.config.models import PushConfig
from signal_generator.metrics.exposition import ReplaySelfMetrics
from signal_generator.metrics.models import MetricFrame
from signal_generator.metrics.push import PushAdapter
from signal_generator.metrics.store import FrameCursor, FrameExhaustedError

LOGGER = logging.getLogger(__name__)
SleepFunction = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class PushLoopControl:
    """Runtime controls grouped for injection and cooperative shutdown."""

    self_metrics: ReplaySelfMetrics
    stop_event: asyncio.Event
    sleep: SleepFunction = asyncio.sleep


@dataclass(slots=True)
class _PushState:
    """Mutable state retained across retry batches."""

    pending: MetricFrame | None = None
    previous_observed_at: datetime | None = None
    successful_pushes: int = 0


async def run_push_loop(
    config: PushConfig,
    cursor: FrameCursor,
    adapter: PushAdapter,
    control: PushLoopControl,
) -> int:
    """Push frames until stopped, retaining a failed frame until it succeeds."""

    state = _PushState()
    try:
        while not control.stop_event.is_set():
            if not await _prepare_pending(config, cursor, state, control):
                break
            delivered = await _push_with_retry(state.pending, config, adapter, control)
            if not await _complete_batch(delivered, config, state, control):
                break
    finally:
        await adapter.close()
    return state.successful_pushes


async def _prepare_pending(
    config: PushConfig,
    cursor: FrameCursor,
    state: _PushState,
    control: PushLoopControl,
) -> bool:
    """Allocate and optionally source-delay a frame only when none is pending."""

    if state.pending is not None:
        return True
    try:
        state.pending = cursor.next_frame()
    except FrameExhaustedError:
        LOGGER.exception("push cursor exhausted")
        return False
    if state.pending is None:
        return False
    delay = _source_delay(config, state.previous_observed_at, state.pending)
    return delay <= 0 or await _wait_or_stop(delay, control)


async def _complete_batch(
    delivered: bool,
    config: PushConfig,
    state: _PushState,
    control: PushLoopControl,
) -> bool:
    """Commit successful state or retain a failed frame before the next batch."""

    if delivered:
        state.successful_pushes += 1
        state.previous_observed_at = state.pending.observed_at if state.pending else None
        state.pending = None
    delay_required = not delivered or not config.use_source_timing
    return not delay_required or await _wait_or_stop(config.interval_seconds, control)


async def _push_with_retry(
    frame: MetricFrame | None,
    config: PushConfig,
    adapter: PushAdapter,
    control: PushLoopControl,
) -> bool:
    """Attempt one frame repeatedly without advancing its cursor on failures."""

    if frame is None:
        return False
    retry = config.retry
    for attempt in range(retry.maximum_attempts):
        control.self_metrics.push_attempt()
        try:
            await adapter.push(frame)
        except (OSError, httpx.HTTPError) as error:
            if not await _handle_retry_failure(error, attempt, config, control):
                return False
        else:
            control.self_metrics.push_success()
            return True
    return False


async def _handle_retry_failure(
    error: Exception,
    attempt: int,
    config: PushConfig,
    control: PushLoopControl,
) -> bool:
    """Record a failed attempt and wait its bounded exponential backoff when allowed."""

    control.self_metrics.push_failure()
    LOGGER.warning("push attempt %s failed: %s", attempt + 1, error)
    if attempt + 1 >= config.retry.maximum_attempts:
        return False
    backoff = min(
        config.retry.initial_backoff_seconds * (2**attempt),
        config.retry.maximum_backoff_seconds,
    )
    return await _wait_or_stop(backoff, control)


async def _wait_or_stop(delay: float, control: PushLoopControl) -> bool:
    """Wait through an injectable clock while remaining immediately stoppable in production."""

    if control.sleep is not asyncio.sleep:
        await control.sleep(delay)
        return not control.stop_event.is_set()
    try:
        await asyncio.wait_for(control.stop_event.wait(), timeout=delay)
    except TimeoutError:
        return True
    return False


def _source_delay(
    config: PushConfig, previous_observed_at: datetime | None, frame: MetricFrame
) -> float:
    """Use source observation deltas when requested and available."""

    if not config.use_source_timing or previous_observed_at is None or frame.observed_at is None:
        return 0.0
    return max(0.0, (frame.observed_at - previous_observed_at).total_seconds())
