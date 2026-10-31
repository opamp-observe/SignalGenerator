# Configuration design

## 1. Canonical configuration

The canonical configuration is a UTF-8 JSON document with `schema_version: 1`. JSON is selected so
the standalone tool, container, and OpAMP remote-configuration path use the same representation
without requiring a YAML parser.

Example:

```json
{
  "schema_version": 1,
  "runtime": {
    "log_level": "DEBUG",
    "shutdown_timeout_seconds": 10
  },
  "deployment": {
    "mode": "standalone",
    "failure_policy": "fail_process"
  },
  "logs": {
    "enabled": true,
    "source": {
      "path": "log_events.txt",
      "format": "%t %m",
      "datetime_format": "yyyy/MM/dd HH:mm:ss",
      "separator": " ",
      "unescape_newlines": false
    },
    "format": "%t >%l< %m",
    "datetime_format": "yyyy/MM/dd HH:mm:ss",
    "separator": " ",
    "defaults": {
      "process": "Thread-1",
      "location": "com.demo",
      "log_level": "INFO"
    },
    "replay": {
      "cycles": 1,
      "default_interval_ms": 1000,
      "acceleration": 1.0
    },
    "outputs": [
      {
        "type": "stdout"
      }
    ]
  },
  "metrics": {
    "enabled": true,
    "source": {
      "path": "nginx_metrics.jsonl",
      "eof": "loop"
    },
    "pull": {
      "enabled": true,
      "host": "0.0.0.0",
      "port": 9108,
      "path": "/metrics"
    },
    "push": {
      "enabled": false,
      "protocol": "pushgateway",
      "url": "http://pushgateway:9091",
      "job": "nginx_replay",
      "grouping_key": {
        "instance": "demo-nginx"
      },
      "interval_seconds": 15,
      "timeout_seconds": 5,
      "retry": {
        "maximum_attempts": 5,
        "initial_backoff_seconds": 1,
        "maximum_backoff_seconds": 30
      }
    }
  }
}
```

Relative file paths resolve against the directory containing the configuration file, never against
an incidental process working directory.

## 2. Top-level sections

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | integer | Yes | Must be `1` for the first release. |
| `runtime` | object | No | Process logging, shutdown, and diagnostics. |
| `deployment` | object | No | Standalone or embedded host behavior. |
| `logs` | object | No | Log replay configuration. |
| `metrics` | object | No | Metric replay configuration. |
| `traces` | object | No | Reserved namespace; `enabled` must remain false in schema version 1. |

At least one of `logs.enabled` or `metrics.enabled` must be true.

Unknown fields are rejected in strict mode. The normal `run` command uses strict mode so a typo
cannot silently disable intended behavior. A future migration command may use permissive parsing.

## 3. Runtime section

| Field | Type | Default | Validation |
|---|---|---|---|
| `log_level` | string | `DEBUG` | Standard Python level name. |
| `shutdown_timeout_seconds` | number | `10` | Greater than zero. |
| `diagnostics` | boolean | `false` | Enables additional non-secret diagnostics. |

The default log level follows the repository's agent controls. Container deployments may override
it with `SIGNAL_GENERATOR_LOG_LEVEL`.

### 3.1 Deployment section

| Field | Type | Default | Description |
|---|---|---|---|
| `mode` | string | `standalone` | `standalone` or `embedded_quart`. |
| `failure_policy` | string | mode-specific | `fail_process` or `isolate`. |
| `route_prefix` | string | runtime-specific | Required unique prefix in embedded mode. |
| `runtime_id` | string | unset | Required unique simulator runtime ID in embedded mode. |

The console command rejects `embedded_quart`; only the unified consumer-simulator application may
select that mode through the library attachment API. The adapter rejects a standalone
configuration that would try to bind a second listener. The OpAMP provider does not load this
configuration or host SignalGenerator.

The `signal-generator-opamp-sim` adapter configuration owns runtime IDs, scenario paths, and route
prefixes as described in [opamp_integration_design.md](opamp_integration_design.md). Relative
scenario paths resolve against the adapter configuration file. Environment variables remain higher
precedence.

## 4. Log section

### 4.1 Source

| Field | Type | Required | Description |
|---|---|---|---|
| `path` | string | Yes | Input event file. |
| `format` | string | Yes | Original-style token format. |
| `datetime_format` | string | Conditional | Required for absolute timestamp parsing. |
| `separator` | string | No | Field separator; defaults to whitespace behavior. |
| `encoding` | string | No | Defaults to `utf-8`. |
| `unescape_newlines` | boolean | No | Converts literal `\n` in messages to newlines. |
| `multiline.first_line_pattern` | string | No | Regex identifying the start of a record. |

Supported compatibility tokens:

| Token | Meaning |
|---|---|
| `%t` | Absolute timestamp or `+N` millisecond relative delay. |
| `%m` | Message. |
| `%l` | Log level. |
| `%p` | Process or thread identifier. |
| `%c` | Source/class/location. |
| `%i` | One-based cycle number in output formats. |
| `%j` | One-based record number within a cycle in output formats. |

Python datetime syntax differs from Java `DateTimeFormatter`. The legacy adapter must translate the
documented common patterns or return an actionable validation error when it cannot translate one.

### 4.2 Replay

| Field | Type | Default | Validation |
|---|---|---|---|
| `cycles` | integer or `"forever"` | `1` | Positive integer or explicit infinite value. |
| `default_interval_ms` | integer | `1000` | Zero or greater. |
| `acceleration` | number | `1.0` | Greater than zero. |
| `start_delay_ms` | integer | `0` | Zero or greater. |
| `start_at` | RFC 3339 string or `"now"` | `now` | Anchor for time shifting. |
| `loop_gap_ms` | integer | `0` | Delay between cycles. |
| `source_priority` | integer | `100` | Stable cross-source ordering tie-breaker. |

### 4.3 Outputs

Common output fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | Required | Built-in or plugin output name. |
| `failure_policy` | string | `fail` | `fail`, `retry`, or `continue`. |
| `timeout_seconds` | number | `5` | Network operations only. |
| `retry` | object | bounded defaults | Retry policy when selected. |

Built-in-specific fields:

- `file`: `path`, `mode`, `flush_each_event`.
- `http`: `url`, `method`, `headers`, `content_type`.
- `tcp`: `host`, `port`, `connect_timeout_seconds`, `delimiter`.
- `python_logging`: `logger_name`, `level`.
- `stdout` and `stderr`: no required extra fields.
- `plugin`: `plugin_name` and a plugin-owned `options` object.

Header values whose keys match `authorization`, `proxy-authorization`, `x-api-key`, or configured
secret patterns are redacted from logs and effective-config output.

## 5. Metrics section

### 5.1 Source

| Field | Type | Default | Description |
|---|---|---|---|
| `path` | string | Required | Metric-frame JSONL path. |
| `encoding` | string | `utf-8` | Source encoding. |
| `eof` | string | `loop` | `loop`, `hold_last`, `stop`, or `error`. |
| `maximum_line_bytes` | integer | `10485760` | Safety limit per frame. |
| `maximum_samples_per_frame` | integer | `100000` | Safety limit after expansion. |

### 5.2 Pull

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | `false` | Enables the exposition server. |
| `host` | string | `127.0.0.1` | Listen address. |
| `port` | integer | `9108` | Listen port. |
| `path` | string | `/metrics` | Metrics route. |
| `include_self_metrics` | boolean | `true` | Adds `signal_generator_*` metrics. |

The container example overrides `host` to `0.0.0.0`. The standalone default does not expose the
service beyond the local host.

### 5.3 Push

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | `false` | Enables scheduled pushes. |
| `protocol` | string | `pushgateway` | Initial supported value. |
| `url` | string | Required | Pushgateway base URL. |
| `job` | string | Required | Pushgateway job label. |
| `grouping_key` | object | `{}` | Stable grouping labels. |
| `interval_seconds` | number | Required | Delay after each successful push. |
| `timeout_seconds` | number | `5` | Per-request timeout. |
| `method` | string | `replace` | `replace` uses PUT; future `add` may use POST. |
| `basic_auth.username` | string | unset | Prefer environment injection. |
| `basic_auth.password_env` | string | unset | Environment variable containing the password. |
| `bearer_token_env` | string | unset | Environment variable containing a token. |
| `tls.verify` | boolean | `true` | Server certificate verification. |
| `tls.ca_file` | string | unset | Optional CA file. |
| `retry` | object | bounded defaults | Retry settings. |
| `use_source_timing` | boolean | `false` | Schedule pushes from `observed_at` rather than only the interval. |

Authentication modes are mutually exclusive. Secrets are resolved at runtime and never written to
the effective configuration.

## 6. Metric-frame JSON Lines contract

Every non-empty line is a JSON object representing one complete frame.

```json
{"frame":1,"observed_at":"2026-01-01T00:00:00Z","metrics":[{"name":"nginx_up","type":"gauge","help":"Whether the NGINX target is reachable.","samples":[{"labels":{"instance":"demo-nginx"},"value":1}]},{"name":"nginx_connections_active","type":"gauge","help":"Active NGINX connections.","samples":[{"labels":{"instance":"demo-nginx"},"value":4}]},{"name":"nginx_http_requests_total","type":"counter","help":"Total HTTP requests handled by NGINX.","samples":[{"labels":{"instance":"demo-nginx"},"value":1200}]}]}
```

The physical file contains one such object per line. The example is shown as a single line
intentionally.

### 6.1 Frame fields

| Field | Type | Required | Description |
|---|---|---|---|
| `frame` | integer or string | No | Human-readable frame identifier. |
| `observed_at` | RFC 3339 string | No | Source metadata; not an exported sample timestamp by default. |
| `metrics` | array | Yes | One or more metric family definitions. |
| `metadata` | object | No | Free-form non-exported scenario metadata. |

### 6.2 Metric family fields

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Valid Prometheus metric name without generated suffixes. |
| `type` | string | Yes | `counter`, `gauge`, `histogram`, `summary`, `info`, or `untyped`. |
| `help` | string | Yes | Stable help text across frames. |
| `unit` | string | No | OpenMetrics unit metadata where supported. |
| `samples` | array | Yes | One or more labelled values. |

Metric names beginning with `signal_generator_` are reserved.

### 6.3 Scalar samples

Counters, gauges, and untyped metrics use:

```json
{
  "labels": {
    "host": "nginx-1"
  },
  "value": 42.5
}
```

Counter values must be non-negative. A decrease between frames is allowed because replay scenarios
may model a process restart; the exact source snapshot is exposed.

Info samples use labels as the information payload and an optional stable series-label object:

```json
{
  "labels": {
    "instance": "nginx-1"
  },
  "info": {
    "version": "1.27.0"
  }
}
```

### 6.4 Histogram samples

```json
{
  "labels": {
    "host": "nginx-1"
  },
  "buckets": [
    {"le": 0.1, "count": 80},
    {"le": 0.5, "count": 95},
    {"le": "+Inf", "count": 100}
  ],
  "sum": 16.25,
  "count": 100
}
```

Bucket bounds must be strictly increasing, bucket counts must be cumulative and non-decreasing,
the `+Inf` count must equal `count`, and `sum` must be finite.

### 6.5 Summary samples

```json
{
  "labels": {
    "host": "nginx-1"
  },
  "quantiles": [
    {"quantile": 0.5, "value": 0.12},
    {"quantile": 0.9, "value": 0.40},
    {"quantile": 0.99, "value": 0.95}
  ],
  "sum": 16.25,
  "count": 100
}
```

Quantiles must be unique and between zero and one inclusive.

### 6.6 Label rules

- Names must match Prometheus label syntax.
- `__name__` and labels beginning with `__` are rejected.
- Label-name sets for one metric family remain stable across frames.
- Duplicate label sets within one family and frame are rejected.
- Label values are converted only from JSON strings; implicit number-to-string conversion is not
  allowed.

### 6.7 Numeric rules

- JSON numbers and the strings `"NaN"`, `"+Inf"`, and `"-Inf"` are accepted where the metric type
  permits them.
- Other numeric strings are rejected to catch accidental quoting.
- Histogram counts and summary counts are non-negative integers.
- Ordinary sample values must be finite unless an explicit special value is used.

## 7. Environment overrides

Initial override set:

| Environment variable | Target |
|---|---|
| `SIGNAL_GENERATOR_CONFIG` | CLI default configuration path. |
| `SIGNAL_GENERATOR_LOG_LEVEL` | `runtime.log_level`. |
| `SIGNAL_GENERATOR_METRICS_HOST` | `metrics.pull.host`. |
| `SIGNAL_GENERATOR_METRICS_PORT` | `metrics.pull.port`. |
| `SIGNAL_GENERATOR_PUSH_URL` | `metrics.push.url`. |
| `SIGNAL_GENERATOR_PUSH_INTERVAL_SECONDS` | `metrics.push.interval_seconds`. |
| `SIGNAL_GENERATOR_DEPLOYMENT_MODE` | `deployment.mode`; normally set by the host adapter. |
| `SIGNAL_GENERATOR_ROUTE_PREFIX` | `deployment.route_prefix` in embedded mode. |

Secrets are referenced by named environment variables inside the configuration rather than through
a large fixed list of secret-specific overrides.

## 8. CLI contract

```text
signal-generator run --config PATH
signal-generator validate --config PATH [--format text|json] [--schema-only] [--strict]
signal-generator print-effective-config --config PATH
signal-generator convert-properties --input PATH --output PATH
signal-generator --version
```

`validate` is a read-only preflight command. By default it parses the document, validates it against
the schema selected by `schema_version`, applies configuration-level semantic checks, resolves paths,
and validates referenced source files. It never opens network listeners, connects to outputs, emits
data, or modifies the configuration. `--schema-only` stops after JSON Schema validation, which makes
it suitable for editors and fast CI checks. `--strict` promotes warnings such as deprecated fields
to errors.

Default `--format text` is optimized for a person at a terminal. `--format json` emits one stable
JSON document to stdout for CI, IDE, and adapter consumption. Text-mode errors go to stderr and a
success summary goes to stdout; JSON mode does not mix prose with its stdout document.

`print-effective-config` redacts secrets and writes deterministic JSON. `convert-properties`
creates a versioned JSON candidate and reports unsupported or ambiguous properties. The converted
file must still pass `validate` before use.

The library also exposes a validation API that accepts a mapping and a base path. Embedded Quart
registration uses that API directly; it must not invoke the CLI in-process.

## 9. Validation behavior

Validation runs in deterministic stages:

1. Read UTF-8 and parse JSON, reporting syntax line and column.
2. Select the supported schema from `schema_version` and apply JSON Schema Draft 2020-12.
3. Apply semantic rules that JSON Schema cannot express clearly, including cross-field constraints,
   route collisions, output compatibility, and environment-reference rules.
4. Resolve referenced paths and validate log and metric source files unless `--schema-only` is used.

Errors are collected where safe, sorted by source and JSON Pointer, and capped at a documented
maximum so a badly malformed file cannot flood the terminal. Every diagnostic contains a stable
code, severity, source, JSON Pointer, user-facing message, and optional hint. Line and column are
included when the parser can determine them. Secret values are never included.

Default text output favors the field name and corrective action over schema vocabulary:

```text
ERROR SGCFG-SCHEMA-004 config.json /metrics/push/interval_seconds
  must be greater than 0; received 0
  hint: set interval_seconds to the required push frequency in seconds

ERROR SGDATA-TYPE-002 nginx_metrics.jsonl:4 /metrics/2/samples/0/value
  expected a number
```

Raw validator phrases such as `is not valid under any of the given schemas` must be translated into
domain language. Unknown properties report a nearest-name suggestion when unambiguous, for example
`unknown property 'metrcis'; did you mean 'metrics'?`. Schema locations may be included in verbose
or JSON output for maintainers, but are not the primary human message.

Machine output follows a versioned result shape:

```json
{
  "result_version": 1,
  "valid": false,
  "errors": [
    {
      "code": "SGCFG-SCHEMA-004",
      "severity": "error",
      "source": "config.json",
      "instance_path": "/metrics/push/interval_seconds",
      "schema_path": "/$defs/push/properties/interval_seconds/exclusiveMinimum",
      "message": "must be greater than 0",
      "hint": "set interval_seconds to the required push frequency in seconds"
    }
  ],
  "warnings": []
}
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Success. |
| `2` | CLI usage error. |
| `3` | Configuration or source validation error. |
| `4` | Startup failure such as port binding or output connection. |
| `5` | Runtime replay failure. |

For the `validate` command only, normal outcomes are `0`, `2`, or `3`; it cannot return startup or
runtime failure codes because it starts no runtime resources.

## 10. Schema artifacts

Implementation should add:

- `schemas/config.schema.json`
- `schemas/metric_frame.schema.json`
- `schemas/validation_result.schema.json`
- schema examples under `examples/`
- contract tests that validate every checked-in example against both JSON Schema and Python models.

The checked-in JSON Schema is the normative structural contract for configuration files. It declares
`$schema` as Draft 2020-12, has a stable `$id`, rejects unknown properties by default, and documents
defaults without silently mutating input. Python models provide typed loading and semantic checks;
contract tests must prove they accept and reject the same structural examples so neither can drift.
The packaged schema is available through `importlib.resources`, allowing editors, CI, containers,
and external tooling to validate the exact schema shipped with the installed wheel.

Schema version 1 includes a reserved `traces` object with `enabled: false` and no payload fields.
This makes the future namespace explicit without accepting configurations that imply unsupported
trace replay.

