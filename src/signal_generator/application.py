# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Host-independent application orchestration for implemented replay signals."""

from __future__ import annotations

import logging

from signal_generator.config.models import AppConfig
from signal_generator.lifecycle import ShutdownController
from signal_generator.logs.scheduler import replay_logs

LOGGER = logging.getLogger(__name__)


class ApplicationStartupError(RuntimeError):
    """Report unsupported host modes or not-yet-implemented enabled signals."""


async def run_application(config: AppConfig) -> int:
    """Run enabled Phase 2 signals with a cooperative process shutdown controller."""

    if config.deployment.mode != "standalone":
        raise ApplicationStartupError("the standalone CLI cannot run embedded_quart mode")
    if config.metrics and config.metrics.get("enabled"):
        raise ApplicationStartupError("metrics replay is configured but requires Phase 3")
    if config.logs is None or not config.logs.enabled:
        raise ApplicationStartupError("no implemented signal is enabled")
    controller = ShutdownController()
    controller.install()
    LOGGER.debug("starting log replay")
    emitted = await replay_logs(config.logs, stop_event=controller.stop_event)
    LOGGER.debug("log replay finished after %s events", emitted)
    return emitted
