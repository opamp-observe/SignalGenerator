# Implementation plan verification

## 1. Audit scope and result

This audit compares every phase deliverable, exit gate, and final definition-of-done statement in
[implementation_plan.md](implementation_plan.md) with the checked-in source, tests, workflows,
packages, containers, documentation, and generic changes in the companion
`opamp-observe/opamp-core` checkout.

Result: the requested log replay, Prometheus pull, Pushgateway push, Quart embedding, independent
OpAMP adapter, packaging, container, security, quality, and release-automation deliverables are
implemented. Two broader accepted-design statements are not fully implemented and are now explicit
P0 roadmap items rather than silently claimed complete:

1. [SG-001](roadmap.md#3-sg-001-multi-source-scheduled-replay): multi-source timestamp
   normalization, time shifting, merge ordering, and loop epochs. The schema accepts `start_at` and
   `source_priority`, but the model/scheduler does not consume them.
2. [SG-002](roadmap.md#4-sg-002-openmetrics-negotiation): explicit OpenMetrics HTTP negotiation.
   Prometheus text exposition is complete and interoperable; OpenMetrics selection is not.

Release publication is automated but requires an actual signed release tag, protected GitHub
environment, PyPI Trusted Publisher, and GHCR permissions. Those are deployment prerequisites, not
missing repository code.

## 2. Phase verification matrix

| Phase | Result | Implementation evidence | Verification evidence |
|---|---|---|---|
| 0 — design approval | Verified | Accepted status and repository boundaries in [index.md](index.md), solution/configuration/OpAMP designs | Design status is `accepted`; provider deployment is excluded consistently |
| 1 — package/configuration | Verified | Root `pyproject.toml`, `uv.lock`, `src/signal_generator/config`, four packaged schemas, three startup shells | CLI/config unit and contract tests; wheel/sdist build, Twine, fresh-environment smoke, schema package data, Ruff/Pylint/Xenon |
| 2 — log replay | Verified | Parser, formatter, source reader, monotonic scheduler, output registry, six built-in transports, legacy converter | Byte-exact parser/formatter, fake-clock scheduler, retry/lifecycle, local TCP/HTTP integration tests; documented Groovy differences |
| 3 — metric pull | Verified for required Prometheus scraper behavior; SG-002 remains | JSONL models/validation, atomic cursor/store, isolated registry/collector, HTTP lifecycle routes, four EOF policies, NGINX fixture | Metric-family/parser tests, concurrency tests, non-consuming health tests, real Prometheus pull profile. Explicit OpenMetrics negotiation is absent |
| 4 — scheduled push | Verified | Push adapter protocol, Pushgateway client, independent cursor, interval/source timing, retry/backoff, auth/TLS | Same-frame retry, one-step success, pull/push independence, real Pushgateway profile |
| 5 — container/Quart/demo | Verified | Non-root multi-stage image, host-independent runtime, Quart blueprint attachment, prefixed routes, phase-5 Compose/verifier | Pull, push, and unified profiles pass; Prometheus API sees NGINX metrics; multi-runtime isolation and awaited shutdown tests pass |
| 6 — OpAMP adapter | Verified | Independent adapter TOML/schema/CLI/entry point; supervised lifecycle; unified Quart app; adapter-owned `SimulatorInstance` around the public OpAMP simulator client | Adapter tests, installed entry-point and wheel smoke, one-process unified container against an unmodified `opamp-core`; no provider or SignalGenerator-specific core dependency |
| 7 — hardening/release | Implemented; publication awaits a release tag | Benchmark, failure injection, security gate, lock, SBOM/image-scan/signing/provenance workflow, checksums, compatibility/release docs | Core and adapter coverage/complexity gates, dependency audit, Actionlint, repeat-build hash equality, Twine and clean-install smoke |

## 3. Deliverable and gate observations

- Core tests currently exercise configuration, logs, every metric family, cursor concurrency,
  lifecycle routes, Pushgateway behavior, embedding, failure injection, and release contracts.
- Adapter tests exercise schema-only/full validation, installed discovery, supervised lifecycle,
  invalid remote configuration, passive health, unified routes, and deterministic shutdown.
- The cloud regression workflow can target an ephemeral AWS or Azure self-hosted runner and retains
  machine-readable evidence for pull, push, and unified profiles.
- `opamp-core` supplies the generic simulator client without SignalGenerator-specific changes.
  Embeddable lifecycle, schemas, entry points, and composition remain in the independent adapter.
- The OpAMP provider is not a deployment mode and is not in the adapter dependency graph.
- Copyright and project metadata in tracked content and current release archives use `opamp.info`;
  references to the original `mp3monster/LogGenerator` repository remain only as source attribution.

## 4. Definition-of-done audit

All definition-of-done statements pass except the unqualified multi-signal timing statement. Current
log replay preserves adjacent timestamp intervals and supports acceleration/loops; source-timed
metric pushes are implemented. Cross-source normalization and merged ordering are SG-001.

The signed-tag workflow is implemented and statically validated. It can produce wheel, source,
image, SBOM, checksums, signatures, and provenance, but the first production invocation is
necessarily evidenced by the first signed release rather than this source audit.

## 5. Re-verification commands

```text
python scripts/security_checks.py
python scripts/benchmark_replay.py --output test-results/performance.json
python scripts/run_regression.py --profile all --opamp-core-context ../opamp2
python -m build --outdir dist/core .
python -m build --outdir dist/adapter integrations/opamp-simulator
python -m twine check dist/core/* dist/adapter/*
docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:latest
```

The release workflow adds image scanning, package/image SBOMs, signing, and attestations on a
verified tag.
