# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Python logging output adapter and JUL compatibility replacement."""

from __future__ import annotations

import logging

from signal_generator.logs.models import RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput


class PythonLoggingOutput(LogOutput):
    """Publish rendered events through a named Python logger."""

    def __init__(self, logger_name: str, level: str = "INFO") -> None:
        """Resolve the named logger and configured Python level."""

        self.logger = logging.getLogger(logger_name)
        resolved_level = logging.getLevelName(level.upper())
        self.level = resolved_level if isinstance(resolved_level, int) else logging.INFO

    async def write(self, event: RenderedLogEvent) -> None:
        """Emit the event without interpolating its text as a format string."""

        self.logger.log(self.level, "%s", event.text)
