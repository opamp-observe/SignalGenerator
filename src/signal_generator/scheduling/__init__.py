# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Shared deterministic scheduling primitives for time-driven signal replay."""

from signal_generator.scheduling.epochs import create_cycle_envelopes
from signal_generator.scheduling.merge import merge_envelope_streams
from signal_generator.scheduling.models import (
    ScheduledSource,
    ScheduledSourceEvent,
    SignalEnvelope,
)
from signal_generator.scheduling.normalization import (
    TimestampNormalizationError,
    normalize_sources,
)

__all__ = [
    "ScheduledSource",
    "ScheduledSourceEvent",
    "SignalEnvelope",
    "TimestampNormalizationError",
    "create_cycle_envelopes",
    "merge_envelope_streams",
    "normalize_sources",
]
