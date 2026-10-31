# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Render parsed events with the original token vocabulary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from signal_generator.logs.models import LogEvent, RenderedLogEvent
from signal_generator.logs.parser import translate_datetime_format


class LogFormatter:
    """Render output tokens with injected wall time for deterministic tests."""

    def __init__(
        self,
        output_format: str,
        datetime_format: str,
        now_provider: Callable[[], datetime] = datetime.now,
    ) -> None:
        """Store the output format, translated date format, and current-time provider."""

        self.output_format = output_format
        self.datetime_format = translate_datetime_format(datetime_format)
        self.now_provider = now_provider

    def render(self, event: LogEvent, cycle: int, record: int) -> RenderedLogEvent:
        """Replace all supported output tokens for one event and cycle position."""

        timestamp = event.timestamp or self.now_provider()
        replacements = {
            "%t": timestamp.strftime(self.datetime_format),
            "%m": event.message,
            "%l": event.log_level,
            "%p": event.process,
            "%c": event.location,
            "%i": str(cycle),
            "%j": str(record),
        }
        rendered = self.output_format
        for token, value in replacements.items():
            rendered = rendered.replace(token, value)
        return RenderedLogEvent(rendered, event, cycle, record)
