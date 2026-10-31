# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Validation diagnostic translation and source failure edge tests."""

from __future__ import annotations

import json
from pathlib import Path

from signal_generator.config.validation import Diagnostic, validate_config_file


def test_diagnostic_optional_serialization() -> None:
    """Optional location and hint fields appear only when supplied."""

    basic = Diagnostic("CODE", "error", "source", "", "", "message").to_dict()
    detailed = Diagnostic(
        "CODE", "warning", "source", "/x", "/y", "message", "hint", 2, 3
    ).to_dict()
    assert "hint" not in basic
    assert detailed["line"] == 2
    assert detailed["column"] == 3


def test_schema_message_variants(tmp_path: Path) -> None:
    """Required, type, minimum, enum, const, and alternative forms produce friendly messages."""

    documents = (
        {},
        {"schema_version": "one", "logs": {"enabled": True}},
        {"schema_version": 2, "logs": {"enabled": True}},
        {
            "schema_version": 1,
            "logs": {
                "enabled": True,
                "source": {"path": "x", "format": "%m"},
                "replay": {"cycles": 0},
                "outputs": [{"type": "bad"}],
            },
            "metrics": {"enabled": False, "source": {"path": "x", "maximum_line_bytes": 0}},
        },
    )
    messages: list[str] = []
    for index, document in enumerate(documents):
        config_path = tmp_path / f"config-{index}.json"
        config_path.write_text(json.dumps(document), encoding="utf-8")
        messages.extend(
            item.message for item in validate_config_file(config_path, schema_only=True).errors
        )
    assert any("required property" in message for message in messages)
    assert any("expected integer" in message for message in messages)
    assert any("must be 1" in message for message in messages)
    assert any("must be at least" in message for message in messages)
    assert any("must be one of" in message for message in messages)


def test_invalid_regex_and_metric_frame_schema(tmp_path: Path) -> None:
    """Semantic regex and metric-frame schema failures retain precise pointers and line context."""

    (tmp_path / "events.txt").write_text("event\n", encoding="utf-8")
    (tmp_path / "frames.jsonl").write_text('{"metrics":[]}\n', encoding="utf-8")
    document = {
        "schema_version": 1,
        "logs": {
            "enabled": True,
            "source": {
                "path": "events.txt",
                "format": "%m",
                "multiline": {"first_line_pattern": "["},
            },
            "outputs": [{"type": "stdout"}],
        },
        "metrics": {
            "enabled": True,
            "source": {"path": "frames.jsonl"},
            "pull": {"enabled": True},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    result = validate_config_file(config_path)
    assert any("invalid multiline regex" in item.message for item in result.errors)
    assert any("line 1" in item.message for item in result.errors)


def test_missing_and_oversized_metric_source(tmp_path: Path) -> None:
    """Missing files and maximum-line limits become source diagnostics."""

    document = {
        "schema_version": 1,
        "metrics": {
            "enabled": True,
            "source": {"path": "missing.jsonl"},
            "pull": {"enabled": True},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    assert not validate_config_file(config_path).valid
    (tmp_path / "missing.jsonl").write_text("{}\n", encoding="utf-8")
    document["metrics"]["source"]["maximum_line_bytes"] = 1
    config_path.write_text(json.dumps(document), encoding="utf-8")
    assert "exceeds maximum_line_bytes" in validate_config_file(config_path).errors[0].message


def test_metric_routes_push_scheme_and_ca_file_are_preflighted(tmp_path: Path) -> None:
    """Reserved routes, unsupported URL schemes, and missing CA files fail validation."""

    (tmp_path / "frames.jsonl").write_text(
        '{"metrics":[{"name":"up","type":"gauge","help":"Up.","samples":[{"value":1}]}]}\n',
        encoding="utf-8",
    )
    document = {
        "schema_version": 1,
        "metrics": {
            "enabled": True,
            "source": {"path": "frames.jsonl"},
            "pull": {"enabled": True, "path": "/healthz"},
            "push": {
                "enabled": True,
                "url": "ftp://example.test",
                "job": "demo",
                "interval_seconds": 1,
                "tls": {"ca_file": "missing.pem"},
            },
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    messages = [diagnostic.message for diagnostic in validate_config_file(config_path).errors]
    assert any("reserved route" in message for message in messages)
    assert any("http or https" in message for message in messages)
    assert any("missing.pem" in message for message in messages)
