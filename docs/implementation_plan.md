# Remaining implementation plan

Completed phases and their evidence are recorded in
[implementation verification](implementation_verification.md). Detailed scope, ownership, status,
and acceptance criteria for unfinished work remain authoritative in
[roadmap.md](roadmap.md).

- **SG-001 — Multi-source scheduled replay (P0):** support multiple timestamped sources,
  normalize absolute and relative times, shift the scenario to a configured start, merge by time
  and priority, and create monotonic loop epochs.
- **SG-002 — OpenMetrics negotiation (P0):** negotiate Prometheus versus OpenMetrics from the HTTP
  `Accept` header while ensuring one successful scrape advances exactly one frame.
- **SG-003 — OpAMP scenario-bundle actions (P0):** securely stage, validate, activate, inspect,
  roll back, and discard configuration plus referenced test-data files through versioned,
  idempotent OpAMP custom actions.
- **SG-004 — Prometheus remote write (P1):** add an authenticated protobuf/snappy remote-write
  adapter with batching, timestamps, retries, and interoperability coverage.
- **SG-005 — Validated hot reload (P1):** atomically replace standalone or supervised scenarios
  without restarting the host process and retain the previous scenario for rollback.
- **SG-006 — Optional shared cursor (P2):** define and implement explicit opt-in semantics for a
  pull and push path sharing one cursor.
- **SG-007 — Large-source storage (P1):** replace eager loading with bounded streaming or indexed
  storage while preserving validation, deterministic ordering, and EOF behavior.
- **SG-008 — Synthetic metrics (P2):** generate reproducible seeded or formula-based metric values
  through the same typed schema and validation pipeline.
- **SG-009 — Browser interface (P2):** provide schema-backed scenario authoring and runtime control
  without duplicating validation logic or weakening secret handling.
- **SG-010 — Pull and lifecycle endpoint security (P1):** add deployment-managed authentication
  and authorization while retaining explicit unauthenticated loopback development mode.
- **SG-011 — Distributed cursor coordination (P2):** define durable ordering, ownership, recovery,
  and failure semantics for replay across multiple replicas.
- **SG-013 — Permissive legacy migration (P2):** add an explicit lossy-conversion mode that reports
  every dropped, approximated, or ambiguous legacy property.
- **SG-014 — Additive Pushgateway delivery (P2):** support opt-in `POST` without changing the
  existing replace-by-`PUT` default.
- **SG-015 — Explicit Prometheus sample timestamps (P2):** add timestamps only with documented
  stale-sample and out-of-order behavior.
- **SG-016 — PEP 735 dependency groups (P2):** consolidate duplicated development dependency
  declarations after every supported installer and build runner supports the standard.
- **SG-017 — Public package publication (P0):** configure the external PyPI trusted-publisher and
  protected-environment settings, publish both distributions, verify clean installs on Python
  3.10–3.13, and retain immutable release evidence.
  - **Outstanding external configuration:**
    - Create or confirm the `signal-generator` and `signal-generator-opamp-sim` projects on PyPI.
    - Create the protected GitHub `pypi` environment, require release approval, and restrict it to
      protected `main` and release-tag deployments.
    - Configure a PyPI Trusted Publisher for the `signal-generator` project using
      `.github/workflows/publish-main.yml`, environment `pypi`, for main-quality-success wheel
      publication.
    - Configure PyPI Trusted Publishers for both projects using `.github/workflows/release.yml`,
      environment `pypi`, for signed-tag wheel and source-distribution publication.
    - Protect `main`, require the complete `quality` workflow before merge, and protect the `v*`
      and `signal-generator-opamp-sim-v*` release-tag patterns.
    - Confirm repository Actions settings allow OIDC identity tokens, artifact attestations,
      GitHub release creation, and GHCR publication only for the scoped workflow jobs.
    - Confirm a compatible `opamp-consumer` version is publicly available before publishing the
      adapter distribution.
    - Configure a separately scoped TestPyPI Trusted Publisher for the release rehearsal.
  - **Publication execution and verification:**
    - Assign a new immutable version in the owning `pyproject.toml`, update the changelog and
      release notes, and ensure that version does not already exist on the target package index.
    - Perform the isolated TestPyPI rehearsal before production publication.
    - After publication, install each public wheel on Python 3.10–3.13, run `pip check`, validate a
      packaged example, and retain the PyPI URLs, hashes, attestations, and smoke-test evidence.
- **SG-018 — Supported Python library API (P1):** define a small typed top-level API for validation,
  runtime construction, asynchronous lifecycle, dependency injection, and optional Quart
  attachment, with compatibility policy and installed-wheel examples.
