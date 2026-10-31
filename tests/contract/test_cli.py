# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Stable CLI output, exit-code, conversion, and side-effect contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from signal_generator.cli import main
from signal_generator.config.validation import load_schema


def test_validate_text_and_json(log_config_factory, capsys: pytest.CaptureFixture[str]) -> None:
    """Validation supports human and schema-conforming machine output without stderr noise."""

    config_path = log_config_factory()
    assert main(["validate", "--config", str(config_path)]) == 0
    assert "Configuration is valid" in capsys.readouterr().out
    assert main(["validate", "--config", str(config_path), "--format", "json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    Draft202012Validator(load_schema("validation_result.schema.json")).validate(payload)
    assert captured.err == ""


def test_invalid_validate_exit_and_stderr(
    log_config_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invalid full validation returns code three and writes actionable text to stderr."""

    config_path = log_config_factory({"logs": {"source": {"path": "missing.txt"}}})
    assert main(["validate", "--config", str(config_path)]) == 3
    assert "SGCFG-SOURCE-001" in capsys.readouterr().err


def test_print_effective_config_redacts(
    log_config_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Effective output is deterministic JSON and redacts secret-looking header values."""

    config_path = log_config_factory(
        {
            "logs": {
                "outputs": [
                    {
                        "type": "http",
                        "url": "http://localhost",
                        "headers": {"Authorization": "value"},
                    }
                ]
            }
        }
    )
    assert main(["print-effective-config", "--config", str(config_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["logs"]["outputs"][0]["headers"]["Authorization"] == "<redacted>"


def test_convert_properties_and_overwrite_guard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Conversion writes versioned JSON and refuses implicit replacement."""

    input_path = tmp_path / "legacy.properties"
    output_path = tmp_path / "config.json"
    input_path.write_text(
        "OUTPUTTYPE=STDOUT\nSOURCE=events.txt\nSOURCEFORMAT=%t %m\n", encoding="utf-8"
    )
    arguments = ["convert-properties", "--input", str(input_path), "--output", str(output_path)]
    assert main(arguments) == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert main(arguments) == 3
    assert "--force" in capsys.readouterr().err


def test_run_byte_exact(log_config_factory, capsys: pytest.CaptureFixture[str]) -> None:
    """A zero-delay standalone scenario renders byte-exact repeated counters to stdout."""

    config_path = log_config_factory(
        {
            "logs": {
                "source": {"format": "%t %m"},
                "replay": {"cycles": 2, "default_interval_ms": 0, "acceleration": 1000000},
            }
        }
    )
    assert main(["run", "--config", str(config_path)]) == 0
    assert capsys.readouterr().out == "first:1:1\nsecond:1:2\nfirst:2:1\nsecond:2:2\n"


def test_version_uses_argparse_contract(capsys: pytest.CaptureFixture[str]) -> None:
    """Global version output is machine-readable and exits successfully through argparse."""

    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.startswith("signal-generator ")


@pytest.mark.parametrize(
    "relative_path",
    (
        "examples/logs/basic/config.json",
        "examples/logs/multiline/config.json",
        "examples/metrics/config.json",
        "examples/metrics/container-config.json",
    ),
)
def test_checked_in_examples_pass_full_validation(relative_path: str) -> None:
    """Every runnable checked-in configuration passes schema, semantic, and source validation."""

    assert main(["validate", "--config", relative_path, "--format", "json"]) == 0
