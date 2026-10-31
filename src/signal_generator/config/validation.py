# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Schema-backed configuration validation with stable, user-facing diagnostics."""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from signal_generator.config.loader import apply_environment_overrides, read_json_document
from signal_generator.constants import (
    KEY_DEPLOYMENT,
    KEY_ENABLED,
    KEY_LOGS,
    KEY_METRICS,
    KEY_PATH,
    KEY_SOURCE,
    MAXIMUM_VALIDATION_ERRORS,
    RESULT_VERSION,
)

CODE_JSON = "SGCFG-JSON-001"
CODE_SCHEMA = "SGCFG-SCHEMA-001"
CODE_SEMANTIC = "SGCFG-SEMANTIC-001"
CODE_SOURCE = "SGCFG-SOURCE-001"
CODE_METRIC_FRAME = "SGDATA-SCHEMA-001"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One stable error or warning suitable for text and machine output."""

    code: str
    severity: str
    source: str
    instance_path: str
    schema_path: str
    message: str
    hint: str | None = None
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the diagnostic without null optional fields."""

        payload: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "source": self.source,
            "instance_path": self.instance_path,
            "schema_path": self.schema_path,
            "message": self.message,
        }
        for key, value in (("hint", self.hint), ("line", self.line), ("column", self.column)):
            if value is not None:
                payload[key] = value
        return payload


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Aggregate deterministic validation errors and warnings."""

    errors: tuple[Diagnostic, ...] = ()
    warnings: tuple[Diagnostic, ...] = ()

    @property
    def valid(self) -> bool:
        """Return true when no error diagnostic was produced."""

        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize the versioned result envelope used by CLI JSON mode."""

        return {
            "result_version": RESULT_VERSION,
            "valid": self.valid,
            "errors": [diagnostic.to_dict() for diagnostic in self.errors],
            "warnings": [diagnostic.to_dict() for diagnostic in self.warnings],
        }


def load_schema(name: str) -> dict[str, Any]:
    """Load a packaged JSON Schema by file name through importlib resources."""

    schema_resource = files("signal_generator.schemas").joinpath(name)
    return json.loads(schema_resource.read_text(encoding="utf-8"))


def validate_config_file(
    path: str | Path,
    *,
    schema_only: bool = False,
    strict: bool = False,
    environ: Mapping[str, str] | None = None,
) -> ValidationResult:
    """Validate a configuration file without opening outputs, listeners, or network connections."""

    del strict  # Reserved for warning promotion when deprecations are introduced.
    config_path = Path(path).expanduser().resolve()
    try:
        document = read_json_document(config_path)
        effective = apply_environment_overrides(document, environ)
    except json.JSONDecodeError as error:
        return ValidationResult((_json_diagnostic(config_path, error),))
    except (OSError, UnicodeError, ValueError) as error:
        return ValidationResult((_simple_diagnostic(CODE_SOURCE, config_path, str(error)),))
    errors = list(_schema_diagnostics(effective, "config.schema.json", config_path))
    if not errors and not schema_only:
        errors.extend(_semantic_diagnostics(effective, config_path))
        errors.extend(_source_diagnostics(effective, config_path))
    ordered = sorted(errors, key=_diagnostic_sort_key)[:MAXIMUM_VALIDATION_ERRORS]
    return ValidationResult(tuple(ordered))


def _json_diagnostic(path: Path, error: json.JSONDecodeError) -> Diagnostic:
    """Translate a JSON parser exception into the stable validation envelope."""

    return Diagnostic(
        CODE_JSON,
        "error",
        str(path),
        "",
        "",
        error.msg,
        "correct the JSON syntax at the reported line and column",
        error.lineno,
        error.colno,
    )


def _simple_diagnostic(code: str, path: Path, message: str, pointer: str = "") -> Diagnostic:
    """Create a diagnostic for non-schema file or semantic failures."""

    return Diagnostic(code, "error", str(path), pointer, "", message)


def _schema_diagnostics(document: Any, schema_name: str, source: Path) -> Iterable[Diagnostic]:
    """Yield translated Draft 2020-12 errors in deterministic instance-path order."""

    validator = Draft202012Validator(load_schema(schema_name), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    for error in errors:
        message, hint = _friendly_schema_message(error)
        yield Diagnostic(
            CODE_SCHEMA if schema_name == "config.schema.json" else CODE_METRIC_FRAME,
            "error",
            str(source),
            _json_pointer(error.absolute_path),
            _json_pointer(error.absolute_schema_path),
            message,
            hint,
        )


def _friendly_schema_message(error: ValidationError) -> tuple[str, str | None]:
    """Translate common validator messages into field-oriented language and suggestions."""

    handler = _SCHEMA_MESSAGE_HANDLERS.get(str(error.validator))
    return handler(error) if handler else (error.message, None)


def _additional_property_message(error: ValidationError) -> tuple[str, str | None]:
    """Suggest the nearest supported property for an unknown object member."""

    match = re.search(r"\('([^']+)' was unexpected\)", error.message)
    unknown = match.group(1) if match else "unknown field"
    properties = error.schema.get("properties", {}) if isinstance(error.schema, dict) else {}
    choices = difflib.get_close_matches(unknown, properties.keys(), n=1, cutoff=0.7)
    hint = f"did you mean '{choices[0]}'?" if choices else "remove the unsupported property"
    return f"unknown property '{unknown}'", hint


def _required_message(error: ValidationError) -> tuple[str, str]:
    """Name a missing required property and the direct corrective action."""

    match = re.search(r"'([^']+)' is a required property", error.message)
    field = match.group(1) if match else "field"
    return f"required property '{field}' is missing", f"add '{field}' to this object"


def _value_message(prefix: str, error: ValidationError) -> tuple[str, None]:
    """Build a simple message using the validator's configured comparison value."""

    return f"{prefix} {error.validator_value}", None


def _enum_message(error: ValidationError) -> tuple[str, None]:
    """List the complete supported enum values in deterministic schema order."""

    choices = ", ".join(repr(value) for value in error.validator_value)
    return f"must be one of: {choices}", None


def _alternative_message(error: ValidationError) -> tuple[str, str]:
    """Replace nested schema-combinator vocabulary with a user-oriented hint."""

    del error
    return "value does not match any supported form", "check the documented field alternatives"


_SCHEMA_MESSAGE_HANDLERS = {
    "additionalProperties": _additional_property_message,
    "required": _required_message,
    "type": lambda error: _value_message("expected", error),
    "exclusiveMinimum": lambda error: _value_message("must be greater than", error),
    "minimum": lambda error: _value_message("must be at least", error),
    "enum": _enum_message,
    "const": lambda error: (f"must be {error.validator_value!r}", None),
    "anyOf": _alternative_message,
    "oneOf": _alternative_message,
}


def _json_pointer(path_parts: Iterable[Any]) -> str:
    """Encode a jsonschema path as an RFC 6901 JSON Pointer."""

    escaped = (str(part).replace("~", "~0").replace("/", "~1") for part in path_parts)
    return "".join(f"/{part}" for part in escaped)


def _semantic_diagnostics(document: Mapping[str, Any], source: Path) -> list[Diagnostic]:
    """Check cross-field rules that are clearer in Python than JSON Schema."""

    diagnostics: list[Diagnostic] = []
    deployment = document.get(KEY_DEPLOYMENT, {})
    if isinstance(deployment, Mapping) and deployment.get("mode", "standalone") == "embedded_quart":
        for field_name in ("route_prefix", "runtime_id"):
            if not deployment.get(field_name):
                diagnostics.append(
                    _simple_diagnostic(
                        CODE_SEMANTIC,
                        source,
                        f"{field_name} is required in embedded_quart mode",
                        f"/{KEY_DEPLOYMENT}/{field_name}",
                    )
                )
    logs = document.get(KEY_LOGS, {})
    if isinstance(logs, Mapping) and logs.get(KEY_ENABLED):
        source_config = logs.get(KEY_SOURCE, {})
        pattern = (
            source_config.get("multiline", {}).get("first_line_pattern")
            if isinstance(source_config, Mapping)
            else None
        )
        if pattern:
            try:
                re.compile(str(pattern))
            except re.error as error:
                diagnostics.append(
                    _simple_diagnostic(
                        CODE_SEMANTIC,
                        source,
                        f"invalid multiline regex: {error}",
                        "/logs/source/multiline/first_line_pattern",
                    )
                )
    return diagnostics


def _source_diagnostics(document: Mapping[str, Any], config_path: Path) -> list[Diagnostic]:
    """Validate referenced log and metric sources without creating runtime resources."""

    diagnostics: list[Diagnostic] = []
    base_path = config_path.parent
    logs = document.get(KEY_LOGS, {})
    if isinstance(logs, Mapping) and logs.get(KEY_ENABLED):
        source = logs.get(KEY_SOURCE, {})
        if isinstance(source, Mapping):
            source_path = _resolve_source_path(base_path, source.get(KEY_PATH))
            diagnostics.extend(
                _readability_diagnostics(
                    source_path, source.get("encoding", "utf-8"), "/logs/source/path"
                )
            )
    metrics = document.get(KEY_METRICS, {})
    if isinstance(metrics, Mapping) and metrics.get(KEY_ENABLED):
        metric_source = metrics.get(KEY_SOURCE, {})
        if isinstance(metric_source, Mapping):
            source_path = _resolve_source_path(base_path, metric_source.get(KEY_PATH))
            diagnostics.extend(_metric_source_diagnostics(source_path, metric_source))
    return diagnostics


def _resolve_source_path(base_path: Path, configured_path: Any) -> Path:
    """Resolve a configured path relative to its configuration document directory."""

    source_path = Path(str(configured_path)).expanduser()
    return source_path if source_path.is_absolute() else (base_path / source_path).resolve()


def _readability_diagnostics(path: Path, encoding: Any, pointer: str) -> list[Diagnostic]:
    """Read a complete source to detect missing files, encoding errors, and permission failures."""

    try:
        path.read_text(encoding=str(encoding))
    except (OSError, UnicodeError) as error:
        return [_simple_diagnostic(CODE_SOURCE, path, str(error), pointer)]
    return []


def _metric_source_diagnostics(path: Path, source: Mapping[str, Any]) -> list[Diagnostic]:
    """Validate each non-empty metric JSONL line against the packaged frame schema."""

    diagnostics: list[Diagnostic] = []
    maximum_bytes = int(source.get("maximum_line_bytes", 10_485_760))
    try:
        with path.open("r", encoding=str(source.get("encoding", "utf-8"))) as source_file:
            for line_number, raw_line in enumerate(source_file, start=1):
                if len(raw_line.encode("utf-8")) > maximum_bytes:
                    diagnostics.append(
                        _simple_diagnostic(
                            CODE_SOURCE, path, f"line {line_number} exceeds maximum_line_bytes"
                        )
                    )
                    continue
                if not raw_line.strip():
                    continue
                try:
                    frame = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    diagnostics.append(
                        Diagnostic(
                            CODE_JSON,
                            "error",
                            str(path),
                            "",
                            "",
                            error.msg,
                            line=line_number,
                            column=error.colno,
                        )
                    )
                    continue
                for diagnostic in _schema_diagnostics(frame, "metric_frame.schema.json", path):
                    diagnostics.append(
                        Diagnostic(
                            diagnostic.code,
                            diagnostic.severity,
                            diagnostic.source,
                            diagnostic.instance_path,
                            diagnostic.schema_path,
                            f"line {line_number}: {diagnostic.message}",
                            diagnostic.hint,
                            line_number,
                        )
                    )
    except (OSError, UnicodeError) as error:
        diagnostics.append(
            _simple_diagnostic(CODE_SOURCE, path, str(error), "/metrics/source/path")
        )
    return diagnostics


def _diagnostic_sort_key(diagnostic: Diagnostic) -> tuple[str, int, str, str]:
    """Return the stable ordering key used by text and JSON CLI output."""

    return (diagnostic.source, diagnostic.line or 0, diagnostic.instance_path, diagnostic.code)
