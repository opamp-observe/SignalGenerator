# SignalGenerator user guide

## What the tool does

SignalGenerator replays two deterministic signal types:

- log records to stdout, stderr, files, TCP, HTTP, Python logging, or installed output plugins; and
- Prometheus metric snapshots from a JSON Lines file, advancing to the next snapshot on every
  `/metrics` scrape and independently on every successful scheduled push.

Use it for demonstrations, integration tests, dashboards, alert tests, and repeatable OpAMP client
simulations. Health and readiness requests never consume a metric frame.

## Install and start

Python 3.10–3.13 is supported. For a local source checkout:

```text
python -m venv .venv
```

Activate the environment and install the package:

```text
# PowerShell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

# Windows Command Prompt
.venv\Scripts\activate.bat
python -m pip install -e ".[dev]"

# Bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The checked-in launchers activate `.venv`, preserve all CLI arguments, and return the tool's exit
code:

```text
.\scripts\start_signal_generator.ps1 validate --config examples\metrics\config.json
scripts\start_signal_generator.cmd run --config examples\logs\basic\config.json
./scripts/start_signal_generator.sh run --config examples/metrics/config.json
```

For production, install the wheel from a release and use the `signal-generator` console command.

## Validate before running

Always validate a scenario before starting it:

```text
signal-generator validate --config examples/metrics/config.json
signal-generator validate --config examples/metrics/config.json --format json
signal-generator validate --config examples/metrics/config.json --schema-only
signal-generator print-effective-config --config examples/metrics/config.json
```

Text output is intended for people. JSON output follows the packaged validation-result schema and
is suitable for CI. `--schema-only` checks structure without reading referenced data files. The
effective configuration is deterministic and redacts secrets.

Exit codes are:

| Code | Meaning |
|---:|---|
| 0 | Success or valid configuration |
| 2 | Invalid CLI usage |
| 3 | Configuration, schema, or source validation failed |
| 4 | Runtime startup failed |
| 5 | Replay failed after startup |

## Replay logs

Run the basic log scenario:

```text
signal-generator run --config examples/logs/basic/config.json
```

The configuration selects the source format, replay timing, cycles, formatting, and outputs. Paths
are resolved relative to the configuration file. Use `runtime.log_level: DEBUG` when diagnosing a
scenario.

To migrate an original properties file:

```text
signal-generator convert-properties \
  --input examples/legacy/basic.properties \
  --output converted.json
signal-generator validate --config converted.json
```

`--strict` turns warnings into failures. `--force` is required to replace an existing output file.
See [log compatibility](log_compatibility.md) and the [migration guide](migration_guide.md).

## Expose pull metrics

Start the NGINX-style example:

```text
signal-generator run --config examples/metrics/config.json
```

The default listener is `http://127.0.0.1:9108`:

| Route | Purpose | Advances frame? |
|---|---|---|
| `/metrics` | Prometheus text exposition | Yes, once per successful GET |
| `/healthz` | Process liveness | No |
| `/readyz` | Source/listener readiness | No |
| `/` | Service discovery response | No |

Configure Prometheus with `metrics_path: /metrics` and the SignalGenerator host as a scrape target.
The source `eof` policy controls whether the cursor loops, holds the last frame, stops, or errors.

## Push metrics

Enable `metrics.push` with a Pushgateway URL, job name, grouping key, and `interval_seconds`.
SignalGenerator replaces the configured Pushgateway group. A successful push advances the push
cursor exactly once; a failed push retries the same frame. Pull and push cursors are independent.

Passwords and bearer tokens are read only from the environment variable named by configuration.
TLS verification is enabled by default. Detailed fields and examples are in
[metrics replay operations](metrics_replay.md).

## Run the container demonstrations

Use one profile at a time because the demo uses fixed host ports:

```text
python scripts/run_regression.py --profile pull
python scripts/run_regression.py --profile push
python scripts/run_regression.py --profile unified --opamp-core-context ../opamp2
```

`run_regression.py` builds the images, waits for readiness, verifies public Prometheus or
Pushgateway behavior, records `test-results/regression.json`, prints diagnostics on failure, and
always removes its scoped containers and volumes.

## Use the OpAMP adapter

The adapter is an independent package:

```text
python -m pip install ".\integrations\opamp-simulator[unified]"
signal-generator-opamp-sim validate --config examples/opamp/supervised-config.json
signal-generator-opamp-sim supervised --config examples/opamp/supervised-config.json
signal-generator-opamp-sim unified --config examples/opamp/unified-config.json
```

Supervised mode lets the OpAMP consumer manage a SignalGenerator child. Unified mode places the
simulated OpAMP clients and replay runtimes in one Quart process, listener, event loop, and worker;
it creates no SignalGenerator child process. Unified simulation requires
`APP_ENABLE_DEV_FEATURES=true`. It is not built into the OpAMP provider.

See the [adapter operations guide](../integrations/opamp-simulator/README.md) for remote
configuration, route prefixes, and package compatibility.

## Troubleshooting

- Run `validate` first and fix every JSON Pointer reported in the diagnostics.
- If `/readyz` returns 503, check source paths, JSONL limits, and port availability.
- If Prometheus shows no data, query `/healthz`, then inspect its targets page; do not use
  `/metrics` as a health probe because it consumes frames.
- If pushes do not advance, check Pushgateway reachability, authentication environment variables,
  TLS trust, and retry diagnostics.
- If unified mode duplicates data, enforce one Quart worker and one host process.
- Use `print-effective-config` to confirm path resolution and environment precedence without
  exposing secrets.
