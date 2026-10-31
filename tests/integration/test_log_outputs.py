# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Local file, TCP, HTTP, stream, and logging output integration tests."""

from __future__ import annotations

import asyncio
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path

import pytest

from signal_generator.logs.models import LogEvent, RenderedLogEvent
from signal_generator.logs.outputs.file import FileOutput
from signal_generator.logs.outputs.http import HttpOutput
from signal_generator.logs.outputs.python_logging import PythonLoggingOutput
from signal_generator.logs.outputs.streams import StreamOutput
from signal_generator.logs.outputs.tcp import TcpOutput


def _event(text: str = "payload") -> RenderedLogEvent:
    """Create one output-ready event for adapter integration tests."""

    return RenderedLogEvent(text, LogEvent(1, text), 1, 1)


@pytest.mark.asyncio
async def test_file_and_stream_outputs(tmp_path: Path) -> None:
    """File and stream adapters preserve exact text and newline boundaries."""

    output_path = tmp_path / "nested" / "output.log"
    file_output = FileOutput(str(output_path), mode="overwrite")
    await file_output.open()
    await file_output.write(_event())
    await file_output.close()
    assert output_path.read_bytes() == b"payload\n"
    stream = StringIO()
    stream_output = StreamOutput(stream)
    await stream_output.write(_event("stream"))
    await stream_output.flush()
    assert stream.getvalue() == "stream\n"


@pytest.mark.asyncio
async def test_tcp_output_uses_delimiter() -> None:
    """TCP output connects locally and drains one delimiter-terminated event."""

    received = bytearray()

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Capture one record and close the local test connection."""

        received.extend(await reader.readuntil(b"|"))
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    output = TcpOutput("127.0.0.1", port, delimiter="|")
    await output.open()
    await output.write(_event("tcp"))
    await output.close()
    server.close()
    await server.wait_closed()
    assert bytes(received) == b"tcp|"


class _RequestHandler(BaseHTTPRequestHandler):
    """Capture POST bodies without producing server access logs."""

    body = b""

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Read one request body and return a no-content success response."""

        length = int(self.headers["content-length"])
        type(self).body = self.rfile.read(length)
        self.send_response(204)
        self.end_headers()

    def log_message(self, output_format: str, *arguments: object) -> None:
        """Suppress noisy local test-server access logging."""

        del output_format, arguments


@pytest.mark.asyncio
async def test_http_output_posts_locally() -> None:
    """HTTP output sends exact UTF-8 content to a local bounded request server."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _RequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = HttpOutput(f"http://127.0.0.1:{server.server_port}/events")
    try:
        await output.open()
        await output.write(_event("http payload"))
        await output.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    assert _RequestHandler.body == b"http payload"


@pytest.mark.asyncio
async def test_python_logging_output(caplog: pytest.LogCaptureFixture) -> None:
    """Python logging output emits through the configured logger and level."""

    caplog.set_level(logging.WARNING, logger="test.replay")
    output = PythonLoggingOutput("test.replay", "WARNING")
    await output.write(_event("warning payload"))
    assert caplog.messages == ["warning payload"]
