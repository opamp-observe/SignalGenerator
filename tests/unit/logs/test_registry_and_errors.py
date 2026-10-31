# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Output registry selection, plugin discovery, and unopened-adapter error tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from signal_generator.config.models import OutputConfig
from signal_generator.logs.models import LogEvent, RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput
from signal_generator.logs.outputs.file import FileOutput
from signal_generator.logs.outputs.http import HttpOutput
from signal_generator.logs.outputs.tcp import TcpOutput
from signal_generator.logs.registry import create_output


def _rendered() -> RenderedLogEvent:
    """Create one minimal output payload."""

    return RenderedLogEvent("event", LogEvent(1, "event"), 1, 1)


def test_registry_creates_every_builtin(tmp_path: Path) -> None:
    """Every schema-advertised built-in resolves without dynamic imports."""

    configs = (
        OutputConfig("stdout"),
        OutputConfig("stderr"),
        OutputConfig("file", options={"path": str(tmp_path / "out.log")}),
        OutputConfig("http", options={"url": "http://localhost"}),
        OutputConfig("tcp", options={"host": "localhost", "port": 1234}),
        OutputConfig("python_logging"),
    )
    assert all(isinstance(create_output(config), LogOutput) for config in configs)
    with pytest.raises(ValueError, match="unsupported output"):
        create_output(OutputConfig("unknown"))


def test_plugin_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Named entry points load factories and reject missing or invalid plugin results."""

    class EntryPoint:
        """Return an injected plugin factory from ``load``."""

        def __init__(self, factory):
            """Store the factory selected by the test case."""

            self.factory = factory

        def load(self):
            """Return the stored factory as importlib metadata would."""

            return self.factory

    monkeypatch.setattr("signal_generator.logs.registry.entry_points", lambda **kwargs: [])
    with pytest.raises(ValueError, match="not installed"):
        create_output(OutputConfig("plugin", options={"plugin_name": "missing", "options": {}}))
    monkeypatch.setattr(
        "signal_generator.logs.registry.entry_points",
        lambda **kwargs: [EntryPoint(lambda options: FileOutput("plugin.log"))],
    )
    assert isinstance(
        create_output(OutputConfig("plugin", options={"plugin_name": "demo", "options": {}})),
        FileOutput,
    )
    monkeypatch.setattr(
        "signal_generator.logs.registry.entry_points",
        lambda **kwargs: [EntryPoint(lambda options: object())],
    )
    with pytest.raises(TypeError, match="did not return"):
        create_output(OutputConfig("plugin", options={"plugin_name": "bad", "options": {}}))


@pytest.mark.asyncio
async def test_unopened_network_and_file_outputs_fail() -> None:
    """Adapters reject writes before resource acquisition and tolerate empty closes."""

    for output in (FileOutput("unused"), HttpOutput("http://localhost"), TcpOutput("localhost", 1)):
        with pytest.raises(RuntimeError, match="not open"):
            await output.write(_rendered())
        await output.flush()
        await output.close()
