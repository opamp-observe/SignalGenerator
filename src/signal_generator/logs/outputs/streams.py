# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Standard output and error stream adapters."""

from __future__ import annotations

import sys
from typing import TextIO

from signal_generator.logs.models import RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput


class StreamOutput(LogOutput):
    """Write newline-terminated events without taking ownership of the process stream."""

    def __init__(self, stream: TextIO) -> None:
        """Use ``stream`` for writes while leaving its lifecycle owned by the process."""

        self.stream = stream

    async def write(self, event: RenderedLogEvent) -> None:
        """Write one event and a line terminator."""

        self.stream.write(f"{event.text}\n")

    async def flush(self) -> None:
        """Flush the selected process stream."""

        self.stream.flush()


def stdout_output() -> StreamOutput:
    """Create an adapter bound to the current standard output stream."""

    return StreamOutput(sys.stdout)


def stderr_output() -> StreamOutput:
    """Create an adapter bound to the current standard error stream."""

    return StreamOutput(sys.stderr)
