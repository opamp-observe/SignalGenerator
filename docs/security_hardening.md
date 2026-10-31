# Security hardening and failure policy

## Release gates

`python scripts/security_checks.py` is the repository-wide pre-package gate. It runs Ruff's
security rules, Pylint, core and adapter tests with branch coverage, Xenon complexity limits, and
`pip-audit`. CI additionally scans built images with Trivy and generates SBOMs with Syft.

Critical or high image findings block release. A temporary exception requires a changelog entry,
an owner, an expiry date, and evidence that no fixed package or base image exists. Secrets are
supplied through named environment variables and are redacted from effective configuration.

## Failure injection coverage

The automated suite injects:

- an occupied pull port and verifies failed startup does not leak another listener;
- missing and malformed JSONL sources with line-aware diagnostics;
- a Pushgateway connection outage while retaining the immutable frame for retry;
- cooperative signal shutdown; and
- retry, cursor, lifecycle, and invalid remote-configuration failures in the focused unit and
  adapter suites.

Container profiles cover service startup ordering, readiness, real Prometheus scraping, real
Pushgateway delivery, and unified shutdown. Health probes use `/healthz`; they never scrape
`/metrics` and therefore never advance replay.

## Artifact evidence

Each release retains test and coverage results, complexity output, performance JSON, dependency and
image scan results, package and image SBOMs, SHA-256 manifests, provenance attestations, and image
signatures. The compatibility matrix records exactly which independently versioned packages were
tested together.
