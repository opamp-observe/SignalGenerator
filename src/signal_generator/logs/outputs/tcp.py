# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Asynchronous TCP stream output."""

from __future__ import annotations

import asyncio

from signal_generator.logs.models import RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput


class TcpOutput(LogOutput):
    """Own one TCP connection and send delimited UTF-8 event payloads."""

    def __init__(
        self, host: str, port: int, timeout_seconds: float = 5.0, delimiter: str = "\n"
    ) -> None:
        """Store target address, connection timeout, and record delimiter."""

        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.delimiter = delimiter
        self._writer: asyncio.StreamWriter | None = None

    async def open(self) -> None:
        """Open the TCP connection within the configured timeout."""

        _, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self.timeout_seconds
        )

    async def write(self, event: RenderedLogEvent) -> None:
        """Write and drain one delimited event."""

        if self._writer is None:
            raise RuntimeError("TCP output is not open")
        self._writer.write(f"{event.text}{self.delimiter}".encode())
        await self._writer.drain()

    async def close(self) -> None:
        """Close the connection and await transport shutdown."""

        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
