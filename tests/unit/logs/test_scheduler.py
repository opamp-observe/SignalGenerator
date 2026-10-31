# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Deterministic scheduling and output failure-policy tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from signal_generator.config.models import (
    LogsConfig,
    LogSourceConfig,
    OutputConfig,
    ReplayConfig,
    RetryConfig,
)
from signal_generator.logs.models import RenderedLogEvent
from signal_generator.logs.outputs.base import LogOutput
from signal_generator.logs.scheduler import OutputStartupError, ReplayError, replay_logs


class RecordingOutput(LogOutput):
    """Record lifecycle and optionally fail a configured number of writes."""

    def __init__(self, fail_writes: int = 0, fail_open: bool = False) -> None:
        """Configure deterministic open and write failures."""

        self.fail_writes = fail_writes
        self.fail_open = fail_open
        self.actions: list[str] = []
        self.events: list[str] = []

    async def open(self) -> None:
        """Record open or raise the configured startup failure."""

        self.actions.append("open")
        if self.fail_open:
            raise OSError("open failed")

    async def write(self, event: RenderedLogEvent) -> None:
        """Record writes after consuming configured transient failures."""

        self.actions.append("write")
        if self.fail_writes:
            self.fail_writes -= 1
            raise OSError("write failed")
        self.events.append(event.text)

    async def flush(self) -> None:
        """Record scheduler flush ordering."""

        self.actions.append("flush")

    async def close(self) -> None:
        """Record scheduler close ordering."""

        self.actions.append("close")


def _logs_config(tmp_path: Path, output: OutputConfig, cycles: int | str = 1) -> LogsConfig:
    """Create a two-event relative-time scenario for scheduler tests."""

    source_path = tmp_path / "events.txt"
    source_path.write_text("+0 first\n+100 second\n", encoding="utf-8")
    return LogsConfig(
        True,
        LogSourceConfig(source_path, "%t %m"),
        format="%m:%i:%j",
        replay=ReplayConfig(cycles=cycles, acceleration=2.0, start_delay_ms=20, loop_gap_ms=30),
        outputs=(output,),
    )


@pytest.mark.asyncio
async def test_cycles_timing_and_lifecycle(tmp_path: Path) -> None:
    """Fake sleeping proves acceleration, loop gaps, counters, and lifecycle order."""

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        """Record requested monotonic delays without wall-clock waiting."""

        sleeps.append(seconds)

    output_config = OutputConfig("test")
    output = RecordingOutput()
    emitted = await replay_logs(
        _logs_config(tmp_path, output_config, cycles=2), sleeper=fake_sleep, outputs=[output]
    )
    assert emitted == 4
    assert output.events == ["first:1:1", "second:1:2", "first:2:1", "second:2:2"]
    assert sleeps == [0.02, 0.05, 0.03, 0.05]
    assert output.actions[0] == "open"
    assert output.actions[-1] == "close"


@pytest.mark.asyncio
async def test_retry_and_continue_policies(tmp_path: Path) -> None:
    """Retry waits and succeeds, while continue suppresses a permanent output failure."""

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        """Capture retry and source timing delays."""

        sleeps.append(seconds)

    retry_config = OutputConfig("test", "retry", retry=RetryConfig(2, 0.25))
    retry_output = RecordingOutput(fail_writes=1)
    await replay_logs(
        _logs_config(tmp_path, retry_config), sleeper=fake_sleep, outputs=[retry_output]
    )
    assert 0.25 in sleeps
    continue_config = OutputConfig("test", "continue")
    continue_output = RecordingOutput(fail_writes=10)
    assert (
        await replay_logs(
            _logs_config(tmp_path, continue_config), sleeper=fake_sleep, outputs=[continue_output]
        )
        == 2
    )


@pytest.mark.asyncio
async def test_fail_policy_and_startup_unwind(tmp_path: Path) -> None:
    """Fail policy classifies runtime errors and a later open failure closes earlier outputs."""

    output_config = OutputConfig("test")
    with pytest.raises(ReplayError, match="write failed"):
        await replay_logs(
            _logs_config(tmp_path, output_config), outputs=[RecordingOutput(fail_writes=1)]
        )
    first = RecordingOutput()
    second = RecordingOutput(fail_open=True)
    config = _logs_config(tmp_path, output_config)
    with pytest.raises(OutputStartupError, match="open failed"):
        await replay_logs(config, outputs=[first, second])
    assert first.actions == ["open", "close"]


@pytest.mark.asyncio
async def test_forever_stops_cooperatively(tmp_path: Path) -> None:
    """An injected stop event terminates explicit forever replay without another cycle."""

    stop_event = asyncio.Event()
    output = RecordingOutput()

    async def stop_after_first_delay(seconds: float) -> None:
        """Request stop at the first inter-record wait."""

        del seconds
        stop_event.set()

    emitted = await replay_logs(
        _logs_config(tmp_path, OutputConfig("test"), cycles="forever"),
        sleeper=stop_after_first_delay,
        stop_event=stop_event,
        outputs=[output],
    )
    assert emitted == 0
