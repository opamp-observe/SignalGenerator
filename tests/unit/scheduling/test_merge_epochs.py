# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Stable merge ordering and monotonic replay epoch tests."""

from __future__ import annotations

import pytest

from signal_generator.scheduling import (
    SignalEnvelope,
    create_cycle_envelopes,
    merge_envelope_streams,
)


def _envelope(
    payload: str,
    offset_ns: int,
    *,
    priority: int,
    source_ordinal: int,
    source_sequence: int = 0,
) -> SignalEnvelope:
    """Build one envelope with explicit ordering controls."""

    return SignalEnvelope(
        offset_ns,
        priority,
        source_ordinal,
        source_sequence,
        f"source-{source_ordinal}",
        "log",
        payload,
    )


def test_merge_orders_by_time_priority_source_and_sequence() -> None:
    """Every documented tie-break participates in deterministic merge ordering."""

    first_stream = (
        _envelope("first-source-first", 0, priority=20, source_ordinal=0),
        _envelope(
            "first-source-second",
            10,
            priority=10,
            source_ordinal=0,
            source_sequence=1,
        ),
    )
    second_stream = (
        _envelope("priority-winner", 0, priority=10, source_ordinal=1),
        _envelope("source-order-loser", 10, priority=10, source_ordinal=1),
    )

    merged = merge_envelope_streams((first_stream, second_stream))

    assert [envelope.payload for envelope in merged] == [
        "priority-winner",
        "first-source-first",
        "first-source-second",
        "source-order-loser",
    ]


def test_cycle_epochs_advance_after_previous_final_offset() -> None:
    """Loop gaps are measured from the prior final event to the next first event."""

    base = (
        _envelope("first", 5, priority=10, source_ordinal=0),
        _envelope("last", 105, priority=10, source_ordinal=0, source_sequence=1),
    )
    first_cycle = create_cycle_envelopes(
        base,
        cycle=1,
        previous_final_offset_ns=None,
        loop_gap_ms=0,
    )
    second_cycle = create_cycle_envelopes(
        base,
        cycle=2,
        previous_final_offset_ns=first_cycle[-1].scenario_offset_ns,
        loop_gap_ms=2,
    )

    assert [envelope.scenario_offset_ns for envelope in first_cycle] == [0, 100]
    assert [envelope.scenario_offset_ns for envelope in second_cycle] == [2_000_100, 2_000_200]
    assert all(envelope.cycle == 2 for envelope in second_cycle)


def test_zero_loop_gap_still_creates_strictly_monotonic_epoch() -> None:
    """A zero loop gap advances one nanosecond instead of repeating the prior final time."""

    base = (_envelope("only", 0, priority=10, source_ordinal=0),)
    second_cycle = create_cycle_envelopes(
        base,
        cycle=2,
        previous_final_offset_ns=10,
        loop_gap_ms=0,
    )

    assert second_cycle[0].scenario_offset_ns == 11


def test_merge_rejects_unordered_stream() -> None:
    """Callers cannot hide malformed source order inside the heap merge."""

    unordered = (
        _envelope("later", 2, priority=10, source_ordinal=0),
        _envelope("earlier", 1, priority=10, source_ordinal=0, source_sequence=1),
    )

    with pytest.raises(ValueError, match="must be ordered"):
        merge_envelope_streams((unordered,))


@pytest.mark.parametrize(
    ("cycle", "previous_final_offset_ns", "loop_gap_ms", "message"),
    [
        (0, None, 0, "at least one"),
        (1, None, -1, "must not be negative"),
        (1, 0, 0, "must not have"),
        (2, None, 0, "requires"),
    ],
)
def test_cycle_epochs_reject_inconsistent_arguments(
    cycle: int,
    previous_final_offset_ns: int | None,
    loop_gap_ms: int,
    message: str,
) -> None:
    """Cycle creation rejects invalid lifecycle state before shifting envelopes."""

    base = (_envelope("only", 0, priority=10, source_ordinal=0),)

    with pytest.raises(ValueError, match=message):
        create_cycle_envelopes(
            base,
            cycle=cycle,
            previous_final_offset_ns=previous_final_offset_ns,
            loop_gap_ms=loop_gap_ms,
        )


def test_empty_cycle_returns_no_envelopes() -> None:
    """An empty normalized scenario remains empty without manufacturing timestamps."""

    assert (
        create_cycle_envelopes(
            (),
            cycle=1,
            previous_final_offset_ns=None,
            loop_gap_ms=0,
        )
        == ()
    )
