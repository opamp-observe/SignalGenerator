# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Shared constants that keep configuration and structured payload keys consistent."""

SCHEMA_VERSION = 1
RESULT_VERSION = 1
DEFAULT_LOG_LEVEL = "DEBUG"
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0
DEFAULT_DATETIME_FORMAT = "yyyy/MM/dd HH:mm:ss"
DEFAULT_INTERVAL_MILLISECONDS = 1000
DEFAULT_ACCELERATION = 1.0
DEFAULT_OUTPUT_TIMEOUT_SECONDS = 5.0
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 0.1
DEFAULT_MAXIMUM_RETRY_BACKOFF_SECONDS = 30.0
DEFAULT_METRICS_PORT = 9108
DEFAULT_PUSH_INTERVAL_SECONDS = 15.0
DEFAULT_MAXIMUM_LINE_BYTES = 10_485_760
DEFAULT_MAXIMUM_SAMPLES_PER_FRAME = 100_000
MAXIMUM_VALIDATION_ERRORS = 100

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_STARTUP = 4
EXIT_RUNTIME = 5

KEY_SCHEMA_VERSION = "schema_version"
KEY_RUNTIME = "runtime"
KEY_DEPLOYMENT = "deployment"
KEY_LOGS = "logs"
KEY_METRICS = "metrics"
KEY_TRACES = "traces"
KEY_ENABLED = "enabled"
KEY_SOURCE = "source"
KEY_PATH = "path"
KEY_FORMAT = "format"
KEY_OUTPUTS = "outputs"
KEY_TYPE = "type"
KEY_REPLAY = "replay"
KEY_DEFAULTS = "defaults"
KEY_PULL = "pull"
KEY_PUSH = "push"
KEY_FRAME = "frame"
KEY_OBSERVED_AT = "observed_at"
KEY_METADATA = "metadata"
KEY_METRIC_FAMILIES = "metrics"
KEY_NAME = "name"
KEY_HELP = "help"
KEY_UNIT = "unit"
KEY_SAMPLES = "samples"
KEY_LABELS = "labels"
KEY_VALUE = "value"
KEY_INFO = "info"
KEY_BUCKETS = "buckets"
KEY_QUANTILES = "quantiles"
KEY_SUM = "sum"
KEY_COUNT = "count"
KEY_BUCKET_BOUND = "le"
KEY_QUANTILE = "quantile"
KEY_URL = "url"
KEY_TLS = "tls"
KEY_CA_FILE = "ca_file"

ENV_CONFIG = "SIGNAL_GENERATOR_CONFIG"
ENV_LOG_LEVEL = "SIGNAL_GENERATOR_LOG_LEVEL"
ENV_METRICS_HOST = "SIGNAL_GENERATOR_METRICS_HOST"
ENV_METRICS_PORT = "SIGNAL_GENERATOR_METRICS_PORT"
ENV_PUSH_URL = "SIGNAL_GENERATOR_PUSH_URL"
ENV_PUSH_INTERVAL = "SIGNAL_GENERATOR_PUSH_INTERVAL_SECONDS"
ENV_DEPLOYMENT_MODE = "SIGNAL_GENERATOR_DEPLOYMENT_MODE"
ENV_ROUTE_PREFIX = "SIGNAL_GENERATOR_ROUTE_PREFIX"

SECRET_KEY_FRAGMENTS = ("authorization", "password", "secret", "token", "x-api-key")
REDACTED_VALUE = "<redacted>"
