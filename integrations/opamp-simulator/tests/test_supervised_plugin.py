# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Supervised plugin configuration, process, metadata, and bootstrap tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from opamp_consumer.abstract_client import AbstractOpAMPClient
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.plugin_config import ConsumerPluginConfigContext

from signal_generator_opamp_sim import supervised_plugin
from signal_generator_opamp_sim.supervised_plugin import (
    SignalGeneratorLifecycle,
    SignalGeneratorOpAMPClient,
    process_consumer_config,
)


class FakeProcess:
    """Small subprocess contract used to exercise bounded lifecycle branches."""

    def __init__(self, *, time_out: bool = False) -> None:
        """Initialize call state and optional first-wait timeout."""

        self.time_out = time_out
        self.terminated = False
        self.killed = False
        self.wait_count = 0

    def terminate(self) -> None:
        """Record graceful termination."""

        self.terminated = True

    def kill(self) -> None:
        """Record forced termination."""

        self.killed = True

    def wait(self, timeout=None) -> int:
        """Raise once when configured, then report successful exit."""

        del timeout
        self.wait_count += 1
        if self.time_out and self.wait_count == 1:
            raise subprocess.TimeoutExpired("signal-generator", 1)
        return 0


def _owner(tmp_path: Path) -> SimpleNamespace:
    """Create the minimal owner contract used by SignalGeneratorLifecycle."""

    config = ConsumerConfig(
        agent_config_path=str(tmp_path / "scenario.json"),
        agent_additional_params=["--once"],
    )
    config.signal_generator_executable_path = "signal-generator"
    config.signal_generator_shutdown_timeout_seconds = 0.1
    return SimpleNamespace(config=config, data=SimpleNamespace(agent_process=None))


def test_plugin_config_precedence_and_relative_executable(tmp_path: Path, monkeypatch) -> None:
    """Environment wins and path-like executables resolve against the consumer config."""

    context = ConsumerPluginConfigContext(
        "signal_generator",
        "signal_generator",
        {"executable_path": "./bin/signal-generator", "health_port": 9200},
        {},
        tmp_path / "consumer.json",
    )
    monkeypatch.setenv("OPAMP_SIGNAL_GENERATOR_HEALTH_PORT", "9300")
    updates = process_consumer_config(context)
    assert updates["signal_generator_executable_path"] == str(
        (tmp_path / "bin" / "signal-generator").resolve()
    )
    assert updates["signal_generator_health_port"] == 9300
    assert updates["signal_generator_health_host"] == "127.0.0.1"


def test_lifecycle_launch_restart_and_bounded_kill(tmp_path: Path, monkeypatch) -> None:
    """The plugin uses shell-free argv and kills only after a bounded graceful wait."""

    owner = _owner(tmp_path)
    processes = [FakeProcess(), FakeProcess(time_out=True)]
    commands: list[list[str]] = []

    def fake_popen(command):
        commands.append(command)
        return processes.pop(0)

    monkeypatch.setattr(supervised_plugin.subprocess, "Popen", fake_popen)
    lifecycle = SignalGeneratorLifecycle(owner)
    assert lifecycle.launch_agent_process()
    assert commands[0][-1] == "--once"
    assert lifecycle.restart_agent_process()
    second = owner.data.agent_process
    lifecycle.terminate_agent_process()
    assert second.terminated and second.killed
    lifecycle.terminate_agent_process()


def test_metadata_version_and_remote_validation(tmp_path: Path, monkeypatch) -> None:
    """Metadata is stable, version probing is bounded, and invalid remote config is rejected."""

    scenario = tmp_path / "scenario.json"
    frame = tmp_path / "frames.jsonl"
    frame.write_text(
        '{"frame":1,"metrics":[{"name":"up","type":"gauge","help":"Up.",'
        '"samples":[{"labels":{},"value":1}]}]}\n',
        encoding="utf-8",
    )
    valid_document = {
        "schema_version": 1,
        "metrics": {
            "enabled": True,
            "source": {"path": "frames.jsonl", "eof": "loop"},
            "pull": {"enabled": True},
            "push": {"enabled": False},
        },
    }
    scenario.write_text(json.dumps(valid_document), encoding="utf-8")
    config = ConsumerConfig(agent_config_path=str(scenario))
    config.signal_generator_executable_path = "signal-generator"
    client = SignalGeneratorOpAMPClient.__new__(SignalGeneratorOpAMPClient)
    client.data = SimpleNamespace(config=config, agent_version="")
    metadata = client.get_config_metadata()
    assert metadata.config_data == scenario.read_text(encoding="utf-8")
    assert len(metadata.config_version) == 64
    completed = SimpleNamespace(stdout="signal-generator 0.1.0\n", stderr="")
    monkeypatch.setattr(supervised_plugin.shutil, "which", lambda executable: executable)
    monkeypatch.setattr(supervised_plugin.subprocess, "run", lambda *args, **kwargs: completed)
    client.add_agent_version(9108)
    assert client.data.agent_version == "signal-generator 0.1.0"
    target = tmp_path / "remote.json"
    client.write_config_file(str(target), json.dumps(valid_document).encode())
    assert target.exists()
    with pytest.raises(ValueError, match="required property"):
        client.write_config_file(str(target), b'{"metrics": {}}')
    with pytest.raises(json.JSONDecodeError):
        client.write_config_file(str(target), b"{")


def test_client_initialization_and_version_failure(monkeypatch) -> None:
    """Client endpoint settings initialize correctly and version failures remain non-fatal."""

    def fake_base_init(owner, base_url, config) -> None:
        del base_url
        owner.data = SimpleNamespace(config=config, agent_type_name="", agent_version="")

    monkeypatch.setattr(AbstractOpAMPClient, "__init__", fake_base_init)
    config = ConsumerConfig()
    config.signal_generator_health_host = "127.0.0.1"
    config.signal_generator_status_timeout_seconds = 2
    config.signal_generator_executable_path = "missing"
    client = SignalGeneratorOpAMPClient("http://provider", config)
    assert client._localhost_base == "http://127.0.0.1"
    assert isinstance(client._create_runtime_process_lifecycle(), SignalGeneratorLifecycle)
    monkeypatch.setattr(supervised_plugin.shutil, "which", lambda executable: None)
    monkeypatch.setattr(
        supervised_plugin.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    client.add_agent_version(9108)
    assert client.data.agent_version == ""


@pytest.mark.asyncio
async def test_async_runner_connects_heartbeats_and_cleans_up(monkeypatch) -> None:
    """The plugin's async owner always disconnects and terminates its child."""

    calls: list[str] = []

    class FakeClient:
        """Record the public lifecycle used by the async plugin runner."""

        def __init__(self, base_url, config) -> None:
            del base_url, config

        def launch_agent_process(self) -> None:
            calls.append("launch")

        def add_agent_version(self, port) -> None:
            calls.append(f"version-{port}")

        async def send(self) -> None:
            calls.append("send")

        async def run_heartbeat_loop(self, port) -> None:
            calls.append(f"heartbeat-{port}")

        async def finalize_async(self) -> None:
            calls.append("finalize")

        def terminate_agent_process(self) -> None:
            calls.append("terminate")

    monkeypatch.setattr(supervised_plugin, "SignalGeneratorOpAMPClient", FakeClient)
    config = ConsumerConfig(server_url="http://provider")
    config.signal_generator_health_port = 9191
    await supervised_plugin._run(config)
    assert calls == ["launch", "version-9191", "send", "heartbeat-9191", "finalize", "terminate"]


def test_main_uses_shared_consumer_bootstrap(monkeypatch) -> None:
    """Installed entry-point bootstrap loads, validates, instruments, and runs one client."""

    config = ConsumerConfig(server_url="http://provider", client_status_port=9108)
    parser = SimpleNamespace(parse_args=lambda: SimpleNamespace())
    calls: list[str] = []
    monkeypatch.setattr(supervised_plugin, "build_common_cli_parser", lambda: parser)
    monkeypatch.setattr(supervised_plugin, "load_config_from_cli_args", lambda args: config)
    monkeypatch.setattr(
        supervised_plugin, "configure_logging_for_config", lambda loaded: calls.append("logging")
    )
    monkeypatch.setattr(
        supervised_plugin,
        "validate_runtime_server_config",
        lambda **kwargs: kwargs["config"],
    )
    monkeypatch.setattr(
        supervised_plugin,
        "configure_observability_for_config",
        lambda **kwargs: calls.append("observability"),
    )
    monkeypatch.setattr(supervised_plugin.asyncio, "run", lambda coroutine: coroutine.close())
    supervised_plugin.main()
    assert calls == ["logging", "observability"]
