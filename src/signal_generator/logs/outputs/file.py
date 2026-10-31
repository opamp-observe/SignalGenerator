# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""UTF-8 file output adapter."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from signal_generator.logs.models import RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput


class FileOutput(LogOutput):
    """Own a configured output file and optional per-event flush behavior."""

    def __init__(self, path: str, mode: str = "append", flush_each_event: bool = True) -> None:
        """Store file location, append/overwrite mode, and flush policy."""

        self.path = Path(path)
        self.mode = "a" if mode == "append" else "w"
        self.flush_each_event = flush_each_event
        self._file: TextIO | None = None

    async def open(self) -> None:
        """Create parent directories and open the UTF-8 output file."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open(self.mode, encoding="utf-8", newline="\n")

    async def write(self, event: RenderedLogEvent) -> None:
        """Write one newline-terminated event to the opened file."""

        if self._file is None:
            raise RuntimeError("file output is not open")
        self._file.write(f"{event.text}\n")
        if self.flush_each_event:
            self._file.flush()

    async def flush(self) -> None:
        """Flush buffered file content when the file is open."""

        if self._file is not None:
            self._file.flush()

    async def close(self) -> None:
        """Close the owned file and clear its handle."""

        if self._file is not None:
            self._file.close()
            self._file = None
