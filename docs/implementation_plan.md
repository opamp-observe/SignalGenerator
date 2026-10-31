# Implementation plan

## 1. Delivery rule

No runtime implementation should begin until the design documents in this folder are accepted.
Changes should be delivered in small phases with passing quality gates. OpAMP composition is built
as the independent `signal-generator-opamp-sim` distribution. `opamp-core` changes are limited to a
generic, stable embeddable simulator-client API.

## 2. Phase 0: design approval

Deliverables:

- Review architecture and repository boundary.
- Confirm canonical configuration and metric-frame schema.
- Confirm Pushgateway as the initial push protocol.
- Confirm independent pull and push cursors.
- Confirm legacy LogGenerator compatibility scope.
- Confirm adapter-module ownership and generic simulator-client dependency contract.
- Confirm standalone and unified-simulator Quart deployment contracts.
- Confirm cyclomatic-complexity thresholds and wheel/release policy.

Exit gate: design status changes from `proposed` to `accepted` in [index.md](index.md).

## 3. Phase 1: package and configuration foundation

Implementation status: **implemented; quality and artifact gates verified for version 0.1.0**.

Deliverables:

- `src/signal_generator` package and CLI entry point.
- Canonical root `pyproject.toml` with runtime, Quart, test, quality, and release dependency sets.
- PowerShell, Windows Command Prompt, and Bash startup wrappers that use the project virtual
  environment and preserve CLI arguments and exit status.
- Typed configuration models and loader.
- Draft 2020-12 configuration, metric-frame, adapter, and validation-result JSON Schema artifacts.
- Path resolution, environment overrides, redacted effective config.
- Schema-backed `validate` with text/JSON formats, stable diagnostics and exit codes, plus
  `print-effective-config`.
- Logging and graceful lifecycle skeleton.
- Unit and contract tests for all checked-in examples.
- Ruff C90, Radon, and Xenon configuration with the agreed complexity limits.

Exit gate:

- Clean wheel and source distribution build, metadata check, content audit, and install in fresh
  base and Quart-extra environments.
- All static checks pass.
- Cyclomatic complexity is at most B per function and A by module/package average.
- Configuration tests meet their coverage target.
- Packaged schemas, Python models, checked-in examples, and CLI validation results pass drift and
  clean-wheel contract tests.
- No listener or replay implementation is required yet.

## 4. Phase 2: log replay core

Implementation status: **implemented; local transport and deterministic timing gates verified**.

Deliverables:

- Log source reader, multiline grouping, token parser, and formatter.
- Monotonic replay scheduler with repeats and acceleration.
- stdout, stderr, file, TCP, HTTP, and Python logging outputs.
- Output plugin registry.
- Legacy `.properties` adapter and conversion command.
- Compatibility fixtures based on public original examples.

Exit gate:

- Byte-exact output tests.
- Deterministic fake-clock timing tests.
- Local TCP and HTTP integration tests.
- Documented differences from the Groovy implementation.

## 5. Phase 3: metric pull replay

Implementation status: **implemented; pull sequencing, concurrency, lifecycle-route, exposition,
and container gates verified**.

Deliverables:

- Metric-frame models, JSONL reader, and descriptor validation.
- Frame store and thread-safe pull cursor.
- Custom Prometheus collector and isolated registry.
- `/metrics`, `/healthz`, `/readyz`, and `/` routes.
- EOF policies and self-metrics.
- NGINX metrics fixture.

Exit gate:

- Every metric family renders valid Prometheus/OpenMetrics text.
- Concurrency and sequence tests pass without sleep-based races.
- Health/readiness calls demonstrably do not advance frames.
- Pull container test passes.

## 6. Phase 4: scheduled push

Implementation status: **implemented; retry retention, cursor independence, authentication/TLS,
and real Pushgateway interoperability gates verified**.

Deliverables:

- Push adapter protocol.
- Pushgateway implementation.
- Independent push cursor.
- Interval scheduler, retry, backoff, auth, and TLS handling.
- Push self-metrics and diagnostics.

Exit gate:

- Failed push retries the same frame.
- Successful push advances exactly once.
- Pull and push sequences remain independent.
- Real Pushgateway container interoperability passes.

## 7. Phase 5: container, embedded Quart, and demonstration

Implementation status: **implemented**. The root image, pull/push Compose profiles, Prometheus API
verification, host-independent runtime, optional Quart attachment, and unified adapter image/profile
are checked in under `tests/test-containers/phase5` and `integrations/opamp-simulator`.

Deliverables:

- Multi-stage, non-root Dockerfile.
- Host-independent runtime API plus optional Quart registration adapter.
- Prefixed embedded routes and Quart lifecycle hooks.
- NGINX replay demo data and configuration.
- Prometheus and Pushgateway Compose services.
- Unified consumer-simulator Quart-container profile proving one process and one listener.
- Automated end-to-end verifier.
- User documentation and troubleshooting.

Exit gate:

- Clean image build.
- Healthcheck uses `/healthz`.
- Pull and push Compose profiles pass from a clean checkout.
- Prometheus query API shows the expected replayed NGINX series.
- Multiple runtime metric paths coexist without route, cursor, or registry collision.
- Embedded shutdown leaves no replay task running.

## 8. Phase 6: separately built OpAMP simulator adapter

Implementation status: **implemented**. Generic simulator lifecycle changes reside in
`opamp-observe/opamp-core`; all SignalGenerator-aware behavior resides in the independently built
`integrations/opamp-simulator` distribution.

Generic dependency deliverables in `opamp-core`:

- Public embeddable async simulator-client lifecycle API.
- Cancellable connection, heartbeat, scripted-response, logical-restart, and shutdown behavior.
- Public configuration, identity, response-plan, and health types.
- API contract tests and versioned compatibility guarantees with no SignalGenerator references.
- Existing launcher and provider behavior unchanged.

Deliverables in `integrations/opamp-simulator`:

- Independent `pyproject.toml`, lock file, wheel, source distribution, and console command.
- Installed `opamp_consumer.plugins` entry point for supervised mode.
- Schema-backed adapter `validate` command using the shared diagnostic result contract.
- Lifecycle, health, version, config metadata, and remote-config adapter behavior.
- Unified Quart application composed from public dependency APIs.
- In-process SignalGenerator runtime attachment with logical restart and remote configuration.
- Unified adapter image and configuration schema.
- Unit, integration, and cross-repository contract tests.
- Adapter operations and compatibility documentation.

Exit gate:

- Base adapter wheel installs against the declared SignalGenerator and OpAMP dependency ranges
  without Quart; the `unified` extra installs and starts the Quart host.
- Adapter and nested SignalGenerator configurations validate from installed wheels with actionable
  text output and machine-readable JSON, without starting runtime resources.
- Supervised plugin registers as a distinct healthy OpAMP agent through installed discovery.
- Health polling never consumes a metric frame.
- Valid remote config updates and restarts the child.
- Invalid remote config leaves the running scenario unchanged.
- Consumer-sim start and stop behavior remains reliable.
- Unified simulator mode runs simulated OpAMP clients and SignalGenerator runtimes in one Quart
  process, with no supervisor/observer relationship or SignalGenerator subprocess.
- The OpAMP provider package, image, routes, and component configuration remain unchanged.
- No SignalGenerator-specific module, dependency, schema, or entry point is added to `opamp-core`.

## 9. Phase 7: hardening and release

Implementation status: **implemented**. The repository includes measured performance floors,
failure injection, repository and image security gates, package and image SBOMs, SHA-256 manifests,
signed-tag enforcement, OIDC trusted publication, keyless image signing, artifact provenance, and
an explicit compatibility matrix.

Deliverables:

- Performance measurements and documented limits.
- Dependency audit, source scan, image scan, and SBOM.
- Failure injection for ports, files, network, signals, and malformed data.
- Versioned release notes and migration guide from the Groovy tool.
- Signed-tag release workflow, trusted publication, wheel/source/image procedures, checksums,
  provenance, and compatibility matrix.

Exit gate:

- All repository-wide checks pass.
- Complexity and coverage gates pass with retained reports.
- Wheel and source distribution reproduce and pass clean-install smoke tests.
- No open critical/high security findings without documented disposition.
- Release artifacts reproduce from a clean checkout.

Implementation evidence:

- `scripts/benchmark_replay.py` and [performance limits](performance_limits.md).
- `tests/integration/test_failure_injection.py` and [security hardening](security_hardening.md).
- `.github/workflows/release.yml`, `scripts/release_artifacts.py`, and the operational
  [release process](release_process.md).
- [Compatibility matrix](compatibility_matrix.md) and versioned changelog/migration guidance.

## 10. Work breakdown

| Work item | Repository | Depends on |
|---|---|---|
| Config model and schemas | SignalGenerator-Python | Design approval |
| Log compatibility adapter | SignalGenerator-Python | Config foundation |
| Log outputs and scheduler | SignalGenerator-Python | Package foundation |
| Metrics JSONL and cursor | SignalGenerator-Python | Config foundation |
| Pull server and collector | SignalGenerator-Python | Metrics cursor |
| Pushgateway adapter | SignalGenerator-Python | Metrics cursor |
| TOML metadata and wheel pipeline | SignalGenerator-Python | Package foundation |
| Quart runtime attachment API | SignalGenerator-Python | Stable runtime lifecycle |
| Container/demo | SignalGenerator-Python | Pull and push |
| Generic embeddable simulator API | `opamp-observe/opamp-core` | Stable simulator lifecycle |
| Adapter TOML and wheel pipeline | integrations/opamp-simulator | Published dependency APIs |
| Supervised consumer plugin | integrations/opamp-simulator | Stable CLI/health contract |
| Unified simulator Quart host | integrations/opamp-simulator | Embeddable dependency APIs |
| Cross-package E2E | integrations/opamp-simulator plus built wheels | All three distributions |

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Scrapes race and skip frames | Nondeterministic demos | Atomic cursor assignment and concurrency tests. |
| Health polling advances replay | Hidden sequence corruption | Stable `/healthz`; contract tests forbid `/metrics` polling. |
| Pull and push steal each other's frames | Incomplete sequences | Independent cursors by design. |
| Metric descriptors change between frames | Invalid Prometheus series | Validate all frames before readiness. |
| Counter values reset | Misleading assumptions | Replay exact snapshot and document restart semantics. |
| Push interpreted as direct Prometheus text ingest | Integration failure | Name initial protocol `pushgateway`; keep remote write separate. |
| Large JSONL consumes excess memory | Startup/memory pressure | Limits first; indexed file store can replace in-memory store later. |
| Legacy datetime formats differ | Migration errors | Explicit translator, conversion diagnostics, compatibility fixtures. |
| Adapter code leaks into either dependency | Tight coupling | Independent distribution, direct dependencies, and wheel-content contracts. |
| Remote config breaks running demo | Downtime | Candidate validation, atomic replace, readiness check, rollback. |
| Container shutdown loses state | Unclean tests | Exec entrypoint, signal handling, bounded close/flush. |
| Replay logic becomes branch-heavy | Defects and weak reviewability | Complexity 10 hard limit, A averages, focused branch tests. |
| Embedded runtime routes collide | Startup failure or wrong data | Unique runtime prefixes and URL-map collision validation. |
| Embedded tasks outlive Quart shutdown | Leaks and corrupt test state | Host lifecycle hooks and awaited cancellation. |
| Multiple Quart workers duplicate replay | Duplicate agents and signals | Enforce one worker and explicit instance partitioning. |
| Wheel metadata and automation drift | Broken installs/releases | Root TOML source of truth and artifact contract tests. |

## 12. Deferred features

These are intentionally outside the initial implementation unless promoted through design review:

- Prometheus remote-write push adapter.
- Hot reload without process restart.
- Shared pull/push cursor.
- Streaming/indexed frame storage for very large files.
- Random or formula-based synthetic metric generation.
- Browser UI.
- Authentication on the local pull endpoint.
- Distributed cursor coordination across replicas.

## 13. Definition of done

The project is complete for the requested scope when:

- The Python tool reproduces the agreed log replay features.
- Metric JSONL frames replay deterministically by scrape and configured push interval.
- Timestamped signals are time-shifted, merged, and looped using the documented ordering rules.
- Pull and Pushgateway flows are demonstrated with NGINX-style metrics.
- Unit, contract, integration, and container end-to-end tests pass.
- Coverage and cyclomatic-complexity gates pass.
- Verified wheel and source distribution are created from canonical TOML metadata.
- A non-root production-style container is available.
- Standalone and unified-simulator Quart deployment modes are demonstrated.
- The SignalGenerator plugin behavior is documented.
- The separate adapter wheel is implemented, built, installed, and tested against published
  SignalGenerator and OpAMP simulator-client APIs.
- `opamp-core` contains only generic simulator-client API changes and no SignalGenerator-specific
  code.
- The signed-tag release process produces wheel, source, image, SBOM, checksums, and provenance.
- Configuration, migration, operations, and troubleshooting documentation are complete.

