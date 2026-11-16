# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Bounded loader for OTLP JSON export requests stored one per line."""

# pylint: disable=duplicate-code

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from signal_generator.config.models import TraceSourceConfig

TIMESTAMP_KEYS = frozenset({"startTimeUnixNano", "endTimeUnixNano", "timeUnixNano"})


class TraceDataError(ValueError):
    """Report invalid or unsafe OTLP JSON Lines input."""


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """One OTLP export request and its earliest timestamp."""

    payload: dict[str, Any]
    first_timestamp_unix_nano: int


def load_trace_records(config: TraceSourceConfig) -> tuple[TraceRecord, ...]:
    """Load and minimally validate all non-empty OTLP JSON Lines records."""

    records: list[TraceRecord] = []
    with config.path.open("r", encoding=config.encoding) as source_file:
        for line_number, raw_line in enumerate(source_file, start=1):
            if not raw_line.strip():
                continue
            if len(raw_line.encode(config.encoding)) > config.maximum_line_bytes:
                raise TraceDataError(f"line {line_number} exceeds maximum_line_bytes")
            records.append(_parse_record(raw_line, line_number))
    if not records:
        raise TraceDataError("trace source contains no records")
    return tuple(records)


def _parse_record(raw_line: str, line_number: int) -> TraceRecord:
    """Parse one request and require OTLP resource spans with timestamped spans."""

    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError as error:
        raise TraceDataError(f"line {line_number}: invalid JSON: {error.msg}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("resourceSpans"), list):
        raise TraceDataError(f"line {line_number}: resourceSpans must be an array")
    timestamps = list(iter_timestamp_values(payload))
    if not timestamps:
        raise TraceDataError(f"line {line_number}: no OTLP span or event timestamps found")
    return TraceRecord(payload, min(timestamps))


def iter_timestamp_values(value: Any):
    """Yield integer nanosecond timestamps from nested OTLP JSON objects."""

    if isinstance(value, dict):
        for key, child in value.items():
            if key in TIMESTAMP_KEYS:
                try:
                    timestamp = int(child)
                except (TypeError, ValueError) as error:
                    raise TraceDataError(f"{key} must be an integer string") from error
                if timestamp < 0:
                    raise TraceDataError(f"{key} must not be negative")
                yield timestamp
            else:
                yield from iter_timestamp_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_timestamp_values(child)
