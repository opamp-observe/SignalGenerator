# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Typed immutable configuration models used by replay components."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from signal_generator.constants import (
    DEFAULT_ACCELERATION,
    DEFAULT_DATETIME_FORMAT,
    DEFAULT_INTERVAL_MILLISECONDS,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAXIMUM_LINE_BYTES,
    DEFAULT_MAXIMUM_RETRY_BACKOFF_SECONDS,
    DEFAULT_MAXIMUM_SAMPLES_PER_FRAME,
    DEFAULT_METRICS_PORT,
    DEFAULT_OUTPUT_TIMEOUT_SECONDS,
    DEFAULT_PUSH_INTERVAL_SECONDS,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Process-wide logging and graceful-shutdown configuration."""

    log_level: str = DEFAULT_LOG_LEVEL
    shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS
    diagnostics: bool = False


@dataclass(frozen=True, slots=True)
class DeploymentConfig:
    """Host mode and failure-policy configuration."""

    mode: str = "standalone"
    failure_policy: str = "fail_process"
    route_prefix: str | None = None
    runtime_id: str | None = None


@dataclass(frozen=True, slots=True)
class LogSourceConfig:
    """Location and token grammar for one log-event source file."""

    path: Path
    format: str
    datetime_format: str = DEFAULT_DATETIME_FORMAT
    separator: str | None = None
    encoding: str = "utf-8"
    unescape_newlines: bool = False
    first_line_pattern: str | None = None


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    """Cycle count and monotonic scheduling controls for log replay."""

    cycles: int | str = 1
    default_interval_ms: int = DEFAULT_INTERVAL_MILLISECONDS
    acceleration: float = DEFAULT_ACCELERATION
    start_delay_ms: int = 0
    loop_gap_ms: int = 0


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Bounded retry policy for output writes."""

    maximum_attempts: int = DEFAULT_RETRY_ATTEMPTS
    initial_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS
    maximum_backoff_seconds: float = DEFAULT_MAXIMUM_RETRY_BACKOFF_SECONDS


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """Output adapter selection and adapter-owned options."""

    type: str
    failure_policy: str = "fail"
    timeout_seconds: float = DEFAULT_OUTPUT_TIMEOUT_SECONDS
    retry: RetryConfig = field(default_factory=RetryConfig)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LogDefaults:
    """Fallback event fields used when source tokens omit values."""

    process: str = "Thread-1"
    location: str = "signal_generator"
    log_level: str = "INFO"


@dataclass(frozen=True, slots=True)
class LogsConfig:
    """Complete log parsing, formatting, scheduling, and output configuration."""

    enabled: bool
    source: LogSourceConfig
    format: str = "%t %m"
    datetime_format: str = DEFAULT_DATETIME_FORMAT
    separator: str = " "
    defaults: LogDefaults = field(default_factory=LogDefaults)
    replay: ReplayConfig = field(default_factory=ReplayConfig)
    outputs: tuple[OutputConfig, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricSourceConfig:
    """Metric JSON Lines source and bounded loading controls."""

    path: Path
    encoding: str = "utf-8"
    eof: str = "loop"
    maximum_line_bytes: int = DEFAULT_MAXIMUM_LINE_BYTES
    maximum_samples_per_frame: int = DEFAULT_MAXIMUM_SAMPLES_PER_FRAME


@dataclass(frozen=True, slots=True)
class PullConfig:
    """Standalone Prometheus exposition endpoint configuration."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = DEFAULT_METRICS_PORT
    path: str = "/metrics"
    include_self_metrics: bool = True


@dataclass(frozen=True, slots=True)
class BasicAuthConfig:
    """Pushgateway basic-auth configuration with environment-backed password."""

    username: str
    password_env: str


@dataclass(frozen=True, slots=True)
class TlsConfig:
    """Pushgateway server-certificate verification configuration."""

    verify: bool = True
    ca_file: Path | None = None


@dataclass(frozen=True, slots=True)
class PushConfig:
    """Scheduled Pushgateway delivery configuration."""

    enabled: bool = False
    protocol: str = "pushgateway"
    url: str | None = None
    job: str | None = None
    grouping_key: dict[str, str] = field(default_factory=dict)
    interval_seconds: float = DEFAULT_PUSH_INTERVAL_SECONDS
    timeout_seconds: float = DEFAULT_OUTPUT_TIMEOUT_SECONDS
    method: str = "replace"
    basic_auth: BasicAuthConfig | None = None
    bearer_token_env: str | None = None
    tls: TlsConfig = field(default_factory=TlsConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    use_source_timing: bool = False


@dataclass(frozen=True, slots=True)
class MetricsConfig:
    """Complete metric source, pull, and push replay configuration."""

    enabled: bool
    source: MetricSourceConfig | None = None
    pull: PullConfig = field(default_factory=PullConfig)
    push: PushConfig = field(default_factory=PushConfig)


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Top-level typed configuration required by implemented phases."""

    schema_version: int
    runtime: RuntimeConfig
    deployment: DeploymentConfig
    logs: LogsConfig | None
    metrics: MetricsConfig | None
    traces: dict[str, Any] | None
