# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Adapter schema, CLI, and installed-discovery contract tests."""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from signal_generator_opamp_sim import cli
from signal_generator_opamp_sim.cli import main
from signal_generator_opamp_sim.config import load_adapter_config, validate_adapter_file


def _write_json(path: Path, document: object) -> None:
    """Write deterministic JSON test input."""

    path.write_text(json.dumps(document), encoding="utf-8")


def _scenario(tmp_path: Path) -> Path:
    """Create a valid one-frame SignalGenerator scenario."""

    frames = tmp_path / "frames.jsonl"
    frames.write_text(
        json.dumps(
            {
                "frame": 1,
                "metrics": [
                    {
                        "name": "nginx_connections_active",
                        "type": "gauge",
                        "help": "Active NGINX connections.",
                        "samples": [{"labels": {"instance": "test"}, "value": 4}],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "signal.json"
    _write_json(
        config,
        {
            "schema_version": 1,
            "metrics": {
                "enabled": True,
                "source": {"path": "frames.jsonl", "eof": "loop"},
                "pull": {"enabled": True, "path": "/metrics"},
                "push": {"enabled": False},
            },
        },
    )
    return config


def _adapter_document(tmp_path: Path) -> dict[str, object]:
    """Create referenced consumer/response documents and return adapter input."""

    _write_json(tmp_path / "consumer.json", {"consumer": {"server_url": "http://provider"}})
    _write_json(tmp_path / "responses.json", {"responses": {"*": ["accept"]}})
    return {
        "schema_version": 1,
        "mode": "unified_quart",
        "quart": {"host": "127.0.0.1", "port": 9108, "workers": 1},
        "signal_generator_runtimes": [
            {"id": "nginx", "config_path": _scenario(tmp_path).name, "route_prefix": "/signals/nginx"}
        ],
        "instances": [
            {
                "name": "simulator-a",
                "consumer_config_path": "consumer.json",
                "responses_path": "responses.json",
                "signal_generator_runtime": "nginx",
                "identity": {"service_instance_uid": "simulator-a"},
            }
        ],
    }


def test_validate_load_and_json_cli(tmp_path: Path, capsys) -> None:
    """Full validation resolves nested files and JSON CLI output uses the shared envelope."""

    config_path = tmp_path / "adapter.json"
    _write_json(config_path, _adapter_document(tmp_path))
    result = validate_adapter_file(config_path)
    assert result.valid
    loaded = load_adapter_config(config_path)
    assert loaded.runtimes[0].config_path == (tmp_path / "signal.json").resolve()
    assert main(["validate", "--config", str(config_path), "--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["result_version"] == 1 and output["valid"] is True


def test_semantic_and_source_errors_are_actionable(tmp_path: Path) -> None:
    """Duplicate ownership and missing references fail before runtime resources exist."""

    document = _adapter_document(tmp_path)
    document["signal_generator_runtimes"].append(  # type: ignore[union-attr]
        {"id": "nginx", "config_path": "missing.json", "route_prefix": "/signals/nginx"}
    )
    config_path = tmp_path / "bad.json"
    _write_json(config_path, document)
    result = validate_adapter_file(config_path)
    assert not result.valid
    assert {diagnostic.code for diagnostic in result.errors} == {"SGOPAMP-SEMANTIC-001"}
    assert any("duplicate runtime id" in diagnostic.message for diagnostic in result.errors)


def test_installed_plugin_entry_point_is_discoverable() -> None:
    """The adapter registers externally without modifying opamp-core's built-in registry."""

    entry_points = metadata.entry_points().select(group="opamp_consumer.plugins")
    values = {entry_point.name: entry_point.value for entry_point in entry_points}
    assert values["signal_generator"] == "signal_generator_opamp_sim.supervised_plugin:main"


def test_schema_only_does_not_read_references_and_text_cli_fails(tmp_path: Path, capsys) -> None:
    """Schema-only is side-effect-free while text mode returns actionable failures."""

    document = _adapter_document(tmp_path)
    document["signal_generator_runtimes"][0]["config_path"] = "missing.json"  # type: ignore[index]
    config_path = tmp_path / "schema-only.json"
    _write_json(config_path, document)
    assert validate_adapter_file(config_path, schema_only=True).valid
    assert main(["validate", "--config", str(config_path)]) == 2
    assert "SGCFG-SOURCE-001" in capsys.readouterr().out


def test_invalid_json_and_unknown_runtime_reference(tmp_path: Path) -> None:
    """Parser and cross-reference failures retain stable adapter codes."""

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert validate_adapter_file(broken).errors[0].code == "SGOPAMP-JSON-001"
    document = _adapter_document(tmp_path)
    document["instances"][0]["signal_generator_runtime"] = "unknown"  # type: ignore[index]
    config_path = tmp_path / "unknown.json"
    _write_json(config_path, document)
    result = validate_adapter_file(config_path)
    assert "unknown SignalGenerator runtime" in result.errors[0].message


def test_cli_dispatches_supervised_and_unified(monkeypatch) -> None:
    """Top-level dispatch reaches both runtime modes without importing them during validation."""

    monkeypatch.setattr(cli, "_supervised", lambda config_path: 7)
    monkeypatch.setattr(cli, "_unified", lambda config_path: 8)
    assert main(["supervised", "--config", "adapter.json"]) == 7
    assert main(["unified", "--config", "adapter.json"]) == 8


def test_supervised_cli_process_contract_and_timeout(monkeypatch) -> None:
    """Supervised CLI uses a shell-free child and escalates an interrupted timed-out stop."""

    settings = SimpleNamespace(
        executable_path="signal-generator",
        config_path=Path("scenario.json"),
        shutdown_timeout_seconds=0.1,
    )
    monkeypatch.setattr(
        cli,
        "load_adapter_config",
        lambda path: SimpleNamespace(mode="supervised", supervised=settings),
    )

    class Child:
        """Raise interrupt and timeout in sequence to cover bounded escalation."""

        def __init__(self) -> None:
            self.calls = 0
            self.terminated = False
            self.killed = False

        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            if self.calls == 2:
                raise cli.subprocess.TimeoutExpired("signal-generator", timeout)
            return 9

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

    child = Child()
    monkeypatch.setattr(cli.subprocess, "Popen", lambda command: child)
    assert cli._supervised("adapter.json") == 9
    assert child.terminated and child.killed
    monkeypatch.setattr(
        cli,
        "load_adapter_config",
        lambda path: SimpleNamespace(mode="unified_quart", supervised=None),
    )
    with pytest.raises(ValueError, match="mode supervised"):
        cli._supervised("adapter.json")


def test_unified_cli_builds_one_worker_server(monkeypatch) -> None:
    """Unified CLI pins one Hypercorn worker and runs the app in the foreground."""

    settings = SimpleNamespace(host="127.0.0.1", port=9108, workers=1)
    monkeypatch.setattr(
        cli,
        "load_adapter_config",
        lambda path: SimpleNamespace(quart=settings),
    )
    observed = {}

    async def fake_serve(app, server_config) -> None:
        observed["app"] = app
        observed["bind"] = server_config.bind
        observed["workers"] = server_config.workers

    monkeypatch.setattr("hypercorn.asyncio.serve", fake_serve)
    monkeypatch.setattr(
        "signal_generator_opamp_sim.quart_app.create_app", lambda path: "quart-app"
    )
    assert cli._unified("adapter.json") == 0
    assert observed == {"app": "quart-app", "bind": ["127.0.0.1:9108"], "workers": 1}
