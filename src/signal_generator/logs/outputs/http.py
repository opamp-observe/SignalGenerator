# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Bounded asynchronous HTTP log output."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from signal_generator.logs.models import RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput


class HttpOutput(LogOutput):
    """Send each rendered event as one checked HTTP request."""

    def __init__(
        self,
        url: str,
        method: str = "POST",
        headers: Mapping[str, str] | None = None,
        content_type: str = "text/plain; charset=utf-8",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Store the target request contract and bounded timeout."""

        self.url = url
        self.method = method
        self.headers = dict(headers or {})
        self.headers.setdefault("content-type", content_type)
        self.timeout_seconds = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        """Create the reusable HTTP client without sending a request."""

        self._client = httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False)

    async def write(self, event: RenderedLogEvent) -> None:
        """Send one event and raise for non-success status responses."""

        if self._client is None:
            raise RuntimeError("HTTP output is not open")
        response = await self._client.request(
            self.method, self.url, headers=self.headers, content=event.text.encode("utf-8")
        )
        response.raise_for_status()

    async def close(self) -> None:
        """Close the reusable HTTP client."""

        if self._client is not None:
            await self._client.aclose()
            self._client = None
