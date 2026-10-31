# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Quart blueprint and lifecycle attachment for in-process replay runtimes."""

from __future__ import annotations

import re
from typing import Any

from signal_generator.config.models import AppConfig
from signal_generator.metrics.exposition import PROMETHEUS_CONTENT_TYPE
from signal_generator.runtime import SignalGeneratorRuntime

EXTENSION_KEY = "signal_generator.runtimes"
KEY_RUNTIME_ID = "runtime_id"
KEY_RUNNING = "running"
KEY_READY = "ready"
KEY_RESTART_COUNT = "restart_count"
KEY_ERROR = "error"
KEY_ROUTE_PREFIX = "route_prefix"
KEY_RUNTIME = "runtime"
KEY_METRICS = "metrics"


def attach_signal_generator_runtime(
    app: Any,
    *,
    runtime_id: str,
    config: AppConfig,
    route_prefix: str,
    manage_lifecycle: bool = True,
) -> SignalGeneratorRuntime:
    """Attach one uniquely prefixed runtime and its lifecycle to a Quart application."""

    try:
        from quart import Blueprint, Response, jsonify  # pylint: disable=import-outside-toplevel
    except ModuleNotFoundError as error:  # pragma: no cover - exercised in clean-wheel tests.
        raise RuntimeError("Quart attachment requires signal-generator[quart]") from error
    normalized_prefix = _normalize_prefix(route_prefix)
    runtimes = app.extensions.setdefault(EXTENSION_KEY, {})
    if runtime_id in runtimes:
        raise ValueError(f"duplicate SignalGenerator runtime_id: {runtime_id}")
    if any(item[KEY_ROUTE_PREFIX] == normalized_prefix for item in runtimes.values()):
        raise ValueError(f"duplicate SignalGenerator route_prefix: {normalized_prefix}")
    runtime = SignalGeneratorRuntime(runtime_id, config)
    blueprint_name = f"signal_generator_{re.sub(r'[^a-zA-Z0-9_]', '_', runtime_id)}"
    blueprint = Blueprint(blueprint_name, __name__, url_prefix=normalized_prefix)

    @blueprint.get("/metrics")
    async def metrics_route() -> Any:
        """Render one replay frame through the host listener."""

        return Response(runtime.render_metrics(), content_type=PROMETHEUS_CONTENT_TYPE)

    @blueprint.get("/healthz")
    async def health_route() -> Any:
        """Report in-memory liveness without advancing replay state."""

        return jsonify(_health_payload(runtime))

    @blueprint.get("/readyz")
    async def readiness_route() -> Any:
        """Report readiness with a service-unavailable status when false."""

        health = runtime.health()
        return jsonify(_health_payload(runtime)), 200 if health.ready else 503

    @blueprint.get("/")
    async def root_route() -> Any:
        """Identify the runtime and its prefixed metrics route."""

        return jsonify({KEY_RUNTIME_ID: runtime_id, KEY_METRICS: f"{normalized_prefix}/metrics"})

    app.register_blueprint(blueprint)
    runtimes[runtime_id] = {
        KEY_RUNTIME: runtime,
        KEY_ROUTE_PREFIX: normalized_prefix,
    }

    if manage_lifecycle:
        _register_lifecycle(app, runtime)

    return runtime


def _register_lifecycle(app: Any, runtime: SignalGeneratorRuntime) -> None:
    """Register host lifecycle hooks when the adapter is not coordinating them itself."""

    @app.before_serving
    async def start_attached_runtime() -> None:
        """Start this runtime on Quart's active event loop."""

        await runtime.start()

    @app.after_serving
    async def stop_attached_runtime() -> None:
        """Await runtime cleanup before Quart completes shutdown."""

        await runtime.stop()


def _normalize_prefix(route_prefix: str) -> str:
    """Normalize and validate a non-root URL prefix."""

    normalized = route_prefix.strip().rstrip("/")
    if not normalized.startswith("/") or normalized == "":
        raise ValueError("route_prefix must be an absolute non-root path")
    if normalized in {"/", "/healthz", "/readyz"}:
        raise ValueError(f"route_prefix is reserved: {normalized}")
    return normalized


def _health_payload(runtime: SignalGeneratorRuntime) -> dict[str, Any]:
    """Serialize immutable health for host routes and adapter inspection."""

    health = runtime.health()
    return {
        KEY_RUNTIME_ID: health.runtime_id,
        KEY_RUNNING: health.running,
        KEY_READY: health.ready,
        KEY_RESTART_COUNT: health.restart_count,
        KEY_ERROR: health.error,
    }
