# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Merge normalized envelope streams without losing deterministic tie-breaking."""

from __future__ import annotations

import heapq

from signal_generator.scheduling.models import SignalEnvelope


def merge_envelope_streams(
    streams: tuple[tuple[SignalEnvelope, ...], ...],
) -> tuple[SignalEnvelope, ...]:
    """Return a stable time, priority, source, and sequence ordered scenario.

    Args:
        streams: Individually time-ordered source envelope sequences.

    Returns:
        A single immutable deterministic scenario sequence.

    Raises:
        ValueError: An input stream is not already ordered.
    """

    for stream in streams:
        if any(current < previous for previous, current in zip(stream, stream[1:])):
            raise ValueError("envelope streams must be ordered before merging")
    return tuple(heapq.merge(*streams))
