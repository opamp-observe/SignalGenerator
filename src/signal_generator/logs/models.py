# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Immutable parsed and rendered log event models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LogEvent:
    """One parsed source record before cycle counters and output formatting are applied."""

    source_index: int
    message: str
    timestamp: datetime | None = None
    relative_delay_ms: int | None = None
    log_level: str = "INFO"
    process: str = "Thread-1"
    location: str = "signal_generator"


@dataclass(frozen=True, slots=True)
class RenderedLogEvent:
    """One output-ready text payload with its source event and replay counters."""

    text: str
    event: LogEvent
    cycle: int
    record: int
