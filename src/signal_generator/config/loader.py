# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Load validated configuration with deterministic precedence and path resolution."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from signal_generator.config.models import (
    AppConfig,
    DeploymentConfig,
    LogDefaults,
    LogsConfig,
    LogSourceConfig,
    OutputConfig,
    ReplayConfig,
    RetryConfig,
    RuntimeConfig,
)
from signal_generator.constants import (
    ENV_DEPLOYMENT_MODE,
    ENV_LOG_LEVEL,
    ENV_METRICS_HOST,
    ENV_METRICS_PORT,
    ENV_PUSH_INTERVAL,
    ENV_PUSH_URL,
    ENV_ROUTE_PREFIX,
    KEY_DEFAULTS,
    KEY_DEPLOYMENT,
    KEY_LOGS,
    KEY_METRICS,
    KEY_OUTPUTS,
    KEY_PATH,
    KEY_REPLAY,
    KEY_RUNTIME,
    KEY_SCHEMA_VERSION,
    KEY_SOURCE,
    KEY_TRACES,
)


@dataclass(frozen=True, slots=True)
class LoadedConfiguration:
    """Validated raw and typed configuration plus its source location."""

    path: Path
    effective: dict[str, Any]
    model: AppConfig


class ConfigurationLoadError(ValueError):
    """Indicate that configuration could not be loaded into typed models."""


def read_json_document(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object from ``path`` without applying defaults or overrides."""

    with path.open("r", encoding="utf-8") as source_file:
        document = json.load(source_file)
    if not isinstance(document, dict):
        raise ConfigurationLoadError("configuration root must be an object")
    return document


def apply_environment_overrides(
    document: Mapping[str, Any], environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Apply documented environment overrides to a deep copy of ``document``."""

    environment = os.environ if environ is None else environ
    effective = copy.deepcopy(dict(document))
    metric_environment_keys = {ENV_METRICS_HOST, ENV_METRICS_PORT, ENV_PUSH_URL, ENV_PUSH_INTERVAL}
    if metric_environment_keys.intersection(environment) and KEY_METRICS not in effective:
        effective[KEY_METRICS] = {"enabled": False}
    override_specs = (
        (ENV_LOG_LEVEL, (KEY_RUNTIME, "log_level"), str),
        (ENV_METRICS_HOST, (KEY_METRICS, "pull", "host"), str),
        (ENV_METRICS_PORT, (KEY_METRICS, "pull", "port"), int),
        (ENV_PUSH_URL, (KEY_METRICS, "push", "url"), str),
        (ENV_PUSH_INTERVAL, (KEY_METRICS, "push", "interval_seconds"), float),
        (ENV_DEPLOYMENT_MODE, (KEY_DEPLOYMENT, "mode"), str),
        (ENV_ROUTE_PREFIX, (KEY_DEPLOYMENT, "route_prefix"), str),
    )
    for environment_key, object_path, converter in override_specs:
        if environment_key in environment:
            _set_nested(effective, object_path, converter(environment[environment_key]))
    return effective


def _set_nested(document: dict[str, Any], object_path: tuple[str, ...], value: Any) -> None:
    """Set ``value`` at ``object_path``, creating intermediate dictionaries as needed."""

    target = document
    for path_part in object_path[:-1]:
        child = target.setdefault(path_part, {})
        if not isinstance(child, dict):
            raise ConfigurationLoadError(f"cannot override non-object field {path_part}")
        target = child
    target[object_path[-1]] = value


def load_configuration(
    path: str | Path, environ: Mapping[str, str] | None = None, *, validate: bool = True
) -> LoadedConfiguration:
    """Load, validate, resolve, and type a configuration document from ``path``."""

    config_path = Path(path).expanduser().resolve()
    if validate:
        # Delayed import keeps validation's document helpers reusable without an import-time cycle.
        from signal_generator.config.validation import validate_config_file  # pylint: disable=import-outside-toplevel

        result = validate_config_file(config_path, environ=environ)
        if not result.valid:
            messages = "; ".join(diagnostic.message for diagnostic in result.errors)
            raise ConfigurationLoadError(messages)
    effective = apply_environment_overrides(read_json_document(config_path), environ)
    return LoadedConfiguration(config_path, effective, _build_model(effective, config_path.parent))


def _build_model(document: Mapping[str, Any], base_path: Path) -> AppConfig:
    """Build immutable runtime models after structural and semantic validation succeeds."""

    runtime_data = dict(document.get(KEY_RUNTIME, {}))
    deployment_data = dict(document.get(KEY_DEPLOYMENT, {}))
    logs_data = document.get(KEY_LOGS)
    logs = _build_logs(dict(logs_data), base_path) if isinstance(logs_data, Mapping) else None
    return AppConfig(
        schema_version=int(document[KEY_SCHEMA_VERSION]),
        runtime=RuntimeConfig(**runtime_data),
        deployment=DeploymentConfig(**deployment_data),
        logs=logs,
        metrics=copy.deepcopy(document.get(KEY_METRICS)),
        traces=copy.deepcopy(document.get(KEY_TRACES)),
    )


def _build_logs(document: dict[str, Any], base_path: Path) -> LogsConfig:
    """Build log source, output, replay, and default models from the validated mapping."""

    source_data = dict(document[KEY_SOURCE])
    multiline = dict(source_data.pop("multiline", {}))
    source_path = Path(source_data[KEY_PATH]).expanduser()
    source_data[KEY_PATH] = (
        source_path if source_path.is_absolute() else (base_path / source_path).resolve()
    )
    source_data["first_line_pattern"] = multiline.get("first_line_pattern")
    defaults = LogDefaults(**dict(document.get(KEY_DEFAULTS, {})))
    replay = ReplayConfig(**dict(document.get(KEY_REPLAY, {})))
    outputs = tuple(_build_output(output, base_path) for output in document[KEY_OUTPUTS])
    return LogsConfig(
        enabled=bool(document.get("enabled", False)),
        source=LogSourceConfig(**source_data),
        format=str(document.get("format", "%t %m")),
        datetime_format=str(document.get("datetime_format", "yyyy/MM/dd HH:mm:ss")),
        separator=str(document.get("separator", " ")),
        defaults=defaults,
        replay=replay,
        outputs=outputs,
    )


def _build_output(document: Mapping[str, Any], base_path: Path) -> OutputConfig:
    """Separate common output controls from adapter-owned options and resolve file paths."""

    output_data = dict(document)
    output_type = str(output_data.pop("type"))
    failure_policy = str(output_data.pop("failure_policy", "fail"))
    timeout_seconds = float(output_data.pop("timeout_seconds", 5.0))
    retry = RetryConfig(**dict(output_data.pop("retry", {})))
    if output_type == "file" and KEY_PATH in output_data:
        output_path = Path(output_data[KEY_PATH]).expanduser()
        output_data[KEY_PATH] = str(
            output_path if output_path.is_absolute() else (base_path / output_path).resolve()
        )
    return OutputConfig(output_type, failure_policy, timeout_seconds, retry, output_data)
