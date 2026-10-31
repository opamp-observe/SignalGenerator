# Release process

## Release identities

Core tags use `vX.Y.Z`. Adapter tags use `signal-generator-opamp-sim-vX.Y.Z`. Both must be signed,
annotated tags pointing at reviewed commits. Versions are independent and must match the owning
`pyproject.toml`.

```text
git tag -s v0.1.0 -m "SignalGenerator 0.1.0"
git tag -s signal-generator-opamp-sim-v0.1.0 -m "SignalGenerator OpAMP adapter 0.1.0"
git push origin <tag>
```

The release workflow rejects lightweight, unsigned, unverified, or version-mismatched tags.

## One-time repository configuration

1. Protect `main`, both release tag patterns, and the `pypi` environment with required review.
2. Configure PyPI Trusted Publishers for `.github/workflows/release.yml`, environment `pypi`, for
   both Python projects. No long-lived PyPI token is stored.
3. Allow GitHub Actions to write packages, attestations, releases, and OIDC identity tokens only in
   the jobs that need those permissions.
4. Enable immutable GHCR package tags and retain GitHub artifact attestations.

PyPI documents the trusted-publisher setup at
<https://docs.pypi.org/trusted-publishers/using-a-publisher/>. GitHub documents artifact
attestations at
<https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/>.

## Pre-tag gate

From the activated project environment:

```text
python scripts/security_checks.py
python scripts/benchmark_replay.py --output test-results/performance.json
python -m build --outdir dist/core .
python -m build --outdir dist/adapter integrations/opamp-simulator
python -m twine check dist/core/* dist/adapter/*
python scripts/release_artifacts.py dist/core dist/adapter --output dist/evidence
```

Also run the pull, push, and unified phase-5 Compose profiles from a clean image cache. Confirm the
version, changelog, migration guide, compatibility matrix, schema examples, and release notes agree.

## Automated release

For the selected component, `.github/workflows/release.yml`:

1. verifies the signed annotated tag through GitHub's tag verification record;
2. installs the compatible OpAMP packages and runs source, dependency, coverage, complexity, and
   test gates;
3. builds the wheel and source distribution from the tag and runs `twine check`;
4. emits CycloneDX package and SPDX image SBOMs plus `SHA256SUMS` and a JSON manifest;
5. uses PyPI OIDC Trusted Publishing;
6. publishes the immutable GHCR image by version and digest;
7. blocks critical/high image vulnerabilities unless explicitly fixed and reviewed;
8. keyless-signs the image and records GitHub/Sigstore provenance attestations; and
9. creates a GitHub release containing distributions and release evidence.

The core and adapter image jobs are separate. The adapter image checks out `opamp-observe/opamp-core`
as a named build context; it does not copy adapter logic into that repository or the provider.

## Verification and rollback

Verify downloaded files with `sha256sum --check SHA256SUMS`, Python provenance with
`gh attestation verify`, and the image signature with `cosign verify`. Install the public wheel in a
fresh environment and run `--version` plus configuration validation before promoting deployment.

Published versions and immutable image digests are never overwritten. Yank a bad Python release,
move only convenience image tags back to the last known-good digest, document the incident, and
release a new patch version.
