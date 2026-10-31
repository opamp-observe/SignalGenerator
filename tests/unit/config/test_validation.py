# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Configuration schema, source, precedence, and redaction tests."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from signal_generator.config.loader import load_configuration
from signal_generator.config.redaction import redact_secrets
from signal_generator.config.validation import load_schema, validate_config_file
from signal_generator.constants import REDACTED_VALUE


def test_valid_configuration_and_relative_path(log_config_factory) -> None:
    """A valid source resolves relative to the configuration file."""

    config_path = log_config_factory()
    result = validate_config_file(config_path)
    loaded = load_configuration(config_path)
    assert result.valid
    assert loaded.model.logs is not None
    assert loaded.model.logs.source.path == config_path.parent / "events.txt"


def test_schema_only_does_not_require_source(log_config_factory) -> None:
    """Schema-only mode does not read a missing source file."""

    config_path = log_config_factory({"logs": {"source": {"path": "missing.txt"}}})
    assert validate_config_file(config_path, schema_only=True).valid
    assert not validate_config_file(config_path).valid


def test_json_syntax_location(tmp_path: Path) -> None:
    """Malformed JSON reports a parser code plus line and column."""

    config_path = tmp_path / "broken.json"
    config_path.write_text('{"schema_version":', encoding="utf-8")
    diagnostic = validate_config_file(config_path).errors[0]
    assert diagnostic.code == "SGCFG-JSON-001"
    assert diagnostic.line == 1
    assert diagnostic.column is not None


def test_unknown_property_suggestion(log_config_factory) -> None:
    """Misspelled known properties receive an actionable nearest-name hint."""

    config_path = log_config_factory({"metrcis": {"enabled": False}})
    diagnostics = validate_config_file(config_path, schema_only=True).errors
    unknown = next(item for item in diagnostics if "metrcis" in item.message)
    assert unknown.hint == "did you mean 'metrics'?"


def test_environment_precedence_and_type_conversion(log_config_factory) -> None:
    """Environment overrides replace file values and convert numeric fields."""

    config_path = log_config_factory({"runtime": {"log_level": "INFO"}})
    loaded = load_configuration(
        config_path,
        {"SIGNAL_GENERATOR_LOG_LEVEL": "ERROR", "SIGNAL_GENERATOR_METRICS_PORT": "9200"},
    )
    assert loaded.model.runtime.log_level == "ERROR"
    assert loaded.effective["metrics"]["pull"]["port"] == 9200


def test_invalid_environment_conversion_is_diagnostic(log_config_factory) -> None:
    """Invalid numeric environment values become validation diagnostics instead of tracebacks."""

    config_path = log_config_factory()
    result = validate_config_file(config_path, environ={"SIGNAL_GENERATOR_METRICS_PORT": "bad"})
    assert not result.valid
    assert "invalid literal" in result.errors[0].message


def test_embedded_mode_requires_runtime_identity(log_config_factory) -> None:
    """Semantic validation requires embedded route and runtime ownership fields."""

    config_path = log_config_factory({"deployment": {"mode": "embedded_quart"}})
    pointers = {item.instance_path for item in validate_config_file(config_path).errors}
    assert pointers == {"/deployment/route_prefix", "/deployment/runtime_id"}


def test_secret_redaction_is_recursive() -> None:
    """Secret-like values are removed from nested dictionaries and arrays."""

    redacted = redact_secrets(
        {"headers": {"Authorization": "secret"}, "items": [{"password": "p"}]}
    )
    assert redacted["headers"]["Authorization"] == REDACTED_VALUE
    assert redacted["items"][0]["password"] == REDACTED_VALUE


def test_packaged_schemas_are_valid() -> None:
    """Every published schema satisfies the Draft 2020-12 meta-schema."""

    for schema_name in (
        "config.schema.json",
        "metric_frame.schema.json",
        "validation_result.schema.json",
        "adapter_config.schema.json",
    ):
        Draft202012Validator.check_schema(load_schema(schema_name))


def test_metric_source_jsonl_validation(tmp_path: Path) -> None:
    """Malformed metric JSONL is reported with its physical line number."""

    (tmp_path / "frames.jsonl").write_text("{bad}\n", encoding="utf-8")
    document = {
        "schema_version": 1,
        "metrics": {"enabled": True, "source": {"path": "frames.jsonl"}},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    diagnostic = validate_config_file(config_path).errors[0]
    assert diagnostic.source.endswith("frames.jsonl")
    assert diagnostic.line == 1
