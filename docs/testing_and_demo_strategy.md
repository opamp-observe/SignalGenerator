# Testing and demo strategy

## 1. Quality objectives

Testing must prove deterministic sequence behavior, configuration safety, output compatibility,
clean lifecycle management, and container interoperability. Coverage percentage is a signal, not a
substitute for scenario coverage.

Required local quality commands:

```text
python -m ruff check src tests
python -m pylint src/signal_generator
python -m pytest -q -s
```

The project should keep branch coverage enabled and fail CI when coverage drops below an agreed
threshold. The initial target is 90% overall branch coverage and 100% branch coverage for cursor,
frame validation, and configuration precedence modules.

## 2. Complexity and maintainability gates

Cyclomatic complexity is enforced, not merely reported. The initial source-code policy is:

- No function or method may exceed McCabe complexity 10 (Radon rank B).
- Package-average complexity must remain rank A.
- Every module must remain rank A on average.
- New rank-B functions require focused branch tests and a review note explaining why splitting the
  function would reduce clarity.
- Rank C or worse is a release blocker; suppression is not an accepted baseline strategy.
- Generated code is excluded. Test helpers may reach complexity 15, but product decision logic must
  not be hidden in tests or fixtures.

Required tools and commands:

```text
python -m ruff check src tests
python -m radon cc src/signal_generator -s -a
python -m xenon --max-absolute B --max-modules A --max-average A src/signal_generator
```

Ruff enables `C90` and sets `lint.mccabe.max-complexity = 10` as the fast developer check. Radon
provides reviewable per-function scores, and Xenon supplies the CI pass/fail gate. Pylint's branch,
statement, argument, and local-variable warnings remain enabled as complementary design signals.

CI stores the Radon report as an artifact and compares aggregate complexity with the main branch.
A change must not increase the count of rank-B functions without an explicit review decision. The
same gate runs before wheel creation and release tagging.

Maintainability index and raw metrics may be reported by Radon for trends, but cyclomatic
complexity, tests, type/static analysis, and review remain separate gates; one score cannot offset
failure of another.

## 3. Test layout

```text
tests/
  unit/
    config/
    logs/
    metrics/
    health/
    embedding/
  contract/
    test_config_examples.py
    test_metric_frame_examples.py
    test_plugin_contract.py
    test_distribution_contents.py
  integration/
    test_pull_server.py
    test_pushgateway_adapter.py
    test_log_outputs.py
    test_application_lifecycle.py
    test_quart_embedding.py
  e2e/
    test_container_pull_replay.py
    test_container_push_replay.py
    test_container_quart_embedding.py
    test_nginx_demo.py
```

Tests should use temporary directories, ephemeral ports, injected clocks, and local stub servers.
Unit and integration suites must not require internet access.

## 4. Unit test matrix

### 4.1 Configuration

- Valid minimal log-only, pull-only, push-only, and combined configurations.
- Missing or unsupported `schema_version`.
- Relative path resolution from the configuration directory.
- CLI, environment, file, legacy, and default precedence.
- Unknown keys and misspellings.
- Secret redaction in effective config and logs.
- Legacy property mapping for every supported original key.
- Java-to-Python datetime format translation and unsupported pattern diagnostics.
- Every numeric boundary: zero, negative, maximum, and non-numeric values.
- JSON syntax diagnostics include source, line, and column.
- Schema violations have stable codes, JSON Pointers, useful messages, and hints where applicable.
- Unknown-property suggestions, deterministic error ordering, error caps, and secret redaction.
- Structural schema and typed Python model acceptance/rejection parity.

### 4.2 Log parsing and replay

- Every source/output token.
- Default fields and missing optional input fields.
- Relative and absolute source timing.
- Acceleration and zero-delay events.
- Multiline first-record matching.
- Literal newline preservation and optional unescaping.
- Repeat counts and cycle/record counters.
- Cancellation during a wait.
- Monotonic timing with an injected fake clock.
- Output open/write/flush/close ordering.
- Retry, continue, and fail policies.
- Partial output startup cleanup.

### 4.3 Metric-frame validation

- Valid counter, gauge, histogram, summary, info, and untyped families.
- Invalid metric and label names.
- Reserved prefix rejection.
- Duplicate metric names and duplicate label sets.
- Descriptor drift across frames.
- Counter reset acceptance and negative counter rejection.
- Histogram boundary order, cumulative counts, and `+Inf` consistency.
- Summary quantile range and uniqueness.
- Special numeric values.
- Blank lines, malformed JSON, line-size limit, and sample-count limit.
- Precise file, line, and field error locations.

### 4.4 Cursor semantics

- First request returns first frame.
- `loop`, `hold_last`, `stop`, and `error` policies.
- Correct frame and cycle self-metrics.
- Pull and push cursor independence.
- Concurrent callers each receive one distinct ordered assignment.
- Rendering failure behavior.
- Failed push does not advance.
- Successful retry advances exactly once.

Concurrency tests must use barriers rather than arbitrary sleeps.

### 4.5 HTTP and health

- Content negotiation for Prometheus and OpenMetrics.
- `GET /metrics` advances once.
- `HEAD`, invalid method, and unknown path do not advance.
- `/healthz`, `/readyz`, and `/` do not advance.
- Readiness before and after source load, listener start, and shutdown.
- Bind failure unwinds startup.
- No secrets appear in responses.
- Embedded routes use unique runtime prefixes and do not collide with each other.
- Quart health/readiness requests do not advance a replay cursor.
- `before_serving` starts exactly one runtime and `after_serving` awaits its shutdown.
- Embedded mode does not install signals, start a listener, or call `asyncio.run`.

## 5. Contract tests

Contract tests protect boundaries that another repository or external service will consume.

### 5.1 CLI contract

- Stable command names and exit codes.
- `--version` output.
- `validate` has no output side effects.
- `validate --format text` writes actionable diagnostics to stderr and a success summary to stdout.
- `validate --format json` emits only a document conforming to `validation_result.schema.json`.
- `validate --schema-only` performs no path resolution or source reads.
- Schema, semantic, and source errors return `3`; malformed CLI use returns `2`.
- `print-effective-config` is deterministic and redacted.
- Graceful signal exit.

### 5.2 Prometheus contract

- Parse generated output with the Prometheus client parser.
- Assert HELP and TYPE lines and sample suffixes.
- Test escaping of help, labels, backslashes, and newlines.
- Verify histogram and summary wire shapes.
- Verify the Pushgateway request path, job, grouping labels, method, and content type.

### 5.3 OpAMP adapter contract

SignalGenerator tests should publish a small reusable contract fixture that proves:

- `signal-generator run --config <path>` launches the process.
- `/healthz` becomes healthy without consuming a frame.
- `/readyz` reports source readiness.
- `signal-generator validate --config <path>` validates remote config candidates.
- `SIGTERM` stops within the configured timeout.
- `--version` is machine-readable enough for the adapter to report.

The separate adapter distribution owns SignalGenerator-specific plugin, message, lifecycle, and
unified-host tests. `opamp-core` owns only its generic embeddable simulator-client API contract
tests.

Adapter CLI contracts additionally prove that `signal-generator-opamp-sim validate`:

- emits human-readable and schema-conforming JSON diagnostics,
- supports schema-only and full referenced-configuration validation,
- returns the shared stable validation exit codes, and
- does not bind Quart, spawn SignalGenerator, or connect an OpAMP client.

### 5.4 Wheel and simulator Quart attachment contract

- Build both wheel and source distribution from a clean tree.
- Run `twine check` against every distribution.
- Inspect the wheel for package code, schemas, `py.typed`, metadata, and licence.
- Install the base wheel into a clean environment and run CLI smoke tests.
- Install the `quart` extra into a clean environment and attach a runtime to a consumer-simulator
  Quart test application.
- Prove that installing the base wheel does not install Quart.
- Prove that embedded registration fails clearly when the extra is absent.
- Build the adapter wheel independently and install it from a local wheelhouse containing all
  dependency wheels.
- Prove the base adapter install does not install Quart, imports no sibling source checkout, and
  supports installed supervised-plugin discovery.
- Install `signal-generator-opamp-sim[unified]` into a second clean environment and run the unified
  Quart-host contract tests.

## 6. Integration tests

- Use a local TCP listener and assert byte-exact log delivery.
- Use a local HTTP stub and assert methods, headers, payloads, retries, and redaction.
- Use a temporary WSGI server and real HTTP client for pull sequencing.
- Use a Pushgateway-shaped stub for fast failure tests.
- Run selected tests against the real Pushgateway container for interoperability.
- Start the complete application with both log and metric tasks, then exercise graceful shutdown.
- Attach multiple runtimes to one consumer-simulator Quart app and prove each route set works.
- Run two Quart app instances in one test process and prove runtime state is app-scoped rather than
  global.

No integration test should depend on execution order or a fixed host port.

## 7. Container design

The implementation should provide a multi-stage `Dockerfile`:

- Builder installs the wheel and locked runtime dependencies.
- Runtime uses a small supported Python base image.
- Process runs as a non-root user.
- Configuration and data live under `/config` and `/data` mount points.
- Port `9108` is documented and exposed for metrics/health.
- Healthcheck calls `/healthz`, not `/metrics`.
- Entrypoint uses exec form and forwards signals.
- Image contains no compiler, test dependencies, package caches, or source-control metadata.

The image entrypoint is equivalent to:

```text
signal-generator run --config /config/config.json
```

An embedded image test builds from the adapter wheel and its dependency wheels, then verifies one
process owns simulator and SignalGenerator routes. It must assert that no SignalGenerator child
process or second listener is created. The `opamp-core` images are unchanged.

## 8. NGINX metrics replay demo

The demo represents NGINX exporter-style metrics; it does not need a running NGINX server because
the purpose is to replay recorded snapshots.

Planned frames show a recognizable traffic progression:

| Frame | Active | Reading | Writing | Waiting | Requests total |
|---|---:|---:|---:|---:|---:|
| 1 | 4 | 1 | 1 | 2 | 1200 |
| 2 | 9 | 2 | 3 | 4 | 1280 |
| 3 | 15 | 3 | 7 | 5 | 1410 |
| 4 | 6 | 1 | 2 | 3 | 1495 |

Metric families include:

- `nginx_up`
- `nginx_connections_active`
- `nginx_connections_reading`
- `nginx_connections_writing`
- `nginx_connections_waiting`
- `nginx_connections_accepted_total`
- `nginx_connections_handled_total`
- `nginx_http_requests_total`

All frames retain identical help text and label names.

Planned `demo/nginx/compose.yml` services:

| Service | Purpose |
|---|---|
| `signal-generator` | Replays the NGINX JSONL frames and exposes port 9108. |
| `pushgateway` | Receives scheduled frames when the push profile is enabled. |
| `prometheus` | Scrapes SignalGenerator and Pushgateway. |
| `e2e-verifier` | Runs deterministic assertions and exits. |

Compose profiles should support:

```text
docker compose -f demo/nginx/compose.yml up --build
docker compose -f demo/nginx/compose.yml --profile push up --build
docker compose -f demo/nginx/compose.yml --profile test up --build --abort-on-container-exit
```

## 9. End-to-end assertions

### 9.1 Pull replay

1. Start the container with pull enabled and push disabled.
2. Wait for `/readyz` to return 200.
3. Call `/healthz` twice and prove the frame index remains unchanged.
4. Scrape `/metrics` four times.
5. Assert active connections are `4`, `9`, `15`, then `6`.
6. Scrape a fifth time and assert loop back to `4`.
7. Assert self-metric scrape and cycle counts.

### 9.2 Push replay

1. Start SignalGenerator and Pushgateway with a short interval.
2. Wait for four successful pushes.
3. Query the Pushgateway or Prometheus scrape result.
4. Assert the grouping key and latest frame values.
5. Temporarily make the endpoint fail.
6. Assert retry uses the same frame and the failure counter increments.
7. Restore the endpoint and assert the next successful push advances once.

### 9.3 Prometheus interoperability

1. Start Prometheus with a short scrape interval.
2. Query its HTTP API for each NGINX metric.
3. Assert labels and values are ingested.
4. Assert both direct pull and Pushgateway jobs can be distinguished.
5. Run `promtool check config` against the checked-in Prometheus configuration.

### 9.4 Unified simulator Quart deployment

1. Start `consumer-sim` in `unified_quart` mode.
2. Assert one process and listener host all configured simulated clients and replay runtimes.
3. Assert no SignalGenerator subprocess and no supervisor/observer lifecycle is created.
4. Confirm each simulated OpAMP client registers with its configured identity.
5. Confirm per-instance and shared metric routes advance only their intended cursors.
6. Apply a logical restart and verify no host-process restart occurs.
7. Stop Quart and assert all client, heartbeat, replay, and output tasks are awaited.

## 10. CI pipeline

Recommended gates:

1. Formatting, static analysis, and cyclomatic-complexity gates.
2. Unit and contract tests on supported Python versions.
3. Dependency and source security checks.
4. Wheel and source-distribution build, metadata check, content audit, and clean install.
5. Standalone and unified-simulator Quart integration tests.
6. Container build.
7. Pull, push, and embedded container end-to-end profiles.
8. Image vulnerability scan, software bill of materials, and artifact attestation.

The OpAMP integration is tested in the adapter pipeline. Its matrix installs released and candidate
SignalGenerator, `opamp-consumer`, and `opamp-consumer-sim` wheels. The `opamp-core` pipeline tests
only the generic simulator-client API and may trigger downstream adapter compatibility testing.

## 11. Test data rules

- Test data is small, human-reviewable, and deterministic.
- Dates and random values are fixed unless a seeded generator is the subject of the test.
- No credentials, production hostnames, or customer data.
- Invalid fixtures state the expected error in their name or adjacent test.
- Demo data is also schema-validated in CI.

