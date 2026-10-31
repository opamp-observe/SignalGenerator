# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Lifecycle protocol shared by synchronous and network log outputs."""

from __future__ import annotations

from abc import ABC, abstractmethod

from signal_generator.logs.models import RenderedLogEvent


class LogOutput(ABC):
    """Define the async lifecycle required by the replay scheduler."""

    async def open(self) -> None:
        """Acquire output resources before the first event is written."""

    @abstractmethod
    async def write(self, event: RenderedLogEvent) -> None:
        """Write one rendered event or raise an exception for the scheduler policy."""

    async def flush(self) -> None:
        """Flush buffered data at a cycle or shutdown boundary."""

    async def close(self) -> None:
        """Release resources after replay finishes or fails."""
