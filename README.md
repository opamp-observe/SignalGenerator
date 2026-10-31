# SignalGenerator Python

SignalGenerator replays log events and Prometheus metric snapshots from deterministic source
files. The project is an enhanced Python successor to
[mp3monster/LogGenerator](https://github.com/mp3monster/LogGenerator).

The CLI supports configuration validation, effective-configuration output, legacy property
conversion, log replay, scrape-driven metric replay, and scheduled Pushgateway delivery. See
[the design index](docs/index.md), [metrics operations](docs/metrics_replay.md), and the
[startup script guide](scripts/README.md).

Start with the task-oriented [user guide](docs/user_guide.md). Contributors should use the separate
[development setup](docs/development_setup.md).

```text
signal-generator validate --config examples/logs/basic/config.json
signal-generator run --config examples/logs/basic/config.json
signal-generator validate --config examples/metrics/config.json
signal-generator run --config examples/metrics/config.json
```

The metric example exposes `/metrics`, `/healthz`, `/readyz`, and `/` on
`http://127.0.0.1:9108`. Each `/metrics` scrape consumes the next JSONL frame; lifecycle routes do
not move the cursor.

## Containers and OpAMP simulator integration

Phase 5 Compose profiles provide real Prometheus and Pushgateway interoperability plus the unified
single-process Quart deployment:

```text
docker compose -f tests/test-containers/phase5/compose.yaml --profile pull up --build -d
python tests/test-containers/phase5/verify.py pull

docker compose -f tests/test-containers/phase5/compose.yaml --profile push up --build -d
python tests/test-containers/phase5/verify.py push

docker compose -f tests/test-containers/phase5/compose.yaml --profile unified up --build -d
python tests/test-containers/phase5/verify.py unified
```

Run `docker compose ... down --remove-orphans` between profiles. Pull mode exposes SignalGenerator
on `19108` and Prometheus on `19090`; push mode exposes Pushgateway on `19091`; unified mode exposes
the shared Quart listener on `19110` and its Prometheus on `19092`.

The separately built adapter is documented in
[`integrations/opamp-simulator/README.md`](integrations/opamp-simulator/README.md). Unified mode
requires `APP_ENABLE_DEV_FEATURES=true` and runs simulated OpAMP clients and replay runtimes in one
worker, process, listener, and event loop without a SignalGenerator subprocess.

## Quality and release evidence

Run the complete core and adapter gate, performance benchmark, and release-manifest generator with:

```text
python scripts/security_checks.py
python scripts/benchmark_replay.py --output test-results/performance.json
python scripts/release_artifacts.py dist/phase5-6 dist/phase5-6-adapter --output dist/evidence
```

See [performance limits](docs/performance_limits.md), [security hardening](docs/security_hardening.md),
the [compatibility matrix](docs/compatibility_matrix.md), and the signed-tag
[release process](docs/release_process.md).
