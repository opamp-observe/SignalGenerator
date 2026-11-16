# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Immutable source and envelope models used by the shared scenario scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ScheduledSourceEvent:
    """Describe one source event before its timestamp is normalized.

    Attributes:
        payload: Domain object delivered when the event becomes due.
        timestamp: Optional timezone-aware absolute source timestamp.
        relative_delay_ms: Optional delay from the preceding event in this source.
    """

    payload: object
    timestamp: datetime | None = None
    relative_delay_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ScheduledSource:
    """Group one ordered signal source and its deterministic merge controls.

    Attributes:
        source_id: Unique identifier used in diagnostics and effective configuration.
        signal_type: Domain name such as ``log`` or ``metric_push``.
        priority: Lower values win when source timestamps are equal.
        source_ordinal: Stable configuration order used after priority tie-breaking.
        events: Events in their original source order.
    """

    source_id: str
    signal_type: str
    priority: int
    source_ordinal: int
    events: tuple[ScheduledSourceEvent, ...]


@dataclass(frozen=True, slots=True, order=True)
class SignalEnvelope:
    """Hold one normalized event with a complete deterministic ordering key.

    Attributes:
        scenario_offset_ns: Nanoseconds from the scenario's normalized first event.
        source_priority: Configured cross-source priority; lower values run first.
        source_ordinal: Stable source configuration order.
        source_sequence: Zero-based sequence within the source.
        source_id: Source identifier retained for diagnostics.
        signal_type: Domain dispatcher key.
        payload: Domain event delivered by the scheduler.
        original_timestamp: Explicit absolute source timestamp when one was supplied.
        cycle: One-based replay cycle number.
    """

    scenario_offset_ns: int
    source_priority: int
    source_ordinal: int
    source_sequence: int
    source_id: str = field(compare=False)
    signal_type: str = field(compare=False)
    payload: object = field(compare=False)
    original_timestamp: datetime | None = field(default=None, compare=False)
    cycle: int = field(default=1, compare=False)
