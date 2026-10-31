# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Small standalone asyncio HTTP server for pull and lifecycle endpoints."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from prometheus_client import CollectorRegistry

from signal_generator.config.models import PullConfig
from signal_generator.metrics.exposition import (
    PROMETHEUS_CONTENT_TYPE,
    ReplaySelfMetrics,
    render_registry,
)

MAXIMUM_REQUEST_HEADER_BYTES = 16_384
KEY_STATUS = "status"
KEY_SERVICE = "service"
KEY_METRICS_ROUTE = "metrics"


class MetricHttpServer:
    """Serve one isolated metric registry and non-consuming lifecycle routes."""

    def __init__(
        self,
        config: PullConfig,
        registry: CollectorRegistry,
        self_metrics: ReplaySelfMetrics,
        readiness: Callable[[], bool],
    ) -> None:
        """Create a stopped server with its complete route dependencies."""

        self._config = config
        self._registry = registry
        self._self_metrics = self_metrics
        self._readiness = readiness
        self._server: asyncio.AbstractServer | None = None

    @property
    def bound_port(self) -> int | None:
        """Return the actual bound port, including an OS-selected test port."""

        if self._server is None or not self._server.sockets:
            return None
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        """Bind the configured host and port."""

        self._server = await asyncio.start_server(
            self._handle_connection,
            self._config.host,
            self._config.port,
        )

    async def close(self) -> None:
        """Stop accepting connections and wait for the listener to close."""

        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Read one GET request, dispatch it, and close the connection."""

        try:
            request = await reader.readuntil(b"\r\n\r\n")
            if len(request) > MAXIMUM_REQUEST_HEADER_BYTES:
                response = _response(431, b"request headers too large\n", "text/plain")
            else:
                response = self._dispatch(request.split(b"\r\n", maxsplit=1)[0])
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            response = _response(400, b"bad request\n", "text/plain")
        writer.write(response)
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def _dispatch(self, request_line: bytes) -> bytes:
        """Dispatch a request line without allowing health routes to collect metrics."""

        parts = request_line.decode("ascii", errors="replace").split()
        if len(parts) != 3 or parts[0] != "GET":
            return _response(405, b"method not allowed\n", "text/plain")
        path = parts[1].split("?", maxsplit=1)[0]
        if path == self._config.path:
            return self._metrics_response()
        if path == "/healthz":
            return _json_response(200, {KEY_STATUS: "healthy"})
        if path == "/readyz":
            ready = self._readiness()
            return _json_response(
                200 if ready else 503,
                {KEY_STATUS: "ready" if ready else "not_ready"},
            )
        if path == "/":
            return _json_response(
                200,
                {KEY_SERVICE: "signal-generator", KEY_METRICS_ROUTE: self._config.path},
            )
        return _response(404, b"not found\n", "text/plain")

    def _metrics_response(self) -> bytes:
        """Render one frame and classify an exhausted/error cursor as a scrape failure."""

        try:
            payload = render_registry(self._registry)
        except RuntimeError as error:
            self._self_metrics.pull_failure()
            return _response(500, f"metric replay failed: {error}\n".encode(), "text/plain")
        return _response(200, payload, PROMETHEUS_CONTENT_TYPE)


def _json_response(status: int, document: dict[str, str]) -> bytes:
    """Serialize a compact deterministic JSON HTTP response."""

    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return _response(status, payload, "application/json")


def _response(status: int, payload: bytes, content_type: str) -> bytes:
    """Build a complete HTTP/1.1 close-delimited response."""

    reason = {
        200: "OK",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
        431: "Request Header Fields Too Large",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }[status]
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    return headers + payload
