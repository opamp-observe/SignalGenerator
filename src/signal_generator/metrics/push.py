# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Push adapter protocol and authenticated Pushgateway implementation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import quote

import httpx

from signal_generator.config.models import PushConfig
from signal_generator.metrics.exposition import PROMETHEUS_CONTENT_TYPE, render_frame
from signal_generator.metrics.models import MetricFrame

HEADER_AUTHORIZATION = "Authorization"
HEADER_CONTENT_TYPE = "Content-Type"


class PushAdapter(Protocol):
    """Transport contract used by the scheduled push loop."""

    async def push(self, frame: MetricFrame) -> None:
        """Replace the configured destination group with one frame."""

    async def close(self) -> None:
        """Release transport resources."""


class PushConfigurationError(ValueError):
    """Report missing secret environment values or invalid push settings."""


class PushgatewayAdapter:
    """Deliver Prometheus text frames to a Pushgateway grouping URL."""

    def __init__(
        self,
        config: PushConfig,
        environ: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Resolve authentication and create or retain an async HTTP client."""

        if not config.url or not config.job:
            raise PushConfigurationError("Pushgateway url and job are required")
        environment = os.environ if environ is None else environ
        headers, auth = _resolve_authentication(config, environment)
        verify = str(config.tls.ca_file) if config.tls.ca_file else config.tls.verify
        self._url = _grouping_url(config.url, config.job, config.grouping_key)
        self._headers = headers
        self._auth = auth
        self._client = client or httpx.AsyncClient(
            timeout=config.timeout_seconds,
            verify=verify,
        )
        self._owns_client = client is None

    async def push(self, frame: MetricFrame) -> None:
        """PUT one rendered snapshot and reject non-success responses."""

        response = await self._client.put(
            self._url,
            content=render_frame(frame),
            headers=self._headers,
            auth=self._auth,
        )
        response.raise_for_status()

    async def close(self) -> None:
        """Close only a client created by this adapter."""

        if self._owns_client:
            await self._client.aclose()


def _grouping_url(base_url: str, job: str, grouping_key: Mapping[str, str]) -> str:
    """Build a deterministic Pushgateway grouping path with escaped segments."""

    segments = [base_url.rstrip("/"), "metrics", "job", quote(job, safe="")]
    for label_name, label_value in sorted(grouping_key.items()):
        segments.extend((quote(label_name, safe=""), quote(label_value, safe="")))
    return "/".join(segments)


def _resolve_authentication(
    config: PushConfig, environment: Mapping[str, str]
) -> tuple[dict[str, str], httpx.BasicAuth | None]:
    """Resolve one mutually exclusive authentication mode from named environment secrets."""

    if config.basic_auth and config.bearer_token_env:
        raise PushConfigurationError("basic_auth and bearer_token_env are mutually exclusive")
    headers = {HEADER_CONTENT_TYPE: PROMETHEUS_CONTENT_TYPE}
    if config.basic_auth:
        password = environment.get(config.basic_auth.password_env)
        if password is None:
            raise PushConfigurationError(
                f"required password environment variable is not set: "
                f"{config.basic_auth.password_env}"
            )
        return headers, httpx.BasicAuth(config.basic_auth.username, password)
    if config.bearer_token_env:
        token = environment.get(config.bearer_token_env)
        if token is None:
            raise PushConfigurationError(
                f"required bearer token environment variable is not set: {config.bearer_token_env}"
            )
        headers[HEADER_AUTHORIZATION] = f"Bearer {token}"
    return headers, None
