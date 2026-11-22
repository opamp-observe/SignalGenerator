# Solution design

## 1. Purpose

SignalGenerator Python will be an enhanced Python implementation of
[mp3monster/LogGenerator](https://github.com/mp3monster/LogGenerator). It will preserve the
original tool's core purpose—replaying log events from source data into configurable outputs—and
add deterministic Prometheus metrics and OpenTelemetry trace replay.

The original tool supports file, HTTP, TCP, Java logging, standard output, standard error, and
custom output destinations. Its timing is driven by source timestamps or a default offset, with
repeat and acceleration controls. The Python implementation should retain those concepts while
using a versioned configuration model and replaceable Python interfaces.

## 2. Goals

- Replay log events from files with deterministic ordering and timing.
- Read existing log files and time-shift their timestamps so they appear current while preserving
  the original relative intervals.
- Support the original formatting concepts, including `%t`, `%m`, `%l`, `%p`, `%c`, `%i`, and `%j`.
- Provide file, HTTP, TCP, Python logging, Java-util-logging-compatible formatted output, stdout,
  stderr, and plugin-provided log outputs.
- Read Prometheus metric snapshots from a JSON Lines file where one line is one complete frame.
- Expose the next metric frame on every successful scrape of the configured metrics path.
- Push metric frames on a configured interval.
- Keep pull and push replay deterministic when both modes run together.
- Provide health and readiness endpoints that never consume metric frames.
- Provide a container and a reproducible NGINX metrics replay demonstration.
- Expose stable process, configuration, and health contracts for an independently built OpAMP
  simulator adapter.
- Keep OpAMP-specific composition in a separately built adapter module; SignalGenerator core and
  `opamp-observe/opamp-core` contain no SignalGenerator-specific cross-project extension logic.
- Provide strong unit, contract, integration, and container end-to-end coverage.
- Replay OTLP JSON trace captures with current timestamps and loop-safe identities.
- Replay every enabled signal type from one service and one coordinated lifecycle.
- Provide documented reference configurations for common log formats.
- Generate operational SignalGenerator metrics and allow them to be included in test output.
- Release scheduled signals in timestamp order when source timing is available.
- Optionally loop source files for long-running replay scenarios.
- Support both a standalone process and in-process attachment to the unified consumer-simulator
  Quart application.
- Ship as a standards-compliant wheel from a canonical TOML project definition.
- Enforce test coverage and cyclomatic-complexity quality gates.
- Provide schema-backed CLI validation with actionable human diagnostics and stable JSON output.

## 3. Non-goals for the first release

- Generating synthetic metric values during replay. Planned scenario authoring generates a complete,
  inspectable JSON Lines file before replay under [SG-008](roadmap.md).
- Acting as a Prometheus server or long-term metrics store.
- Replacing Prometheus, Pushgateway, or an OpenTelemetry Collector.
- Coupling the core package to OpAMP protocol libraries.
- Guaranteeing compatibility with arbitrary Groovy custom outputter classes.
- Using the simulator as a production telemetry agent.
- Building a user interface.

## 4. Key terminology

| Term | Meaning |
|---|---|
| Event | One input log record after source parsing. |
| Log replay | Timed delivery of events to one or more log outputs. |
| Metric frame | The complete set of metric families and samples represented by one JSONL line. |
| Cursor | The independently tracked next frame for a replay consumer. |
| Pull cursor | Cursor advanced by requests to the metrics endpoint. |
| Push cursor | Cursor advanced by successful scheduled pushes. |
| Cycle | One complete pass through a source file. |
| OpAMP simulator adapter | Independently built integration distribution for child-process supervision or unified hosting. |
| Embedded mode | SignalGenerator runtime and routes hosted inside the unified simulator Quart process. |
| Signal envelope | Internal scheduled item carrying signal type, source time, and payload. |

## 5. Architecture

The colour-coded [UML package and deployment diagrams](uml_architecture.md) show distribution
ownership, allowed dependency directions, and all three supported process permutations. The flow
below focuses on the internal signal paths.

```mermaid
flowchart LR
    Config[Versioned JSON config] --> App[Application orchestrator]

    LogSource[Log source] --> LogParser[Log parser and formatter]
    LogParser --> LogScheduler[Log replay scheduler]
    LogScheduler --> LogOutputs[File / HTTP / TCP / logging / plugin outputs]

    Jsonl[Metric frames JSONL] --> FrameStore[Validated frame store]
    FrameStore --> PullCursor[Pull cursor]
    FrameStore --> PushCursor[Push cursor]
    PullCursor --> Collector[Prometheus collector]
    Collector --> MetricsEndpoint[GET /metrics]
    PushCursor --> PushScheduler[Push scheduler]
    PushScheduler --> PushAdapter[Pushgateway adapter]

    TraceJsonl[OTLP traces JSONL] --> TraceScheduler[Trace replay scheduler]
    TraceScheduler --> TracePush[OTLP HTTP JSON endpoint]

    App --> Standalone[Standalone HTTP adapter]
    App --> Embedded[Embedded Quart adapter]
    Standalone --> Health[GET /healthz and /readyz]
    AdapterHost[signal-generator-opamp-sim unified Quart process] --> Embedded
    Adapter[signal-generator-opamp-sim supervised plugin] -. supervises child .-> Standalone
    Adapter -. polls only .-> Health
```

The log, metric, and trace paths share configuration, lifecycle, diagnostics, and shutdown handling. They
do not share source cursors or timing state.

The application core must not depend on its HTTP host. `SignalGeneratorRuntime` owns configuration,
sources, cursors, schedulers, and lifecycle. A standalone adapter supplies its own HTTP server; an
embedded adapter registers routes and lifecycle hooks on the unified consumer-simulator Quart app.

## 6. Package structure

```text
src/signal_generator/
  __init__.py
  __main__.py
  cli.py
  application.py
  lifecycle.py
  diagnostics.py
  signals.py
  config/
    __init__.py
    models.py
    loader.py
    validation.py
    legacy_properties.py
  logs/
    __init__.py
    models.py
    source.py
    parser.py
    formatter.py
    scheduler.py
    registry.py
    outputs/
      base.py
      file.py
      http.py
      tcp.py
      python_logging.py
      streams.py
  metrics/
    __init__.py
    models.py
    jsonl_source.py
    validation.py
    frame_store.py
    cursor.py
    collector.py
    exposition.py
    push.py
    scheduler.py
  traces/
    source.py
    replay.py
  health/
    __init__.py
    application.py
  embedding/
    __init__.py
    quart.py
tests/
  unit/
  contract/
  integration/
  e2e/
demo/nginx/
  config.json
  nginx_metrics.jsonl
  prometheus.yml
  compose.yml
docs/
```

The folders describe responsibility boundaries, not a mandate for one class per file. Small modules
may be combined when that makes the implementation clearer.

Push metrics can use frame source timing; pull metrics remain demand-driven because a scrape is the
required advance trigger. Trace replay reads OTLP JSON export requests, applies one current-time
delta per cycle, preserves source pacing, and sends each record through OTLP/HTTP JSON.

## 7. Process lifecycle

1. Parse CLI arguments.
2. Load the versioned configuration file.
3. Resolve relative paths against the configuration file's directory.
4. Apply environment and CLI overrides.
5. Validate the complete configuration against its versioned JSON Schema and semantic rules before
   opening outputs or ports.
6. Load and validate source files.
7. Start health/readiness handling.
8. Start enabled replay tasks:
   - log scheduler,
   - pull exposition server,
   - push scheduler,
   - trace replay scheduler.
9. Mark readiness only after all enabled sources and required listeners are ready.
10. On `SIGINT` or `SIGTERM`, stop accepting work, allow bounded in-flight completion, close
    outputs, stop the HTTP server, and return a meaningful exit status.

Partial startup must unwind already-created resources. A configuration error must fail before any
events or metric frames are emitted.

The same validation pipeline is exposed by `signal-generator validate`. Startup and CLI validation
must not maintain separate rule sets: both call the packaged schema validator and semantic
validation service described in [configuration_design.md](configuration_design.md).

## 8. Log replay design

### 8.1 Compatibility model

The primary configuration is the versioned JSON format described in
[configuration_design.md](configuration_design.md). A legacy `.properties` adapter maps the
original uppercase keys into the new model.

Initial compatibility mappings include:

| Original key | New model |
|---|---|
| `SOURCE` | `logs.source.path` |
| `SOURCEFORMAT` | `logs.source.format` |
| `SOURCEDTG` | `logs.source.datetime_format` |
| `TARGETFORMAT` | `logs.format` |
| `TARGETDTG` | `logs.datetime_format` |
| `OUTPUTTYPE` | `logs.outputs[].type` |
| `TARGETFILE` | file output path |
| `TARGETIP`, `TARGETPORT` | TCP output host and port |
| `TARGETURL` | HTTP output URL |
| `REPEAT` | `logs.replay.cycles` |
| `ACCELERATEBY` | `logs.replay.acceleration` |
| `DEFAULTTIMEOFFSET` | `logs.replay.default_interval_ms` |
| `FIRSTOFMULTILINEREGEX` | `logs.source.multiline.first_line_pattern` |
| `ALLOWNL` | `logs.source.unescape_newlines` |
| `CUSTOMOUTPUT` | named Python output plugin |

Unknown legacy keys should produce a warning by default and an error in strict validation mode.

### 8.2 Timing

- A source-relative `+N` time value means an `N` millisecond delay from the previous event.
- Absolute source timestamps derive the delay between adjacent records.
- `default_interval_ms` applies when the source has no timing value.
- `acceleration` divides the derived delay and must be greater than zero.
- A monotonic clock drives waits; wall-clock changes must not alter replay spacing.
- An injectable clock and sleeper make timing unit tests deterministic.
- Cancellation interrupts waits cleanly.

### 8.3 Outputs

Every output implements a small lifecycle protocol:

```text
open() -> None
write(event: RenderedLogEvent) -> None
flush() -> None
close() -> None
```

Async implementations may expose equivalent awaitable methods behind the same application-facing
adapter. Output failures follow an explicit policy: `fail`, `retry`, or `continue`. The default is
`fail` to avoid silently losing test data.

Custom log outputs are discovered through Python package entry points under
`signal_generator.log_outputs`. Configuration selects a plugin by name; it must not import or
execute arbitrary file paths from untrusted configuration.

### 8.4 Reference scenario catalog

Checked-in reference scenarios combine a source fixture, configuration, expected rendered events,
and short usage document. The initial catalog covers:

- NGINX/Apache common and combined access logs,
- RFC 3164 and RFC 5424 syslog,
- one-event-per-line JSON logs,
- Java util logging-style text,
- Python logging-style text,
- multiline Java/Python stack traces,
- generic delimited application logs,
- time-shifted and accelerated variants of the timestamped formats.

Every scenario is executable in standalone and container tests. Formats are data-driven examples,
not hard-coded parser modes unless a format requires semantics the token parser cannot express.
Documentation identifies expected fidelity and any deliberate difference from the original Groovy
tool.

## 9. Metrics replay design

### 9.1 Frame loading

- The JSONL file is opened during startup and validated line by line.
- Blank lines are ignored; comments are not allowed because the file is JSON Lines.
- Validation errors include the path, one-based line number, and field location.
- Frames are indexed once so independent cursors can replay the same data.
- The first implementation keeps validated frames in memory. Indexed storage is tracked as
  [SG-007](roadmap.md) without changing the cursor contract.
- At least one frame is required when pull or push is enabled.

### 9.2 Stable metric descriptors

Across all frames, a metric name must retain the same:

- metric type,
- help text,
- label-name set,
- histogram bucket boundaries where applicable.

Label values and sample values may change. Descriptor drift is a startup error, not a scrape-time
surprise.

### 9.3 Pull sequence semantics

Only a successful request to the configured metrics path consumes a pull frame.

```text
request 1 -> frame 1
request 2 -> frame 2
request 3 -> frame 3
request 4 -> frame 1 when EOF policy is loop
```

The server acquires the next frame under a short lock, releases the lock, and renders an immutable
snapshot. Concurrent scrapes therefore receive distinct frames in a defined sequence. If a client
disconnects after the snapshot is assigned, that frame remains consumed; attempting to infer
whether a remote scraper received every byte would make behavior nondeterministic.

Requests to `/`, `/healthz`, and `/readyz` never advance the cursor. Unsupported methods and paths
never advance it. A rendering failure increments an internal error metric and returns HTTP 500.

### 9.4 Pull and push independence

Pull and push use separate cursors by default. This prevents a scheduled push from causing a
Prometheus scrape to skip a frame, and prevents extra diagnostic scrapes from changing the pushed
sequence.

An optional shared-cursor mode is tracked as [SG-006](roadmap.md); it is excluded from the first
release because its race behavior is difficult to reason about and test.

### 9.5 End-of-file policy

Each cursor has one of these policies:

| Policy | Behavior |
|---|---|
| `loop` | Continue from frame 1. Default for demonstrations. |
| `hold_last` | Continue returning or pushing the final frame. |
| `stop` | Pull returns 410 after the last frame; push task exits successfully. |
| `error` | Treat the next read after the final frame as a runtime failure. |

Cursor cycle and frame indexes are exposed as SignalGenerator self-metrics.

### 9.6 Prometheus rendering

Use a custom collector and isolated `CollectorRegistry` from `prometheus_client`. Do not mutate the
process-global registry and do not model snapshot counters by repeatedly calling `Counter.inc()`.
A custom collector can render the exact counter, gauge, histogram, summary, info, or untyped values
represented by the current frame.

Source timestamps are metadata by default. Prometheus should timestamp samples at scrape/ingest
time. Explicit sample timestamps are [SG-015](roadmap.md) and require a proven use case that
justifies the stale-sample and out-of-order risks.

Prometheus text exposition is implemented. Explicit OpenMetrics negotiation is
[SG-002](roadmap.md).

### 9.7 Push semantics

Prometheus normally scrapes targets. The first push implementation therefore targets a
Pushgateway-compatible endpoint, which is the conventional bridge for short-lived or batch jobs.
The configuration names this protocol explicitly as `pushgateway`; it does not imply that an
ordinary Prometheus server accepts text exposition pushes.

The push scheduler:

1. Selects the current push frame.
2. Renders it into an isolated registry.
3. Sends it using the configured job and grouping key.
4. Advances only after a successful response.
5. Retries the same frame after a bounded exponential backoff on transient failure.
6. Applies the configured interval between successful pushes.

Direct Prometheus remote write is tracked as [SG-004](roadmap.md) because it requires a different
wire protocol, authentication model, timestamp policy, and dependency set. The push interface makes
that adapter possible without changing frame loading or scheduling.

### 9.8 Self-observability

Self-metrics use a reserved `signal_generator_` prefix and include:

- `signal_generator_info`
- `signal_generator_ready`
- `signal_generator_metric_frames_total`
- `signal_generator_metric_frame_index`
- `signal_generator_metric_cycles_total`
- `signal_generator_metric_scrapes_total`
- `signal_generator_metric_pushes_total`
- `signal_generator_metric_push_failures_total`
- `signal_generator_log_events_emitted_total`
- `signal_generator_log_output_failures_total`

Self-metrics do not come from the frame file and do not change descriptor validation.

### 9.9 Planned synthetic metric replay-file generation

[SG-008](roadmap.md) adds an authoring step that produces the existing metric-frame JSON Lines
format from a validated configuration. It does not calculate values inside the pull collector or
push scheduler. Generation completes first, the resulting file can be reviewed or refined to
stimulate a specific behavior, and normal validation and replay then consume that immutable file.
This preserves deterministic cursors, makes generated incidents reproducible, and lets the same
artifact be used by pull, Pushgateway, and OTLP metric delivery.

The planned flow is:

1. Validate the generation configuration without opening replay transports.
2. Construct a synthetic timeline from `start_at`, `interval_ms`, and either `frames` or `duration`.
3. Evaluate every metric definition at each synthetic date and time using a required seed.
4. Write a candidate JSONL file atomically, never partially replacing an existing output.
5. Validate the candidate through the normal metric-frame loader before making it available.
6. Allow a user or test to refine the generated frames before selecting them as `metrics.source`.

Each metric definition supplies its stable name, type, help text, optional unit and labels, plus one
value domain:

- `range` declares inclusive `minimum` and `maximum` numeric values; or
- `enumerated` declares the complete set of permitted values.

A `steady_state.value` establishes the normal value and must belong to that domain. Numeric steady
state metrics may declare a fluctuation tolerance as either `percentage` or a
**mathjson-solver** expression. A percentage defines a seeded deviation band around the steady
state. A MathJSON expression evaluates a signed deviation for the current frame; the candidate is
then constrained to the configured domain. For an enumerated domain, a MathJSON expression must
evaluate to one of the declared members; percentage fluctuation is invalid. Counter generation
must remain non-negative and monotonic unless an explicit reset frame is configured. Histogram and
summary authoring must generate structures that already satisfy the existing cumulative-bucket,
count, sum, and quantile contracts.

Expressions receive read-only synthetic-time variables derived from the frame timestamp:
`timestamp_unix_seconds`, `year`, `month`, `day`, `hour`, `minute`, `second`, `day_of_week`,
`day_of_year`, and `frame_index`. They do not read the machine clock during evaluation. The
expression evaluator must use the bounded **mathjson-solver** operation set rather than Python
`eval`; file access, network access, arbitrary functions, unbounded recursion, and non-finite
results are rejected. The same configuration, seed, generator version, and timezone must produce
byte-identical output.

The draft authoring shape below is illustrative. It is owned by SG-008 and is not accepted by the
current runtime schema until that roadmap item is implemented:

```json
{
  "schema_version": 1,
  "synthetic_metrics": {
    "seed": 419,
    "timeline": {
      "start_at": "2026-11-16T00:00:00Z",
      "interval_ms": 60000,
      "frames": 1440,
      "timezone": "Europe/London"
    },
    "output": {"path": "generated/checkout_day.ndjson", "overwrite": false},
    "metrics": [
      {
        "name": "checkout_latency_seconds",
        "type": "gauge",
        "help": "Synthetic checkout latency.",
        "unit": "s",
        "labels": {"service": "checkout"},
        "values": {"range": {"minimum": 0.05, "maximum": 4.0}},
        "steady_state": {
          "value": 0.25,
          "fluctuation": {"percentage": 8}
        }
      },
      {
        "name": "checkout_queue_depth",
        "type": "gauge",
        "help": "Synthetic checkout queue depth.",
        "values": {"range": {"minimum": 0, "maximum": 500}},
        "steady_state": {
          "value": 12,
          "fluctuation": {
            "mathjson": ["If", ["Greater", "hour", 17], 80, 5]
          }
        }
      },
      {
        "name": "checkout_state",
        "type": "gauge",
        "help": "Synthetic checkout state code.",
        "values": {"enumerated": [0, 1, 2]},
        "steady_state": {
          "value": 0,
          "fluctuation": {
            "mathjson": ["If", ["Equal", "day_of_week", 6], 1, 0]
          }
        }
      }
    ]
  }
}
```

The implemented schema must use `oneOf` for range versus enumerated domains and percentage versus
MathJSON fluctuation. Typed models, semantic validation, effective configuration, CLI diagnostics,
fixtures, documentation, and deterministic golden-file tests must be delivered together.

### 9.10 Planned template-based trace replay-file generation

SG-008 applies the same generate-review-refine-validate-replay pattern to traces, but trace
generation starts from a template rather than synthesizing every field. A template is an ordered
series of newline-delimited OTLP JSON `ExportTraceServiceRequest` entries, such as
`examples/traces/traces.ndjson`. A separate JSON generation configuration selects that template,
defines the synthetic timeline and output file, and describes steady-state and anomalous
alterations. Generation produces another ordinary trace NDJSON file; the trace replay runtime does
not evaluate generation rules while it is sending data.

For every generated occurrence, the generator must:

1. Deep-copy the complete ordered template series without modifying the source file.
2. Offset all template timestamps to the occurrence's synthetic date and time while preserving
   span durations, event offsets, entry order, and relationships.
3. Deterministically replace trace and span IDs for that occurrence, consistently updating parent
   and link references so repeated template occurrences remain distinct.
4. Apply configured steady-state mutations, seeded fluctuations, and active anomaly mutations.
5. Validate the resulting OTLP JSON entries before atomically publishing the output NDJSON file.

#### 9.10.1 Template identity slots

Every generated occurrence (one complete cycle of the template series) starts with a fresh set of
non-zero, lowercase hexadecimal OTLP trace and span IDs. IDs are stable only within that occurrence;
the next occurrence creates new values for every identity slot. This prevents separate generated
cycles from being combined into one trace by a collector.

An ID without a suffix selects the default slot for its ID kind. When a template needs multiple
distinct trace IDs or span IDs, append a positive slot suffix such as `+1`, `+2`, or `+3` to the
template value. Slot namespaces are separate for trace IDs and span IDs:

- every `traceId` carrying `+1` receives the same generated 32-character trace ID within one
  occurrence;
- every `spanId`, `parentSpanId`, or linked span ID carrying `+1` receives the same generated
  16-character span ID within that occurrence;
- `+1` and `+2` always produce different IDs of the same kind; and
- the same suffix produces new IDs when the next template occurrence starts.

The suffix, rather than the hexadecimal stem before it, identifies the slot. Suffixes must be
positive base-10 integers without leading zeroes; `+0`, `+01`, a bare `+`, negative values, and
multiple suffixes are invalid. The suffix is template notation only and is removed from generated
OTLP output. The generator validates the emitted widths and maintains the same slot mapping across
all template entries, parent references, and links in the occurrence.

For example, this template fragment describes one trace with a root and child span:

```json
[
  {
    "traceId": "11111111111111111111111111111111",
    "spanId": "2222222222222222+1",
    "name": "root"
  },
  {
    "traceId": "11111111111111111111111111111111",
    "spanId": "2222222222222222+2",
    "parentSpanId": "2222222222222222+1",
    "name": "child"
  }
]
```

Within the first occurrence, both unsuffixed `traceId` values map to one new trace ID, the root
`spanId` and child `parentSpanId` map to the same new `+1` span ID, and the child receives a
different `+2` span ID. The second occurrence repeats those relationships using an entirely new
trace ID, `+1` span ID, and `+2` span ID. To model two traces in one occurrence, their template
`traceId` values use `+1` and `+2` respectively. If the generated file is subsequently replayed in
multiple runtime cycles, the existing trace replay identity remapping creates another fresh set for
each runtime cycle while preserving these within-cycle relationships.

Mutation targets use a bounded JSONPath subset rooted at one original template entry. The supported
subset must include object-member selection and numeric array indexes, for example
`$.resourceSpans[0].scopeSpans[0].spans[0].status`. Wildcards, filters, scripts, recursive descent,
and mutation-created paths are excluded from the first implementation. Every numeric index is
resolved relative to the immutable template entry, not relative to an array produced by an earlier
mutation. This means configuration continues to address the same template element even when a
replacement JSON child contains arrays or objects. A missing or ambiguous target is a generation
error. Mutations are evaluated in configuration order, but their target locations are resolved
against the template before any mutation is applied; two mutations may not target the same path or
an ancestor/descendant pair.

Each mutation uses exactly one replacement form:

- `set.value` supplies a JSON scalar (`string`, `number`, `boolean`, or `null`); or
- `set.json` supplies a complete JSON object or array child structure.

The replacement is copied into the generated payload, so later occurrences cannot share mutable
state. Semantic validation must reject replacements that violate OTLP field types, identifier
widths, timestamp ordering, or required trace structure. Mutation of generated trace/span IDs is
not allowed; identity replacement remains generator-owned. A JSONPath may target an OTLP timestamp,
but the replacement must be an integer nanosecond value and the generator must revalidate span
start/end ordering and event timestamp validity after all mutations. Percentage fluctuation is
invalid for absolute timestamps; duration variation is expressed by calculating an end timestamp
from the read-only span start value, as in the example below.

Trace anomalies share the metric generator's seed, synthetic timeline, timezone, and expression
context. Numeric trace fields can use percentage fluctuation around a steady-state value, while
anomaly activation and replacement values can use bounded **mathjson-solver** expressions. The
trace expression context adds `template_index`, `occurrence_index`, and the read-only
`template_value` to the metric variables so a rule can distinguish entries within the template
series without depending on generated array positions. When a target belongs to a span, the context
also provides `span_start_unix_nano` and `span_end_unix_nano`. Integer solver results assigned to
OTLP decimal-string fields are serialized back to canonical decimal strings after range checks.

The trace generation configuration has an explicit `enable_mathjson_solver` flag. When it is
`true`, every string in a mutation rule whose first characters are the exact, case-sensitive prefix
`mathjson-solver:` is treated as an expression. The suffix is JSON-escaped MathJSON text in the
containing configuration string; it is decoded once and then evaluated by the same bounded solver
used for metric generation. This recursive interpretation includes `when`, `set.value`, and strings
inside `set.json` children. Other strings remain literal. When the flag is `false`, all strings
remain literal and no solver is loaded. Invalid escaped JSON, an empty suffix, an unsupported
operation, a non-finite result, or a result incompatible with the target field is a validation
error rather than a literal fallback.

This illustrative configuration is planned syntax and is not accepted by the current runtime
schema:

```json
{
  "schema_version": 1,
  "synthetic_traces": {
    "seed": 419,
    "template": {"path": "examples/traces/traces.ndjson"},
    "timeline": {
      "start_at": "2026-11-16T00:00:00Z",
      "interval_ms": 60000,
      "occurrences": 1440,
      "timezone": "Europe/London"
    },
    "enable_mathjson_solver": true,
    "output": {"path": "generated/checkout_traces.ndjson", "overwrite": false},
    "mutations": [
      {
        "template_index": 0,
        "path": "$.resourceSpans[0].scopeSpans[0].spans[0].attributes",
        "steady_state": {
          "set": {
            "json": [
              {"key": "deployment.environment", "value": {"stringValue": "test"}}
            ]
          }
        }
      },
      {
        "template_index": 0,
        "path": "$.resourceSpans[0].scopeSpans[0].spans[0].endTimeUnixNano",
        "steady_state": {
          "set": {
            "value": "mathjson-solver:[\"Add\",\"span_start_unix_nano\",50000000]"
          }
        },
        "anomalies": [
          {
            "when": "mathjson-solver:[\"And\",[\"GreaterEqual\",\"hour\",17],[\"Less\",\"hour\",19]]",
            "set": {
              "value": "mathjson-solver:[\"Add\",\"span_start_unix_nano\",500000000,[\"Multiply\",\"minute\",1000000]]"
            }
          }
        ]
      },
      {
        "template_index": 0,
        "path": "$.resourceSpans[0].scopeSpans[0].spans[0].status",
        "anomalies": [
          {
            "when": "mathjson-solver:[\"Equal\",\"day_of_week\",6]",
            "set": {"json": {"code": 2, "message": "synthetic weekend failure"}}
          }
        ]
      }
    ]
  }
}
```

## 10. HTTP and health contract

Defaults:

| Method and path | Purpose | Consumes a frame |
|---|---|---|
| `GET /metrics` | Current pull frame plus self-metrics | Yes |
| `GET /healthz` | Process liveness | No |
| `GET /readyz` | Sources loaded and enabled services ready | No |
| `GET /` | Small service identity document | No |

The metrics path is configurable. Health paths remain stable so containers and the OpAMP simulator
adapter can rely on them. Health responses are small JSON objects and must not disclose secrets or
complete configuration.

The exposition server can be implemented with a small WSGI router around `prometheus_client` and a
background HTTP server. Log replay and push scheduling can use `asyncio`; blocking library calls
run through bounded worker threads. This avoids adopting a full web framework solely for four
endpoints.

## 11. Configuration precedence

Highest to lowest:

1. Explicit CLI overrides.
2. Environment variables.
3. Versioned configuration file.
4. Legacy properties mapping.
5. Code defaults.

Secrets such as HTTP authorization tokens are accepted through environment variables or referenced
secret files, not printed in effective-config output, and not included in examples.

## 12. Security and reliability

- Bind the metrics server to loopback by default; container examples explicitly bind all interfaces.
- Reject paths outside configured mount roots only when an optional restricted mode is enabled;
  otherwise resolve and log absolute paths.
- Enforce source file and line-size limits to avoid accidental memory exhaustion.
- Bound HTTP timeouts, retry counts, and backoff.
- Do not follow arbitrary redirects for pushes unless configured.
- Validate metric and label names before startup.
- Never import plugins by arbitrary filesystem path; use installed entry points.
- Run as a non-root user in the container.
- Handle signals and child supervision without shell command construction.
- Redact authorization headers and secret configuration values from logs.

## 13. Performance expectations

The primary target is deterministic functional testing, not maximum-throughput load generation.
Initial design targets are:

- 10,000 metric samples per frame without corrupting output.
- 100 concurrent scrape requests with ordered, lock-safe frame assignment.
- Log scheduling drift below one configured interval for normal local workloads.
- Bounded memory documented as approximately source-frame size plus parsed representation.

Benchmarks inform [SG-007](roadmap.md) and other optimization work. Correct sequencing and clear
failure behavior take priority over speculative micro-optimizations.

## 14. Deployment modes

### 14.1 Standalone process

The `signal-generator run` command owns the replay runtime and its HTTP listener. This mode is used
by the standalone container and by the `signal-generator-opamp-sim` supervised plugin when
child-process supervision is required. It exposes the configured root routes (`/metrics`,
`/healthz`, and `/readyz`) and handles operating-system signals directly.

### 14.2 Unified simulator Quart component

The `quart` optional dependency exposes a lower-level attachment API:

```text
signal_generator.embedding.quart:attach_signal_generator_runtime
```

The independent adapter's unified host calls it with its Quart application, runtime ID, validated
configuration, and route prefix. The attachment:

1. Creates one `SignalGeneratorRuntime` and stores it in an app-scoped runtime registry.
2. Registers a uniquely named Blueprint under the runtime's configured prefix.
3. Starts replay tasks through `app.before_serving`.
4. Stops and awaits replay tasks through `app.after_serving`.
5. Reuses the simulator event loop, logging, listener, and signal handling.

Default embedded routes are:

| Route | Purpose |
|---|---|
| `/signal-generator/<runtime-id>/metrics` | Demand-driven replay metrics. |
| `/signal-generator/<runtime-id>/healthz` | Component liveness. |
| `/signal-generator/<runtime-id>/readyz` | Component readiness. |

The prefix is mandatory and unique in embedded mode so multiple simulated clients can own
independent runtimes without route collisions.

Embedded mode must not:

- start another HTTP server,
- install process signal handlers,
- call `asyncio.run`,
- stop the host application when a replay source completes,
- use the process-global Prometheus registry,
- replace host logging or observability configuration.

A runtime failure marks only its associated simulator/runtime ownership scope unready and cancels
those tasks. Whether the unified simulator should terminate is an explicit `failure_policy`
setting; the default is `isolate` for embedded mode and `fail_process` for standalone mode.

### 14.3 Container choices

Two supported container shapes follow from these modes:

- A dedicated SignalGenerator image running the console command.
- A unified adapter image containing the `signal-generator-opamp-sim`, SignalGenerator, and
  `opamp-consumer` wheels, with runtimes attached by the adapter app factory.

The second option is one operating-system process. It is not a sidecar and does not use the
child-process consumer lifecycle.

## 15. Multi-signal timing and replay

Timestamped scheduled sources normalize records into a `SignalEnvelope` containing signal type,
source timestamp, source sequence, and immutable payload. A merge scheduler orders envelopes by:

1. normalized source timestamp,
2. configured source priority,
3. stable source sequence.

Time shifting calculates one scenario offset from the earliest source timestamp to an explicitly
configured replay start and applies that same offset to all timestamped signals. This preserves
relative ordering across files and signal types. Omitting the start on a legacy single-source log
configuration retains its original timestamps and adjacent-delay behavior. Acceleration scales
elapsed intervals after the offset is applied.

Looping creates a new cycle epoch. The next cycle begins after the previous cycle's final scheduled
timestamp plus the configured loop gap. It must not move timestamps backwards. Demand-driven metric
scrapes remain outside the merge scheduler. Cross-source merge behavior, including scheduled metric
pushes with `observed_at`, is tracked as [SG-001](roadmap.md).

SignalGenerator self-metrics are always available as operational metrics. Configuration may include
them in the test exposition registry, but recursive measurements such as scrape counters are
snapshotted once per response so rendering cannot recurse indefinitely.

## 16. Design decisions

| Decision | Rationale |
|---|---|
| Versioned JSON is the canonical config | Standard-library parsing, schema clarity, and easy OpAMP remote config. |
| Legacy properties are an adapter | Preserves migration without constraining the internal model. |
| One JSONL line is one complete metric frame | Matches the requested replay unit and makes sequencing deterministic. |
| Pull and push have independent cursors | Prevents cross-channel frame theft and timing races. |
| Health never uses `/metrics` | OpAMP/container polling must not alter replay. |
| Pushgateway is the initial push protocol | It is the conventional Prometheus push bridge and accepts exposition data. |
| Custom collector instead of mutable counters | Snapshot replay must expose exact source values, including resets. |
| OpAMP composition lives in an independent adapter distribution | Keeps SignalGenerator-specific code out of both core dependencies while allowing the adapter to depend on their published APIs. |
| Core runtime is host-independent | The same replay logic supports a console process and embedded Quart component. |
| Embedded routes require a runtime prefix | Allows multiple in-process simulator runtimes without collisions. |
| Complexity is a release gate | Keeps replay, validation, and lifecycle paths reviewable and testable. |
| Root `pyproject.toml` is canonical | Prevents dependency, build, and tool configuration drift. |

