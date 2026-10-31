# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Coordinated lifecycle for metric loading, pull serving, and scheduled push."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from signal_generator.config.models import MetricsConfig
from signal_generator.metrics.exposition import ReplaySelfMetrics, create_pull_registry
from signal_generator.metrics.push import PushAdapter, PushgatewayAdapter
from signal_generator.metrics.push_scheduler import PushLoopControl, run_push_loop
from signal_generator.metrics.server import MetricHttpServer
from signal_generator.metrics.source import load_metric_frames
from signal_generator.metrics.store import FrameCursor, FrameStore


class MetricReplayRuntime:
    """Own independent pull/push cursors and all metric transport resources."""

    def __init__(
        self,
        config: MetricsConfig,
        *,
        environ: Mapping[str, str] | None = None,
        push_adapter: PushAdapter | None = None,
        serve_pull_http: bool = True,
    ) -> None:
        """Load frames and prepare resources without binding a listener."""

        if not config.enabled:
            raise ValueError("metric runtime requires metrics.enabled")
        if config.source is None:
            raise ValueError("metric runtime requires a source")
        frames = load_metric_frames(config.source)
        self.config = config
        self.store = FrameStore(frames)
        self.self_metrics = ReplaySelfMetrics()
        self.pull_cursor: FrameCursor | None = None
        self.push_cursor: FrameCursor | None = None
        self.server: MetricHttpServer | None = None
        self.registry = None
        self._push_adapter = push_adapter
        self._environ = environ
        self._push_task: asyncio.Task[int] | None = None
        self._ready = False
        self._serve_pull_http = serve_pull_http
        self._configure_pull()
        self._configure_push()

    @property
    def ready(self) -> bool:
        """Return whether startup completed and no push task failed unexpectedly."""

        return self._ready and not (
            self._push_task is not None
            and self._push_task.done()
            and self._push_task.exception() is not None
        )

    def _configure_pull(self) -> None:
        """Create a dedicated pull cursor, registry, and server when enabled."""

        if not self.config.pull.enabled:
            return
        self.pull_cursor = self.store.cursor(self.config.source.eof, "pull")
        self.registry = create_pull_registry(
            self.pull_cursor,
            self.self_metrics,
            self.config.pull.include_self_metrics,
        )
        if not self._serve_pull_http:
            return
        self.server = MetricHttpServer(
            self.config.pull,
            self.registry,
            self.self_metrics,
            lambda: self.ready,
        )

    def _configure_push(self) -> None:
        """Create an independent push cursor and default adapter when enabled."""

        if not self.config.push.enabled:
            return
        self.push_cursor = self.store.cursor(self.config.source.eof, "push")
        if self._push_adapter is None:
            self._push_adapter = PushgatewayAdapter(self.config.push, self._environ)

    async def start(self, stop_event: asyncio.Event) -> None:
        """Bind pull first, then launch the push task, and become ready."""

        if self.server:
            await self.server.start()
        if self.push_cursor and self._push_adapter:
            self._push_task = asyncio.create_task(
                run_push_loop(
                    self.config.push,
                    self.push_cursor,
                    self._push_adapter,
                    PushLoopControl(self.self_metrics, stop_event),
                ),
                name="signal-generator-push",
            )
        self._ready = True

    async def wait(self, stop_event: asyncio.Event) -> int:
        """Wait for shutdown while pull is serving or for a push-only task to finish."""

        if self.server:
            await stop_event.wait()
            return 0 if self._push_task is None else _task_result_if_done(self._push_task)
        if self._push_task:
            return await self._push_task
        raise ValueError("metrics require pull or push to be enabled")

    async def close(self, stop_event: asyncio.Event) -> None:
        """Request push shutdown and release listener and transport resources."""

        self._ready = False
        stop_event.set()
        if self._push_task:
            await self._push_task
            self._push_task = None
        if self.server:
            await self.server.close()


def _task_result_if_done(task: asyncio.Task[int]) -> int:
    """Return a completed task result without blocking a pull-only shutdown path."""

    return task.result() if task.done() else 0


async def run_metric_runtime(config: MetricsConfig, stop_event: asyncio.Event) -> int:
    """Run one standalone metric runtime through cooperative shutdown."""

    runtime = MetricReplayRuntime(config)
    await runtime.start(stop_event)
    try:
        return await runtime.wait(stop_event)
    finally:
        await runtime.close(stop_event)
