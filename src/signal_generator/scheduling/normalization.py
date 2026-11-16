# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Normalize absolute and relative source time into scenario-relative envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from signal_generator.scheduling.models import (
    ScheduledSource,
    ScheduledSourceEvent,
    SignalEnvelope,
)

MILLISECONDS_TO_NANOSECONDS = 1_000_000
SECONDS_PER_DAY = 86_400
SECONDS_TO_NANOSECONDS = 1_000_000_000
MICROSECONDS_TO_NANOSECONDS = 1_000


class TimestampNormalizationError(ValueError):
    """Report an ambiguous or invalid timestamp sequence before replay starts."""


@dataclass(frozen=True, slots=True)
class _TimedSourceEvent:
    """Retain one event with either an absolute time or a relative source offset."""

    event: ScheduledSourceEvent
    source_sequence: int
    absolute_time: datetime | None
    relative_offset_ns: int | None


def normalize_sources(
    sources: tuple[ScheduledSource, ...],
    *,
    default_interval_ms: int,
) -> tuple[tuple[SignalEnvelope, ...], ...]:
    """Normalize source timestamps into independently sorted envelope streams.

    Args:
        sources: Sources in their stable configuration order.
        default_interval_ms: Spacing used after untimed records.

    Returns:
        One immutable envelope tuple per source, ready for deterministic merging.

    Raises:
        TimestampNormalizationError: A source identifier, timestamp, or sequence is invalid.
    """

    _validate_sources(sources, default_interval_ms)
    timed_sources = tuple(
        _normalize_source_timeline(source, default_interval_ms) for source in sources
    )
    absolute_times = tuple(
        timed_event.absolute_time
        for timed_source in timed_sources
        for timed_event in timed_source
        if timed_event.absolute_time is not None
    )
    _validate_absolute_time_awareness(absolute_times)
    scenario_absolute_origin = min(absolute_times) if absolute_times else None
    return tuple(
        _create_envelopes(source, timed_source, scenario_absolute_origin)
        for source, timed_source in zip(sources, timed_sources, strict=True)
    )


def _validate_sources(sources: tuple[ScheduledSource, ...], default_interval_ms: int) -> None:
    """Validate source-level invariants before deriving any timestamps."""

    if default_interval_ms < 0:
        raise TimestampNormalizationError("default_interval_ms must not be negative")
    source_ids = [source.source_id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise TimestampNormalizationError("scheduled source identifiers must be unique")
    source_ordinals = [source.source_ordinal for source in sources]
    if len(source_ordinals) != len(set(source_ordinals)):
        raise TimestampNormalizationError("scheduled source ordinals must be unique")
    for source in sources:
        if not source.source_id.strip():
            raise TimestampNormalizationError("scheduled source identifier must not be empty")
        if not source.signal_type.strip():
            raise TimestampNormalizationError(
                f"scheduled source {source.source_id!r} must declare a signal type"
            )
        if not source.events:
            raise TimestampNormalizationError(
                f"scheduled source {source.source_id!r} must contain at least one event"
            )


def _normalize_source_timeline(
    source: ScheduledSource, default_interval_ms: int
) -> tuple[_TimedSourceEvent, ...]:
    """Resolve one source without applying the cross-source absolute origin."""

    normalized: list[_TimedSourceEvent] = []
    current_absolute: datetime | None = None
    current_relative_ns = 0
    relative_only_started = False
    for source_sequence, event in enumerate(source.events):
        _validate_event_time(source.source_id, source_sequence, event)
        if event.timestamp is not None:
            absolute_time = (
                event.timestamp.astimezone(UTC)
                if event.timestamp.utcoffset() is not None
                else event.timestamp
            )
            if relative_only_started:
                raise TimestampNormalizationError(
                    f"source {source.source_id!r} cannot introduce an absolute timestamp after "
                    "relative-only events"
                )
            if current_absolute is not None and absolute_time < current_absolute:
                raise TimestampNormalizationError(
                    f"source {source.source_id!r} timestamp decreases at "
                    f"event {source_sequence + 1}"
                )
            current_absolute = absolute_time
            normalized.append(_TimedSourceEvent(event, source_sequence, current_absolute, None))
            continue
        delay_ms = _event_delay_ms(event, source_sequence, default_interval_ms)
        if current_absolute is not None:
            current_absolute += timedelta(milliseconds=delay_ms)
            normalized.append(
                _TimedSourceEvent(event, source_sequence, current_absolute, None)
            )
            continue
        relative_only_started = True
        current_relative_ns += delay_ms * MILLISECONDS_TO_NANOSECONDS
        normalized.append(
            _TimedSourceEvent(event, source_sequence, None, current_relative_ns)
        )
    return tuple(normalized)


def _validate_event_time(
    source_id: str, source_sequence: int, event: ScheduledSourceEvent
) -> None:
    """Reject event timestamp combinations whose ordering would be ambiguous."""

    if event.timestamp is not None and event.relative_delay_ms is not None:
        raise TimestampNormalizationError(
            f"source {source_id!r} event {source_sequence + 1} cannot have "
            "absolute and relative time"
        )
    if event.relative_delay_ms is not None and event.relative_delay_ms < 0:
        raise TimestampNormalizationError(
            f"source {source_id!r} event {source_sequence + 1} relative delay must not be negative"
        )


def _validate_absolute_time_awareness(absolute_times: tuple[datetime, ...]) -> None:
    """Reject scenarios that mix timezone-aware and timezone-free absolute sources."""

    awareness = {timestamp.utcoffset() is not None for timestamp in absolute_times}
    if len(awareness) > 1:
        raise TimestampNormalizationError(
            "scheduled sources cannot mix timezone-aware and timezone-free absolute timestamps"
        )


def _event_delay_ms(
    event: ScheduledSourceEvent, source_sequence: int, default_interval_ms: int
) -> int:
    """Return legacy-compatible spacing for a relative or untimed event."""

    if source_sequence == 0:
        return 0
    if event.relative_delay_ms is not None:
        return event.relative_delay_ms
    return default_interval_ms


def _create_envelopes(
    source: ScheduledSource,
    timed_source: tuple[_TimedSourceEvent, ...],
    scenario_absolute_origin: datetime | None,
) -> tuple[SignalEnvelope, ...]:
    """Convert one timed source into envelopes sharing the scenario origin."""

    envelopes = tuple(
        SignalEnvelope(
            scenario_offset_ns=_scenario_offset_ns(timed_event, scenario_absolute_origin),
            source_priority=source.priority,
            source_ordinal=source.source_ordinal,
            source_sequence=timed_event.source_sequence,
            source_id=source.source_id,
            signal_type=source.signal_type,
            payload=timed_event.event.payload,
            original_timestamp=timed_event.event.timestamp,
        )
        for timed_event in timed_source
    )
    if any(
        current.scenario_offset_ns < previous.scenario_offset_ns
        for previous, current in zip(envelopes, envelopes[1:])
    ):
        raise TimestampNormalizationError(
            f"source {source.source_id!r} does not normalize to monotonic time"
        )
    return envelopes


def _scenario_offset_ns(
    timed_event: _TimedSourceEvent, scenario_absolute_origin: datetime | None
) -> int:
    """Calculate nanoseconds from the shared absolute or relative scenario origin."""

    if timed_event.absolute_time is None:
        return timed_event.relative_offset_ns or 0
    if scenario_absolute_origin is None:  # pragma: no cover - protected by caller construction
        raise TimestampNormalizationError("absolute event requires a scenario origin")
    difference = timed_event.absolute_time - scenario_absolute_origin
    return (
        difference.days * SECONDS_PER_DAY * SECONDS_TO_NANOSECONDS
        + difference.seconds * SECONDS_TO_NANOSECONDS
        + difference.microseconds * MICROSECONDS_TO_NANOSECONDS
    )
