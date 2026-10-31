# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Graceful process shutdown primitives shared by replay runtimes."""

from __future__ import annotations

import asyncio
import signal


class ShutdownController:
    """Expose one event that is set by supported process termination signals."""

    def __init__(self) -> None:
        """Create an initially unset async stop event."""

        self.stop_event = asyncio.Event()

    def install(self) -> None:
        """Install best-effort SIGINT and SIGTERM handlers on the active event loop."""

        event_loop = asyncio.get_running_loop()
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            try:
                event_loop.add_signal_handler(signal_number, self.request_stop)
            except (NotImplementedError, RuntimeError):
                continue

    def request_stop(self) -> None:
        """Request cooperative shutdown without cancelling cleanup code."""

        self.stop_event.set()
