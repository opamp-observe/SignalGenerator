# Changelog

## 0.1.0 - Unreleased

### Added

- Versioned JSON configuration, Draft 2020-12 schemas, environment precedence, redaction, and
  human/machine validation output.
- CLI commands for validation, effective configuration, legacy conversion, and standalone replay.
- Original-style log token parsing, multiline grouping, deterministic replay scheduling, cycles,
  acceleration, and cooperative shutdown.
- Standard streams, file, TCP, HTTP, Python logging, and installed plugin outputs.
- Unit, contract, and local transport integration suites with coverage and complexity gates.
- PowerShell, CMD, and Bash startup wrappers.
- Typed metric-frame models, bounded JSONL loading, semantic descriptor validation, and all four
  EOF policies.
- Atomic independent pull and push cursors, isolated Prometheus registries, NGINX replay fixtures,
  and non-consuming root, health, and readiness routes.
- Scheduled Pushgateway replacement with bounded exponential retry, source/fixed timing,
  grouping keys, basic or bearer authentication, TLS controls, and push diagnostics.
- A non-root multi-stage image plus a real Pushgateway Compose interoperability test.
- A host-independent async replay lifecycle and optional multi-runtime Quart attachment with
  prefixed metrics, liveness, readiness, and deterministic shutdown.
- Pull, push, and unified Compose profiles using real Prometheus and Pushgateway images, NGINX
  replay data, query-API verification, and non-consuming health checks.
- An independently built `signal-generator-opamp-sim` distribution with its own TOML metadata,
  lock file, schema-backed validation CLI, installed OpAMP plugin entry point, wheel/source build,
  supervised lifecycle, and unified one-process Quart host.
- A generic public `opamp-consumer-sim` async simulator lifecycle in `opamp-core`; provider code and
  images remain unchanged and contain no SignalGenerator dependency.
- Release performance floors and a machine-readable benchmark covering JSONL loading, exposition
  throughput, and peak traced allocation.
- Failure-injection tests for occupied ports, missing/malformed sources, Pushgateway outages, and
  cooperative signal shutdown.
- Signed core and adapter tag workflows with PyPI trusted publishing, GHCR images, vulnerability
  scanning, package/image SBOMs, SHA-256 manifests, keyless signing, and build provenance.
- A compatibility matrix plus operational security, performance, and release documentation.
- A complete user guide, separate development setup, and a GitHub-dispatchable regression suite
  for labeled ephemeral AWS or Azure runners.
