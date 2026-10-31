# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Schema-backed adapter configuration, diagnostics, and typed path resolution."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from signal_generator.config.validation import Diagnostic, ValidationResult, validate_config_file

CODE_JSON = "SGOPAMP-JSON-001"
CODE_SCHEMA = "SGOPAMP-SCHEMA-001"
CODE_SEMANTIC = "SGOPAMP-SEMANTIC-001"
CODE_SOURCE = "SGOPAMP-SOURCE-001"
KEY_CONFIG_PATH = "config_path"
KEY_CONSUMER_CONFIG_PATH = "consumer_config_path"
KEY_ID = "id"
KEY_IDENTITY = "identity"
KEY_INSTANCES = "instances"
KEY_NAME = "name"
KEY_RESPONSES_PATH = "responses_path"
KEY_ROUTE_PREFIX = "route_prefix"
KEY_RUNTIME_REFERENCE = "signal_generator_runtime"
KEY_RUNTIMES = "signal_generator_runtimes"
KEY_SERVICE_INSTANCE_UID = "service_instance_uid"
KEY_SUPERVISED = "supervised"


@dataclass(frozen=True, slots=True)
class QuartConfig:
    """Listener settings for the adapter-owned single-worker Quart host."""

    host: str
    port: int
    workers: int = 1


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """One SignalGenerator scenario and its unique route namespace."""

    runtime_id: str
    config_path: Path
    route_prefix: str


@dataclass(frozen=True, slots=True)
class InstanceConfig:  # pylint: disable=too-many-instance-attributes
    """One generic simulated OpAMP client attached to an optional signal runtime."""

    name: str
    consumer_config_path: Path
    responses_path: Path
    signal_generator_runtime: str | None
    service_instance_uid: str
    client_version: str
    config_version: str
    status_port: int = 1


@dataclass(frozen=True, slots=True)
class SupervisedConfig:
    """SignalGenerator child-process settings used only by supervised mode."""

    config_path: Path
    executable_path: str = "signal-generator"
    health_url: str = "http://127.0.0.1:9108/healthz"
    shutdown_timeout_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
# Eight fields mirror the complete top-level adapter ownership contract.
# pylint: disable-next=too-many-instance-attributes
class AdapterConfig:
    """Fully resolved adapter configuration shared by CLI deployment modes."""

    path: Path
    mode: str
    failure_policy: str
    quart: QuartConfig | None
    runtimes: tuple[RuntimeConfig, ...]
    instances: tuple[InstanceConfig, ...]
    supervised: SupervisedConfig | None


def validate_adapter_file(path: str | Path, *, schema_only: bool = False) -> ValidationResult:
    """Validate adapter and referenced files without starting processes or network resources."""

    config_path = Path(path).expanduser().resolve()
    try:
        document = _read_json_object(config_path)
    except json.JSONDecodeError as error:
        return ValidationResult(
            (
                Diagnostic(
                    CODE_JSON,
                    "error",
                    str(config_path),
                    "",
                    "",
                    error.msg,
                    "correct the JSON syntax at the reported line and column",
                    error.lineno,
                    error.colno,
                ),
            )
        )
    except (OSError, UnicodeError, ValueError) as error:
        return ValidationResult((_diagnostic(CODE_SOURCE, config_path, str(error)),))
    diagnostics = list(_schema_diagnostics(document, config_path))
    if not diagnostics:
        diagnostics.extend(_semantic_diagnostics(document, config_path))
    if not diagnostics and not schema_only:
        diagnostics.extend(_referenced_file_diagnostics(document, config_path))
    return ValidationResult(tuple(sorted(diagnostics, key=_diagnostic_key)))


def load_adapter_config(path: str | Path) -> AdapterConfig:
    """Validate and construct immutable adapter models with absolute referenced paths."""

    config_path = Path(path).expanduser().resolve()
    result = validate_adapter_file(config_path)
    if not result.valid:
        raise ValueError("; ".join(diagnostic.message for diagnostic in result.errors))
    document = _read_json_object(config_path)
    base_path = config_path.parent
    quart_raw = document.get("quart")
    quart = QuartConfig(**quart_raw) if isinstance(quart_raw, Mapping) else None
    runtimes = tuple(
        RuntimeConfig(
            str(item[KEY_ID]),
            _resolve_path(base_path, item[KEY_CONFIG_PATH]),
            str(item[KEY_ROUTE_PREFIX]),
        )
        for item in document.get(KEY_RUNTIMES, [])
    )
    instances = tuple(_build_instance(item, base_path) for item in document.get(KEY_INSTANCES, []))
    supervised_raw = document.get(KEY_SUPERVISED)
    supervised = _build_supervised(supervised_raw, base_path)
    return AdapterConfig(
        config_path,
        str(document["mode"]),
        str(document.get("failure_policy", "isolate")),
        quart,
        runtimes,
        instances,
        supervised,
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    """Read a UTF-8 JSON object and reject array or scalar roots."""

    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("configuration root must be an object")
    return document


def _schema_diagnostics(document: Any, source: Path) -> Iterable[Diagnostic]:
    """Translate schema errors into the shared versioned diagnostic envelope."""

    schema_resource = files("signal_generator_opamp_sim.schemas").joinpath(
        "unified_config.schema.json"
    )
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        instance_path = _json_pointer(error.absolute_path)
        schema_path = _json_pointer(error.absolute_schema_path)
        yield Diagnostic(
            CODE_SCHEMA,
            "error",
            str(source),
            instance_path,
            schema_path,
            error.message,
            "correct the named adapter field",
        )


def _semantic_diagnostics(document: Mapping[str, Any], source: Path) -> list[Diagnostic]:
    """Check uniqueness and ownership references that span schema objects."""

    diagnostics: list[Diagnostic] = []
    runtimes = document.get(KEY_RUNTIMES, [])
    instances = document.get(KEY_INSTANCES, [])
    runtime_ids = [str(item.get(KEY_ID, "")) for item in runtimes]
    diagnostics.extend(
        _duplicate_diagnostics(runtime_ids, source, f"/{KEY_RUNTIMES}", "runtime id")
    )
    prefixes = [str(item.get(KEY_ROUTE_PREFIX, "")) for item in runtimes]
    diagnostics.extend(_duplicate_diagnostics(prefixes, source, f"/{KEY_RUNTIMES}", "route prefix"))
    instance_names = [str(item.get(KEY_NAME, "")) for item in instances]
    diagnostics.extend(_duplicate_diagnostics(instance_names, source, f"/{KEY_INSTANCES}", "name"))
    identities = [
        str(item.get(KEY_IDENTITY, {}).get(KEY_SERVICE_INSTANCE_UID, ""))
        for item in instances
    ]
    diagnostics.extend(_duplicate_diagnostics(identities, source, f"/{KEY_INSTANCES}", "identity"))
    known_runtimes = set(runtime_ids)
    for index, instance in enumerate(instances):
        runtime_reference = instance.get(KEY_RUNTIME_REFERENCE)
        if runtime_reference and runtime_reference not in known_runtimes:
            diagnostics.append(
                _diagnostic(
                    CODE_SEMANTIC,
                    source,
                    f"unknown SignalGenerator runtime '{runtime_reference}'",
                    f"/{KEY_INSTANCES}/{index}/{KEY_RUNTIME_REFERENCE}",
                )
            )
    return diagnostics


def _duplicate_diagnostics(
    values: list[str], source: Path, pointer: str, description: str
) -> list[Diagnostic]:
    """Return one actionable diagnostic for each repeated non-empty value."""

    duplicates = sorted({value for value in values if value and values.count(value) > 1})
    return [
        _diagnostic(CODE_SEMANTIC, source, f"duplicate {description} '{value}'", pointer)
        for value in duplicates
    ]


def _referenced_file_diagnostics(
    document: Mapping[str, Any], source: Path
) -> list[Diagnostic]:
    """Validate all nested files without connecting clients or binding Quart."""

    diagnostics: list[Diagnostic] = []
    base_path = source.parent
    for index, runtime in enumerate(document.get(KEY_RUNTIMES, [])):
        scenario_path = _resolve_path(base_path, runtime[KEY_CONFIG_PATH])
        nested = validate_config_file(scenario_path)
        diagnostics.extend(nested.errors)
        if not nested.valid and not nested.errors:
            diagnostics.append(
                _diagnostic(
                    CODE_SOURCE,
                    scenario_path,
                    "invalid SignalGenerator scenario",
                    f"/{KEY_RUNTIMES}/{index}",
                )
            )
    for index, instance in enumerate(document.get(KEY_INSTANCES, [])):
        for field_name in (KEY_CONSUMER_CONFIG_PATH, KEY_RESPONSES_PATH):
            referenced_path = _resolve_path(base_path, instance[field_name])
            try:
                _read_json_object(referenced_path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                diagnostics.append(
                    _diagnostic(
                        CODE_SOURCE,
                        referenced_path,
                        str(error),
                        f"/{KEY_INSTANCES}/{index}/{field_name}",
                    )
                )
    supervised = document.get(KEY_SUPERVISED)
    if isinstance(supervised, Mapping):
        nested = validate_config_file(_resolve_path(base_path, supervised[KEY_CONFIG_PATH]))
        diagnostics.extend(nested.errors)
    return diagnostics


def _build_instance(document: Mapping[str, Any], base_path: Path) -> InstanceConfig:
    """Build one resolved simulator instance from validated input."""

    identity = document[KEY_IDENTITY]
    return InstanceConfig(
        str(document[KEY_NAME]),
        _resolve_path(base_path, document[KEY_CONSUMER_CONFIG_PATH]),
        _resolve_path(base_path, document[KEY_RESPONSES_PATH]),
        document.get(KEY_RUNTIME_REFERENCE),
        str(identity[KEY_SERVICE_INSTANCE_UID]),
        str(identity.get("client_version", "scripted")),
        str(identity.get("config_version", "")),
        int(document.get("status_port", 1)),
    )


def _build_supervised(document: Any, base_path: Path) -> SupervisedConfig | None:
    """Build resolved child-process settings when supervised mode is selected."""

    if not isinstance(document, Mapping):
        return None
    return SupervisedConfig(
        _resolve_path(base_path, document[KEY_CONFIG_PATH]),
        str(document.get("executable_path", "signal-generator")),
        str(document.get("health_url", "http://127.0.0.1:9108/healthz")),
        float(document.get("shutdown_timeout_seconds", 10.0)),
    )


def _resolve_path(base_path: Path, configured: Any) -> Path:
    """Resolve one configured path relative to the adapter document."""

    path = Path(str(configured)).expanduser()
    return path.resolve() if path.is_absolute() else (base_path / path).resolve()


def _diagnostic(
    code: str, source: Path, message: str, instance_path: str = ""
) -> Diagnostic:
    """Construct one shared-envelope adapter diagnostic."""

    return Diagnostic(code, "error", str(source), instance_path, "", message)


def _json_pointer(parts: Iterable[Any]) -> str:
    """Encode schema paths using RFC 6901 escaping."""

    return "".join(
        f"/{str(part).replace('~', '~0').replace('/', '~1')}" for part in parts
    )


def _diagnostic_key(diagnostic: Diagnostic) -> tuple[str, str, str]:
    """Keep validation output deterministic for humans and automation."""

    return diagnostic.source, diagnostic.instance_path, diagnostic.code
