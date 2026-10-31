# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Application and CLI failure classification tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_generator.application import ApplicationStartupError, run_application
from signal_generator.cli import main
from signal_generator.config.loader import load_configuration


@pytest.mark.asyncio
async def test_application_rejects_embedded_mode(log_config_factory) -> None:
    """The standalone command rejects an embedded host configuration."""

    embedded_path = log_config_factory(
        {"deployment": {"mode": "embedded_quart", "route_prefix": "/runtime", "runtime_id": "one"}}
    )
    with pytest.raises(ApplicationStartupError, match="embedded"):
        await run_application(load_configuration(embedded_path).model)


def test_cli_print_and_conversion_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing config and malformed legacy input return validation failures without tracebacks."""

    assert main(["print-effective-config", "--config", str(tmp_path / "missing.json")]) == 3
    legacy_path = tmp_path / "legacy.properties"
    legacy_path.write_text("bad line\n", encoding="utf-8")
    assert (
        main(
            [
                "convert-properties",
                "--input",
                str(legacy_path),
                "--output",
                str(tmp_path / "out.json"),
            ]
        )
        == 3
    )
    assert capsys.readouterr().err


def test_cli_classifies_startup_and_runtime_failures(
    log_config_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Application startup and replay exceptions map to documented exit codes."""

    config_path = log_config_factory()

    async def startup_failure(config):
        """Raise a classified startup failure."""

        del config
        raise ApplicationStartupError("startup")

    monkeypatch.setattr("signal_generator.cli.run_application", startup_failure)
    assert main(["run", "--config", str(config_path)]) == 4

    async def runtime_failure(config):
        """Raise a generic value error classified as a replay failure."""

        del config
        raise ValueError("runtime")

    monkeypatch.setattr("signal_generator.cli.run_application", runtime_failure)
    assert main(["run", "--config", str(config_path)]) == 5


def test_loader_without_validation_and_non_object_override(log_config_factory) -> None:
    """Internal callers may skip validation, while invalid override parents remain explicit errors."""

    config_path = log_config_factory()
    assert load_configuration(config_path, validate=False).model.schema_version == 1
    invalid_path = log_config_factory({"runtime": "bad"})
    with pytest.raises(ValueError, match="non-object"):
        load_configuration(invalid_path, {"SIGNAL_GENERATOR_LOG_LEVEL": "INFO"}, validate=False)


def test_cli_classifies_missing_push_secret_as_startup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unresolved Pushgateway secret fails before network access with exit code four."""

    monkeypatch.delenv("MISSING_PUSH_TOKEN", raising=False)
    (tmp_path / "frames.jsonl").write_text(
        '{"metrics":[{"name":"up","type":"gauge","help":"Up.","samples":[{"value":1}]}]}\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "push.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": {
                    "enabled": True,
                    "source": {"path": "frames.jsonl", "eof": "stop"},
                    "push": {
                        "enabled": True,
                        "url": "http://127.0.0.1:9091",
                        "job": "demo",
                        "interval_seconds": 1,
                        "bearer_token_env": "MISSING_PUSH_TOKEN",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    assert main(["run", "--config", str(config_path)]) == 4
    assert "MISSING_PUSH_TOKEN" in capsys.readouterr().err
