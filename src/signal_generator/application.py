# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Host-independent application orchestration for implemented replay signals."""

from __future__ import annotations

import asyncio
import logging

from signal_generator.config.models import AppConfig
from signal_generator.lifecycle import ShutdownController
from signal_generator.logs.scheduler import replay_logs
from signal_generator.metrics.runtime import run_metric_runtime

LOGGER = logging.getLogger(__name__)


class ApplicationStartupError(RuntimeError):
    """Report unsupported host modes or a configuration with no enabled signals."""


async def run_application(config: AppConfig) -> int:
    """Run enabled log and metric signals with one cooperative shutdown controller."""

    if config.deployment.mode != "standalone":
        raise ApplicationStartupError("the standalone CLI cannot run embedded_quart mode")
    if not _has_enabled_signal(config):
        raise ApplicationStartupError("no signal is enabled")
    controller = ShutdownController()
    controller.install()
    tasks = _create_replay_tasks(config, controller.stop_event)
    results = await asyncio.gather(*tasks)
    return sum(results)


def _has_enabled_signal(config: AppConfig) -> bool:
    """Return whether at least one configured signal can be scheduled."""

    return bool(
        (config.logs is not None and config.logs.enabled)
        or (config.metrics is not None and config.metrics.enabled)
    )


def _create_replay_tasks(config: AppConfig, stop_event: asyncio.Event) -> list[asyncio.Task[int]]:
    """Create named tasks for each enabled signal family."""

    tasks: list[asyncio.Task[int]] = []
    if config.logs and config.logs.enabled:
        LOGGER.debug("starting log replay")
        tasks.append(
            asyncio.create_task(
                replay_logs(config.logs, stop_event=stop_event),
                name="signal-generator-logs",
            )
        )
    if config.metrics and config.metrics.enabled:
        LOGGER.debug("starting metric replay")
        tasks.append(
            asyncio.create_task(
                run_metric_runtime(config.metrics, stop_event),
                name="signal-generator-metrics",
            )
        )
    return tasks
