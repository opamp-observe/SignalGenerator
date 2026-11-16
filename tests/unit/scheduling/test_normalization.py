# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Timestamp normalization tests for absolute, relative, and untimed sources."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from signal_generator.scheduling import (
    ScheduledSource,
    ScheduledSourceEvent,
    TimestampNormalizationError,
    normalize_sources,
)


def _source(
    source_id: str,
    events: tuple[ScheduledSourceEvent, ...],
    *,
    priority: int = 100,
    source_ordinal: int = 0,
) -> ScheduledSource:
    """Build one log source with concise defaults for focused tests."""

    return ScheduledSource(source_id, "log", priority, source_ordinal, events)


def test_normalizes_absolute_sources_against_earliest_utc_timestamp() -> None:
    """Timezone offsets share one UTC origin while retaining explicit source timestamps."""

    utc_start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    offset_start = datetime(2026, 1, 1, 11, 0, 1, tzinfo=timezone_plus_one())
    streams = normalize_sources(
        (
            _source("utc", (ScheduledSourceEvent("first", timestamp=utc_start),)),
            _source(
                "offset",
                (ScheduledSourceEvent("second", timestamp=offset_start),),
                source_ordinal=1,
            ),
        ),
        default_interval_ms=1000,
    )

    assert streams[0][0].scenario_offset_ns == 0
    assert streams[1][0].scenario_offset_ns == 1_000_000_000
    assert streams[1][0].original_timestamp == offset_start


def timezone_plus_one() -> timezone:
    """Return a fixed one-hour offset without hiding it in test data."""

    return timezone(timedelta(hours=1))


def test_normalizes_relative_and_untimed_events_with_legacy_first_event_semantics() -> None:
    """The first event is immediate and later absent times use the configured interval."""

    source = _source(
        "relative",
        (
            ScheduledSourceEvent("first", relative_delay_ms=999),
            ScheduledSourceEvent("second", relative_delay_ms=25),
            ScheduledSourceEvent("third"),
        ),
    )

    stream = normalize_sources((source,), default_interval_ms=100)[0]

    assert [envelope.scenario_offset_ns for envelope in stream] == [0, 25_000_000, 125_000_000]


def test_relative_events_after_absolute_time_remain_on_absolute_timeline() -> None:
    """Relative delays following an absolute anchor participate in cross-source alignment."""

    absolute_start = datetime(2026, 1, 1, tzinfo=UTC)
    source = _source(
        "mixed",
        (
            ScheduledSourceEvent("first", timestamp=absolute_start),
            ScheduledSourceEvent("second", relative_delay_ms=250),
        ),
    )

    stream = normalize_sources((source,), default_interval_ms=1000)[0]

    assert [envelope.scenario_offset_ns for envelope in stream] == [0, 250_000_000]


@pytest.mark.parametrize(
    ("events", "message"),
    [
        (
            (
                ScheduledSourceEvent(
                    "both",
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                    relative_delay_ms=1,
                ),
            ),
            "absolute and relative",
        ),
        (
            (ScheduledSourceEvent("negative", relative_delay_ms=-1),),
            "must not be negative",
        ),
        (
            (
                ScheduledSourceEvent("relative"),
                ScheduledSourceEvent("absolute", timestamp=datetime(2026, 1, 1, tzinfo=UTC)),
            ),
            "cannot introduce an absolute timestamp",
        ),
    ],
)
def test_rejects_ambiguous_or_invalid_source_time(
    events: tuple[ScheduledSourceEvent, ...], message: str
) -> None:
    """Invalid timestamp forms fail before any runtime resource is opened."""

    with pytest.raises(TimestampNormalizationError, match=message):
        normalize_sources((_source("invalid", events),), default_interval_ms=1000)


def test_rejects_decreasing_absolute_time() -> None:
    """A source cannot silently reorder absolute records during normalization."""

    later = datetime(2026, 1, 2, tzinfo=UTC)
    earlier = datetime(2026, 1, 1, tzinfo=UTC)
    source = _source(
        "decreasing",
        (
            ScheduledSourceEvent("later", timestamp=later),
            ScheduledSourceEvent("earlier", timestamp=earlier),
        ),
    )

    with pytest.raises(TimestampNormalizationError, match="decreases"):
        normalize_sources((source,), default_interval_ms=1000)


def test_rejects_mixed_timezone_awareness_across_sources() -> None:
    """Aware and timezone-free sources cannot be compared without an explicit timezone policy."""

    aware = _source(
        "aware",
        (ScheduledSourceEvent("aware", timestamp=datetime(2026, 1, 1, tzinfo=UTC)),),
    )
    naive = _source(
        "naive",
        (ScheduledSourceEvent("naive", timestamp=datetime(2026, 1, 1)),),
        source_ordinal=1,
    )

    with pytest.raises(TimestampNormalizationError, match="cannot mix"):
        normalize_sources((aware, naive), default_interval_ms=1000)


@pytest.mark.parametrize(
    ("sources", "default_interval_ms", "message"),
    [
        (
            (
                _source("duplicate", (ScheduledSourceEvent("one"),)),
                _source(
                    "duplicate",
                    (ScheduledSourceEvent("two"),),
                    source_ordinal=1,
                ),
            ),
            1,
            "identifiers must be unique",
        ),
        (
            (
                _source("one", (ScheduledSourceEvent("one"),)),
                _source("two", (ScheduledSourceEvent("two"),)),
            ),
            1,
            "ordinals must be unique",
        ),
        ((_source("", (ScheduledSourceEvent("one"),)),), 1, "must not be empty"),
        (
            (ScheduledSource("one", "", 1, 0, (ScheduledSourceEvent("one"),)),),
            1,
            "signal type",
        ),
        ((ScheduledSource("one", "log", 1, 0, ()),), 1, "at least one event"),
        ((_source("one", (ScheduledSourceEvent("one"),)),), -1, "default_interval_ms"),
    ],
)
def test_rejects_invalid_source_definitions(
    sources: tuple[ScheduledSource, ...], default_interval_ms: int, message: str
) -> None:
    """Source identities, order, content, and default timing are validated together."""

    with pytest.raises(TimestampNormalizationError, match=message):
        normalize_sources(sources, default_interval_ms=default_interval_ms)
