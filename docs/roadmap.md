# SignalGenerator roadmap

## 1. Purpose and maintenance

This document is the single register for planned enhancements, deferred design work, and gaps found
by implementation audits. Design documents may explain context, but they link to an item here rather
than keeping an independent list of unowned future work.

Statuses are `proposed`, `planned`, `in_progress`, `blocked`, or `complete`. An item moves to
`complete` only when its code, schemas, documentation, tests, and applicable package/container gates
have passed. Priority `P0` closes an accepted-design or safety gap; `P1` is the next product surface;
`P2` is an optional extension or scalability improvement.

## 2. Roadmap summary

| ID | Priority | Status | Capability | Primary repository |
|---|---|---|---|---|
| SG-001 | P0 | planned | Multi-source timestamp normalization, merge scheduling, time shifting, and loop epochs | SignalGenerator-Python |
| SG-002 | P0 | planned | Explicit Prometheus/OpenMetrics HTTP content negotiation | SignalGenerator-Python |
| SG-003 | P0 | planned | OpAMP custom action handlers for receiving configuration and test-data files | `integrations/opamp-simulator` |
| SG-004 | P1 | proposed | Prometheus remote-write push adapter | SignalGenerator-Python |
| SG-005 | P1 | proposed | Validated hot reload without a process restart | Core and adapter |
| SG-006 | P2 | proposed | Optional shared pull/push cursor | SignalGenerator-Python |
| SG-007 | P1 | proposed | Streaming or indexed frame storage for very large JSONL sources | SignalGenerator-Python |
| SG-008 | P2 | proposed | Seeded random and formula-based synthetic metric generation | SignalGenerator-Python |
| SG-009 | P2 | proposed | Browser user interface | SignalGenerator-Python |
| SG-010 | P1 | proposed | Authentication and authorization on local pull/lifecycle routes | SignalGenerator-Python |
| SG-011 | P2 | proposed | Distributed cursor coordination across replicas | SignalGenerator-Python |
| SG-012 | P2 | proposed | Trace-payload replay through the reserved `traces` namespace | SignalGenerator-Python |
| SG-013 | P2 | proposed | Permissive legacy migration mode with explicit lossy-conversion diagnostics | SignalGenerator-Python |
| SG-014 | P2 | proposed | Pushgateway additive `POST` method | SignalGenerator-Python |
| SG-015 | P2 | proposed | Explicit Prometheus sample timestamps | SignalGenerator-Python |
| SG-016 | P2 | proposed | PEP 735 dependency groups when supported by the installer baseline | SignalGenerator-Python |
| SG-017 | P0 | planned | Complete and verify publication of the core and OpAMP adapter distributions through PyPI | Core and adapter |
| SG-018 | P1 | planned | Stable, documented utility-library API for embedding SignalGenerator in Python applications | SignalGenerator-Python |

## 3. SG-001: multi-source scheduled replay

The accepted design describes a `SignalEnvelope` ordered by normalized source timestamp, configured
source priority, and stable source sequence. The schema already accepts `replay.start_at` and
`replay.source_priority`, but the current typed model and scheduler do not consume them, and one log
configuration owns only one source.

Delivery scope:

- represent one or more scheduled sources without breaking the schema-version-1 single-source form;
- normalize absolute and relative timestamps into immutable envelopes;
- calculate one scenario offset from the earliest timestamp to `start_at` (`now` or RFC 3339);
- merge scheduled logs and source-timed pushes by timestamp, priority, then source sequence;
- create monotonic loop epochs using the prior final timestamp and `loop_gap_ms`;
- keep demand-driven metric scrapes outside the merge scheduler;
- reject or warn on timing fields that cannot affect the configured scenario; and
- add fake-clock, tie-break, acceleration, cancellation, cycle, and schema/model-drift tests.

Acceptance requires the corresponding definition-of-done statement in
[implementation_plan.md](implementation_plan.md) to pass without qualification.

## 4. SG-002: OpenMetrics negotiation

The current server always returns Prometheus text format version 0.0.4. Add deterministic parsing of
the request `Accept` header, OpenMetrics generation and content type, explicit fallback behavior,
and tests proving that negotiation does not advance more than one frame. Prometheus text must remain
the compatible default.

## 5. SG-003: OpAMP configuration and test-data file actions

The separately built OpAMP extension will provide custom action handlers that receive a complete
SignalGenerator scenario bundle: configuration plus referenced log, metric JSONL, response-plan, or
other test-data files. SignalGenerator-specific handlers remain in
`signal-generator-opamp-sim`; they are not built into the OpAMP provider or the generic consumer
core.

### 5.1 Protocol and actions

Define a versioned custom capability such as `io.opamp.signal_generator.files.v1` with idempotent
actions:

- `stage_bundle`: receive files into an isolated candidate area without changing the running
  scenario;
- `validate_bundle`: validate the configuration, every referenced path, schemas, descriptors, and
  adapter configuration;
- `activate_bundle`: atomically select an already validated bundle and perform the appropriate
  supervised restart or unified logical restart;
- `bundle_status`: return request ID, content hash, validation diagnostics, and active/staged state;
  and
- `discard_bundle`: remove an inactive staged bundle.

The custom-message data contract will include a protocol version, request ID, action, bundle ID,
manifest, per-file relative path, media type, byte size, SHA-256 digest, encoding, and content. Large
bundles must use bounded chunking or an authenticated object reference rather than unbounded message
payloads. Every response uses the same request ID and stable machine-readable success/error codes.

### 5.2 Safety and atomicity

- Normalize paths and reject absolute paths, traversal, alternate data streams, device names,
  symlinks, and writes outside the configured scenario root.
- Enforce configurable bundle, file-count, per-file, and decompressed-size limits before writing.
- Verify declared length and SHA-256 before making a file visible.
- Write with restrictive permissions to a newly created staging directory; never execute received
  content.
- Validate the complete dependency graph before activation. A configuration may reference only
  files present in the same immutable bundle or an explicitly allowlisted installed resource.
- Activate with atomic directory/manifest replacement and retain the previous known-good bundle for
  rollback.
- Make repeated request IDs and content hashes idempotent and safe after reconnect.
- Redact secrets and file content from normal logs, OpAMP status, and validation summaries.

### 5.3 Package and OpAMP boundaries

The adapter client should resolve its handler implementations from its installed package. If the
current OpAMP consumer can discover handlers only from source folders, `opamp-core` may add a
generic entry-point or factory-registration API; that API must contain no SignalGenerator names,
schemas, or dependencies. Provider-side test tooling may send the versioned custom message, but the
provider package must not embed SignalGenerator behavior.

Supervised mode stages files, validates them through the installed SignalGenerator CLI/API, then
restarts only the owned child. Unified mode validates in memory and swaps the affected runtime using
the logical lifecycle without restarting Quart or unrelated simulator instances.

### 5.4 Verification

Required tests cover valid multi-file delivery, reordered chunks, duplicates, digest mismatch,
truncation, traversal, symlink escape, oversized payloads, malformed JSON/JSONL, missing references,
descriptor drift, concurrent requests, reconnect/idempotency, activation rollback, health probes
that do not consume frames, and independent activation of multiple unified runtimes. Container E2E
must upload and activate an NGINX scenario, observe its metrics through Prometheus, replace it with a
second bundle, and prove no partial bundle or extra process becomes visible.

## 6. Remaining capability details

### SG-004: remote write

Add a separate adapter for the Prometheus remote-write protocol, including protobuf/snappy encoding,
endpoint authentication, timestamp policy, batching, retries, and interoperability tests. It must
not reinterpret a normal Prometheus scrape endpoint as a push target.

### SG-005: hot reload

Allow a validated candidate to replace a running standalone or supervised scenario without a host
process restart. Preserve the old scenario until new resources are ready, then swap atomically or
roll back.

### SG-006 and SG-011: cursor coordination

SG-006 optionally couples pull and push in one process. SG-011 defines a durable coordination
protocol for replicas. Both require explicit delivery and failure semantics and remain opt-in.

### SG-007: large sources

Replace eager in-memory loading with a validated index or streaming store while retaining precise
line diagnostics, descriptor stability, EOF semantics, concurrency, and deterministic replay.

### SG-008 and SG-009: scenario authoring

Synthetic generation must be seeded and reproducible. A browser UI must use the same schemas and
validation API, introduce no manual bearer-token field, and remain outside the OpAMP provider.

### SG-010: pull endpoint security

Support deployment-managed authentication/authorization without exposing secrets in configuration
output. Preserve unauthenticated loopback operation as an explicit development mode.

### SG-012: traces

Define a separate trace-frame schema, replay transport, scheduling semantics, limits, and
interoperability target before allowing `traces.enabled: true`.

### SG-013 through SG-016: bounded extensions

- SG-013 reports every dropped or approximated legacy property before producing configuration.
- SG-014 adds Pushgateway `POST` without changing the default replace-by-`PUT` behavior.
- SG-015 is gated by demonstrated stale-sample and out-of-order handling requirements.
- SG-016 removes duplicated development-extra declarations only when supported across all target
  installers and build runners.

### SG-017: PyPI publication

Complete the first production publication of both independently versioned distributions:

- `signal-generator`, built from a signed `vX.Y.Z` tag; and
- `signal-generator-opamp-sim`, built from a signed
  `signal-generator-opamp-sim-vX.Y.Z` tag.

The GitHub release workflow and Trusted Publishing job already exist. Completion requires the
external project and repository configuration plus evidence from an actual release:

- create or confirm both PyPI projects and configure narrowly scoped OIDC Trusted Publishers for
  `.github/workflows/release.yml` and its protected `pypi` environment;
- confirm that a compatible `opamp-consumer` release is publicly installable before publishing the
  adapter;
- perform a TestPyPI rehearsal without weakening the production trusted-publisher boundary;
- publish wheel and source distributions only from reviewed, signed, version-matched tags;
- verify project metadata, rendered README, SPDX licence expression, Python-version classifiers,
  package data, hashes, attestations, and release notes;
- install each public wheel into clean Python 3.10 through 3.13 environments, run `pip check`, import
  its package, execute `--version`, and validate a packaged example; and
- record the immutable PyPI URLs and release evidence in the GitHub release.

Published files are never replaced. A defective release is yanked with a reason and followed by a
new patch release. Acceptance requires the public-install smoke tests to run from PyPI rather than a
local wheel or checkout.

### SG-018: utility-library API and guide

Make SignalGenerator a supported Python utility library as well as a command-line application. The
first release currently exposes internal modules that the CLI and adapter use, but the top-level
package promises only `__version__`; consumers should not be told to depend on internal module
layout until this item is complete.

Delivery scope:

- define a small, typed, top-level public API and export it explicitly through
  `signal_generator.__all__`;
- provide a non-terminating configuration-validation function that returns structured diagnostics
  instead of printing or raising `SystemExit`;
- provide factories for constructing a runtime from a configuration file, mapping, or typed model;
- support explicit asynchronous `start`, `stop`, and context-manager lifecycle operations;
- allow callers to supply logging, clocks, transports, HTTP hosting, and cancellation dependencies
  without mutating process-global state;
- document whether runtime objects are reusable, thread-safe, and safe to instantiate more than
  once in a process;
- keep Quart attachment and the OpAMP adapter optional, with clear extras and import boundaries;
- apply semantic-versioning rules to exported names and publish deprecation guidance; and
- add API-reference, type-checking, unit, multi-instance, cancellation, wheel-install, and example
  tests.

Add `docs/library_usage.md` with copyable examples for validation, one-shot log replay, metric-frame
loading, managed asynchronous runtime use, custom log-output registration, and Quart attachment.
Examples must import only documented public names and must run against the installed wheel in CI.
