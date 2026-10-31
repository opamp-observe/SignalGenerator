# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Host-independent lifecycle for embedding SignalGenerator in an async application."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from signal_generator.config.models import AppConfig
from signal_generator.logs.scheduler import replay_logs
from signal_generator.metrics.exposition import render_registry
from signal_generator.metrics.runtime import MetricReplayRuntime


@dataclass(frozen=True, slots=True)
class RuntimeHealth:
    """Immutable in-memory runtime health returned without consuming signals."""

    runtime_id: str
    running: bool
    ready: bool
    restart_count: int
    error: str | None = None


class SignalGeneratorRuntime:
    """Own replay tasks without process signals, listeners, or event-loop creation."""

    def __init__(self, runtime_id: str, config: AppConfig) -> None:
        """Create a stopped runtime for one validated configuration."""

        if not runtime_id.strip():
            raise ValueError("runtime_id must not be empty")
        self.runtime_id = runtime_id
        self.config = config
        self._stop_event = asyncio.Event()
        self._metric_runtime: MetricReplayRuntime | None = None
        self._log_task: asyncio.Task[int] | None = None
        self._running = False
        self._ready = False
        self._restart_count = 0
        self._error: str | None = None
        self._lifecycle_lock = asyncio.Lock()

    @property
    def metric_runtime(self) -> MetricReplayRuntime | None:
        """Return the attached metric runtime for host route rendering."""

        return self._metric_runtime

    async def start(self) -> None:
        """Start enabled replay resources on the caller's active event loop."""

        async with self._lifecycle_lock:
            if self._running:
                return
            self._stop_event = asyncio.Event()
            self._error = None
            try:
                await self._start_resources()
            except Exception as error:
                self._error = str(error)
                await self._stop_resources()
                raise
            self._running = True
            self._ready = True

    async def _start_resources(self) -> None:
        """Construct metric resources before scheduling logs."""

        if self.config.metrics and self.config.metrics.enabled:
            self._metric_runtime = MetricReplayRuntime(
                self.config.metrics,
                serve_pull_http=False,
            )
            await self._metric_runtime.start(self._stop_event)
        if self.config.logs and self.config.logs.enabled:
            self._log_task = asyncio.create_task(
                replay_logs(self.config.logs, stop_event=self._stop_event),
                name=f"signal-generator-logs-{self.runtime_id}",
            )

    async def stop(self) -> None:
        """Stop and await every owned task; repeated calls are safe."""

        async with self._lifecycle_lock:
            if not self._running and self._metric_runtime is None and self._log_task is None:
                return
            self._ready = False
            self._stop_event.set()
            await self._stop_resources()
            self._running = False

    async def _stop_resources(self) -> None:
        """Release log and metric resources in bounded ownership order."""

        if self._log_task:
            await self._log_task
            self._log_task = None
        if self._metric_runtime:
            await self._metric_runtime.close(self._stop_event)
            self._metric_runtime = None

    async def apply_config(self, candidate: AppConfig) -> None:
        """Logically restart with a validated candidate, rolling back on startup failure."""

        previous = self.config
        was_running = self._running
        if was_running:
            await self.stop()
        self.config = candidate
        self._restart_count += 1
        if not was_running:
            return
        try:
            await self.start()
        except Exception:
            self.config = previous
            await self.start()
            raise

    def render_metrics(self) -> bytes:
        """Render and advance exactly one frame for the host's metrics route."""

        metric_runtime = self._metric_runtime
        if metric_runtime is None or metric_runtime.registry is None:
            raise RuntimeError("runtime does not expose pull metrics")
        return render_registry(metric_runtime.registry)

    def health(self) -> RuntimeHealth:
        """Return in-memory state without collecting a metric frame."""

        metric_ready = self._metric_runtime is None or self._metric_runtime.ready
        log_ready = self._log_task is None or not self._log_task.done()
        ready = self._ready and metric_ready and log_ready
        return RuntimeHealth(
            self.runtime_id,
            self._running,
            ready,
            self._restart_count,
            self._error,
        )
