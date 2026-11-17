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

from signal_generator.config.loader import load_configuration, load_configuration_mapping
from signal_generator.config.redaction import redact_secrets
from signal_generator.config.validation import (
    load_schema,
    validate_config_file,
    validate_config_mapping,
)
from signal_generator.constants import REDACTED_VALUE


def test_valid_configuration_and_relative_path(log_config_factory) -> None:
    """A valid source resolves relative to the configuration file."""

    config_path = log_config_factory()
    result = validate_config_file(config_path)
    loaded = load_configuration(config_path)
    assert result.valid
    assert loaded.model.logs is not None
    assert loaded.model.logs.source.path == config_path.parent / "events.txt"


def test_replay_start_and_priority_survive_typed_loading(log_config_factory) -> None:
    """Explicit scheduling fields are retained while omission preserves legacy timing."""

    explicit_path = log_config_factory(
        {"logs": {"replay": {"start_at": "now", "source_priority": 25}}}
    )
    explicit = load_configuration(explicit_path).model.logs
    assert explicit is not None
    assert explicit.replay.start_at == "now"
    assert explicit.replay.source_priority == 25

    legacy_path = log_config_factory()
    legacy = load_configuration(legacy_path).model.logs
    assert legacy is not None
    assert legacy.replay.start_at is None
    assert legacy.replay.source_priority == 100


def test_multiple_log_sources_validate_resolve_and_load(tmp_path: Path) -> None:
    """The multi-source form resolves each path and retains stable identity and priority."""

    (tmp_path / "first.txt").write_text("+0 first\n", encoding="utf-8")
    (tmp_path / "second.txt").write_text("+0 second\n", encoding="utf-8")
    document = {
        "schema_version": 1,
        "logs": {
            "enabled": True,
            "sources": [
                {
                    "id": "first",
                    "priority": 10,
                    "source": {"path": "first.txt", "format": "%t %m"},
                },
                {
                    "id": "second",
                    "source": {"path": "second.txt", "format": "%t %m"},
                },
            ],
            "outputs": [{"type": "stdout"}],
        },
    }
    config_path = tmp_path / "multi.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")

    result = validate_config_file(config_path)
    loaded = load_configuration(config_path).model.logs

    assert result.valid
    assert loaded is not None
    assert loaded.source is None
    assert [source.source_id for source in loaded.sources] == ["first", "second"]
    assert [source.priority for source in loaded.sources] == [10, 100]
    assert loaded.sources[1].source.path == tmp_path / "second.txt"
    assert loaded.replay.start_at == "now"


def test_multiple_log_sources_reject_duplicate_identifiers(tmp_path: Path) -> None:
    """Duplicate source identifiers fail semantic validation before typed loading."""

    (tmp_path / "events.txt").write_text("+0 event\n", encoding="utf-8")
    common_source = {"path": "events.txt", "format": "%t %m"}
    document = {
        "schema_version": 1,
        "logs": {
            "enabled": True,
            "sources": [
                {"id": "duplicate", "source": common_source},
                {"id": "duplicate", "source": common_source},
            ],
            "outputs": [{"type": "stdout"}],
        },
    }
    config_path = tmp_path / "invalid-multi.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")

    result = validate_config_file(config_path)

    assert not result.valid
    assert result.errors[0].message == "duplicate log source id: duplicate"


def test_log_configuration_rejects_legacy_and_multiple_sources(tmp_path: Path) -> None:
    """Schema validation requires exactly one of the legacy and multi-source forms."""

    (tmp_path / "events.txt").write_text("+0 event\n", encoding="utf-8")
    source = {"path": "events.txt", "format": "%t %m"}
    document = {
        "schema_version": 1,
        "logs": {
            "enabled": True,
            "source": source,
            "sources": [{"id": "other", "source": source}],
            "outputs": [{"type": "stdout"}],
        },
    }
    config_path = tmp_path / "ambiguous-sources.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")

    result = validate_config_file(config_path)

    assert not result.valid
    assert any("supported form" in diagnostic.message for diagnostic in result.errors)


def test_replay_start_requires_now_or_timezone_aware_rfc3339(log_config_factory) -> None:
    """Ambiguous or malformed explicit scenario epochs are rejected during validation."""

    config_path = log_config_factory({"logs": {"replay": {"start_at": "2026-01-01"}}})

    result = validate_config_file(config_path)

    assert not result.valid
    assert result.errors[0].instance_path == "/logs/replay/start_at"


def test_in_memory_validation_and_loading_for_embedding(log_config_factory) -> None:
    """Remote-config callers validate and type mappings relative to an explicit base path."""

    config_path = log_config_factory()
    document = json.loads(config_path.read_text(encoding="utf-8"))
    result = validate_config_mapping(document, base_path=config_path.parent)
    loaded = load_configuration_mapping(document, base_path=config_path.parent)
    assert result.valid
    assert loaded.path.name == "<in-memory-config>"
    assert loaded.model.logs and loaded.model.logs.source.path == config_path.parent / "events.txt"


def test_invalid_in_memory_environment_override_is_diagnostic(log_config_factory) -> None:
    """Mapping validation translates invalid environment conversions into diagnostics."""

    config_path = log_config_factory()
    document = json.loads(config_path.read_text(encoding="utf-8"))
    result = validate_config_mapping(
        document,
        base_path=config_path.parent,
        environ={"SIGNAL_GENERATOR_METRICS_PORT": "bad"},
    )
    assert not result.valid and "invalid literal" in result.errors[0].message


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
        "metrics": {
            "enabled": True,
            "source": {"path": "frames.jsonl"},
            "pull": {"enabled": True},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    diagnostic = validate_config_file(config_path).errors[0]
    assert diagnostic.source.endswith("frames.jsonl")
    assert diagnostic.line == 1


def test_trace_configuration_is_validated_resolved_and_typed(tmp_path: Path) -> None:
    """A trace-only scenario validates its OTLP source and resolves the relative path."""

    trace_path = tmp_path / "traces.ndjson"
    trace_path.write_text(
        '{"resourceSpans":[{"scopeSpans":[{"spans":[{'
        '"traceId":"11111111111111111111111111111111",'
        '"spanId":"2222222222222222",'
        '"startTimeUnixNano":"100","endTimeUnixNano":"200"}]}]}]}\n',
        encoding="utf-8",
    )
    document = {
        "schema_version": 1,
        "traces": {
            "enabled": True,
            "source": {"path": "traces.ndjson"},
            "replay": {"cycles": 2},
            "push": {"url": "http://collector:4318/v1/traces"},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    result = validate_config_file(config_path)
    loaded = load_configuration(config_path)
    assert result.valid
    assert loaded.model.traces is not None
    assert loaded.model.traces.source is not None
    assert loaded.model.traces.source.path == trace_path
    assert loaded.model.traces.replay.cycles == 2
    assert loaded.model.traces.push is not None
    assert loaded.model.traces.push.protocol == "otlp_http_json"


def test_otlp_metric_push_validates_without_pushgateway_job(tmp_path: Path) -> None:
    """OTLP metric push requires its endpoint and interval but no Pushgateway grouping job."""

    metric_path = tmp_path / "metrics.ndjson"
    metric_path.write_text(
        '{"metrics":[{"name":"temperature","type":"gauge","help":"Temperature.",'
        '"samples":[{"value":21.5}]}]}\n',
        encoding="utf-8",
    )
    document = {
        "schema_version": 1,
        "metrics": {
            "enabled": True,
            "source": {"path": "metrics.ndjson", "eof": "stop"},
            "push": {
                "enabled": True,
                "protocol": "otlp_http_json",
                "url": "http://collector:4318/v1/metrics",
                "interval_seconds": 1,
            },
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")

    result = validate_config_file(config_path)
    loaded = load_configuration(config_path)

    assert result.valid
    assert loaded.model.metrics is not None
    assert loaded.model.metrics.push.protocol == "otlp_http_json"
    assert loaded.model.metrics.push.job is None
