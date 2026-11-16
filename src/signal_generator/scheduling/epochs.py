# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Create strictly monotonic replay-cycle epochs from a normalized scenario."""

from __future__ import annotations

from dataclasses import replace

from signal_generator.scheduling.models import SignalEnvelope

MILLISECONDS_TO_NANOSECONDS = 1_000_000
MINIMUM_EPOCH_ADVANCE_NS = 1


def create_cycle_envelopes(
    base_envelopes: tuple[SignalEnvelope, ...],
    *,
    cycle: int,
    previous_final_offset_ns: int | None,
    loop_gap_ms: int,
) -> tuple[SignalEnvelope, ...]:
    """Shift a normalized scenario into a monotonic replay-cycle epoch.

    Args:
        base_envelopes: One merged cycle whose first event is the scenario origin.
        cycle: One-based output cycle number.
        previous_final_offset_ns: Final offset of the preceding emitted cycle, if any.
        loop_gap_ms: Configured delay between the prior final and next first event.

    Returns:
        New immutable envelopes carrying the requested cycle and shifted offsets.

    Raises:
        ValueError: Cycle, gap, or normalized envelope invariants are invalid.
    """

    _validate_cycle_arguments(cycle, previous_final_offset_ns, loop_gap_ms)
    if not base_envelopes:
        return ()
    epoch_shift_ns = _epoch_shift_ns(
        base_envelopes[0].scenario_offset_ns,
        cycle,
        previous_final_offset_ns,
        loop_gap_ms,
    )
    return tuple(
        replace(
            envelope,
            scenario_offset_ns=envelope.scenario_offset_ns + epoch_shift_ns,
            cycle=cycle,
        )
        for envelope in base_envelopes
    )


def _validate_cycle_arguments(
    cycle: int, previous_final_offset_ns: int | None, loop_gap_ms: int
) -> None:
    """Reject inconsistent cycle state before creating shifted envelopes."""

    if cycle < 1:
        raise ValueError("cycle must be at least one")
    if loop_gap_ms < 0:
        raise ValueError("loop_gap_ms must not be negative")
    if cycle == 1 and previous_final_offset_ns is not None:
        raise ValueError("first cycle must not have a previous final offset")
    if cycle > 1 and previous_final_offset_ns is None:
        raise ValueError("repeated cycle requires the previous final offset")


def _epoch_shift_ns(
    first_offset_ns: int,
    cycle: int,
    previous_final_offset_ns: int | None,
    loop_gap_ms: int,
) -> int:
    """Calculate the offset that places one cycle after its predecessor."""

    if cycle == 1:
        return -first_offset_ns
    epoch_advance_ns = max(
        loop_gap_ms * MILLISECONDS_TO_NANOSECONDS,
        MINIMUM_EPOCH_ADVANCE_NS,
    )
    return int(previous_final_offset_ns) + epoch_advance_ns - first_offset_ns
