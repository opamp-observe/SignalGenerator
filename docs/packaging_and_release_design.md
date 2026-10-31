# Packaging and release design

## 1. Packaging goals

- Use standards-based TOML metadata as the source of truth.
- Build a pure-Python wheel and source distribution from a clean checkout.
- Keep standalone and unified-simulator Quart dependencies explicit.
- Make build, test, security, complexity, and release tool versions visible in project metadata.
- Verify artifacts by installing them rather than testing only the source tree.
- Publish wheels, source distributions, containers, checksums, SBOMs, and attestations from
  independently versioned core and adapter release workflows.

## 2. TOML ownership

SignalGenerator core is one Python distribution and has one canonical root `pyproject.toml`. It owns:

- build backend and build requirements,
- `[project]` metadata and runtime dependencies,
- console scripts and plugin entry points,
- optional dependency groups,
- setuptools package discovery and package data,
- pytest, coverage, Ruff, Pylint, and complexity settings.

Do not duplicate these settings in `setup.py`, `setup.cfg`, or an application `requirements.txt`.
A lock file may pin development and release environments, but it does not replace project metadata.

The OpAMP integration is a second independently installable distribution under
`integrations/opamp-simulator/pyproject.toml`. It owns adapter code, its console command, installed
plugin entry point, unified Quart host, schemas, tests, and dependency bounds on:

- `signal-generator`,
- `jsonschema`, because the adapter validates its own configuration schema,
- `opamp-consumer`, because the concrete simulator client lives there,
- `opamp-consumer-sim`, because it supplies the simulator packaging and public embeddable API.

The adapter's `unified` extra adds its direct Quart dependency; the base installation remains
sufficient for supervised mode.

The adapter imports only published APIs and declares every directly imported distribution. No
SignalGenerator-specific dependency or entry point is added to an `opamp-core` TOML file.

## 3. Core `pyproject.toml` shape

The exact lower bounds are confirmed during implementation, but the structure is fixed:

```toml
[build-system]
requires = ["setuptools>=82", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "signal-generator"
version = "0.1.0"
description = "Replay logs and Prometheus metric frames for observability testing"
readme = "README.md"
requires-python = ">=3.10"
license = "Apache-2.0"
authors = [{ name = "Phil Wilkins" }]
keywords = ["logging", "metrics", "prometheus", "replay", "testing"]
dependencies = [
  "httpx>=0.27",
  "jsonschema>=4.23",
  "prometheus-client>=0.21",
]

[project.optional-dependencies]
quart = ["quart>=0.19.4"]
test = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "pytest-cov>=7.0.0",
]
quality = [
  "pylint>=3.0",
  "radon>=6.0",
  "ruff>=0.15.0",
  "xenon>=0.9",
]
release = [
  "build>=1.2",
  "twine>=6.0",
]
dev = [
  "build>=1.2",
  "pylint>=3.0",
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "pytest-cov>=7.0.0",
  "quart>=0.19.4",
  "radon>=6.0",
  "ruff>=0.15.0",
  "twine>=6.0",
  "xenon>=0.9",
]

[project.scripts]
signal-generator = "signal_generator.cli:main"

[project.entry-points."signal_generator.log_outputs"]
# Third-party distributions add named outputs in this group.

[tool.setuptools]
package-dir = { "" = "src" }
include-package-data = true

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
signal_generator = ["py.typed", "schemas/*.json"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "S", "C90"]
ignore = ["E501"]

[tool.ruff.lint.mccabe]
max-complexity = 10
```

The `dev` extra intentionally repeats the complete tool set so `pip install -e ".[dev]"` remains a
portable bootstrap command. A metadata contract test compares `dev` with the union of the narrower
extras so version floors cannot drift silently. PEP 735 migration is tracked as
[SG-016](roadmap.md).

Quart stays optional. The base wheel supports CLI/standalone use without installing a web
framework. `signal-generator[quart]` adds the runtime attachment API consumed by the separate
adapter distribution; it is not a provider integration extra.

### 3.1 Adapter `pyproject.toml`

`integrations/opamp-simulator/pyproject.toml` uses the same build backend and quality baseline but
produces `signal-generator-opamp-sim`. Its runtime metadata includes:

```toml
[project]
name = "signal-generator-opamp-sim"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "signal-generator>=0.1.0,<0.2.0",
  "jsonschema>=4.23",
  "opamp-consumer>=0.6.0,<0.7.0",
  "opamp-consumer-sim>=0.6.0,<0.7.0",
]

[project.optional-dependencies]
unified = ["quart>=0.19.4"]

[project.scripts]
signal-generator-opamp-sim = "signal_generator_opamp_sim.cli:main"

[project.entry-points."opamp_consumer.plugins"]
signal_generator = "signal_generator_opamp_sim.supervised_plugin:main"
```

The adapter base install supports supervised mode without installing Quart. Its `unified` extra
declares Quart directly because the adapter's app factory imports it. The adapter also has its own
`dev` extra, which includes `unified`, plus its own coverage source, Ruff first-party package list,
complexity gate, wheel-content contract, and lock file. Core and adapter builds never reach into
each other's source directories.

## 4. Version source

The release version is statically declared in `pyproject.toml` and read at runtime with
`importlib.metadata.version("signal-generator")`. Source modules do not contain a second manually
maintained version constant.

Versioning follows semantic versioning:

- Major: incompatible configuration, plugin, CLI, or replay semantics.
- Minor: backward-compatible signal/output/deployment capability.
- Patch: backward-compatible fix or documentation correction included with code.

Pre-releases use PEP 440 forms such as `1.0.0rc1`. Git tags use `v1.0.0`.

SignalGenerator, `signal-generator-opamp-sim`, `opamp-consumer`, and `opamp-consumer-sim` versions
are independent. Documentation and CI maintain a compatibility matrix rather than forcing lockstep
releases.

## 5. Wheel contents

The wheel must contain:

- `signal_generator` package modules,
- JSON configuration and metric-frame schemas,
- `py.typed`,
- licence and distribution metadata,
- console-script metadata,
- Consumer-simulator Quart attachment module even though Quart itself is optional.

The wheel must not contain:

- tests, coverage output, caches, local configuration, or demo runtime data,
- `.venv`, source-control metadata, build directories, or secrets,
- `signal_generator_opamp_sim` adapter code,
- container-only files.

Demo files and full documentation remain in the source distribution and repository. Small schema
examples required by runtime validation may be package data.

The adapter wheel contains only `signal_generator_opamp_sim`, its unified schema, console and plugin
entry-point metadata, typing marker, licence, and distribution metadata. It does not vendor either
dependency's packages or scenario data.

## 6. Build process

Canonical local commands:

```text
python -m pip install --upgrade build twine
python -m build
python -m build integrations/opamp-simulator
python -m twine check dist/*
python -m twine check integrations/opamp-simulator/dist/*
```

CI builds in an isolated environment from a clean tree. It sets `SOURCE_DATE_EPOCH` from the release
commit and builds twice in separate directories. Wheel file lists and hashes must match; if the
platform or build backend prevents byte-for-byte equality, the reason and normalized-content check
are documented.

Artifact verification:

1. Reject unexpected files by inspecting the wheel ZIP manifest.
2. Check core metadata, licence expression, Python requirement, and extras.
3. Install the wheel with `--no-index --find-links dist` into a clean environment.
4. Run `signal-generator --version`, text validation, and JSON validation-result smoke tests.
5. Install `signal-generator[quart]` into another clean environment.
6. Attach the runtime to a consumer-simulator Quart test app and exercise prefixed health and metric
   routes.
7. Install the base adapter wheel with compatible dependency wheels from a local wheelhouse; prove
   supervised-plugin discovery and that Quart is absent.
8. Install `signal-generator-opamp-sim[unified]` in another clean environment and run the
   unified-host smoke test.
9. Build the container from wheels, not from editable source installs.

## 7. Dependency reproducibility

- Runtime dependency ranges live in `pyproject.toml`.
- A checked-in lock file pins development, CI, demo, and release environments.
- CI has a periodic job that tests minimum declared versions separately from the locked current set.
- Container builds consume a hashed export or wheelhouse generated from the reviewed lock.
- Dependency updates include tests, licence review, vulnerability review, and lock regeneration.
- The wheel itself does not pin every transitive dependency; it declares compatible direct ranges.

## 8. Release prerequisites

Before a release candidate tag:

- Working tree is clean and the release commit is reviewed.
- Version, changelog, migration notes, and compatibility matrix agree.
- Configuration schemas and examples validate.
- Ruff, Pylint, tests, coverage, Radon, and Xenon gates pass.
- The wheel and source distribution for each distribution being released build and install
  successfully.
- Standalone, pull, push, unified-simulator Quart, and OpAMP compatibility suites pass.
- Dependency audit, secret scan, source scan, and container scan pass.
- Documentation names every configuration or behavior change.
- Release notes convert follow-up work into roadmap items rather than leaving it only in notes.

## 9. Release workflow

1. Prepare a release branch or reviewed release commit.
2. Set the PEP 440 version in the `pyproject.toml` owned by the distribution being released.
3. Update changelog, migration guide, and compatibility matrix.
4. Run the complete local/repository gate.
5. Create signed tag `vX.Y.Z` from the reviewed commit.
6. CI rebuilds from the tag; it never uploads developer-built artifacts.
7. CI publishes the wheel and source distribution using trusted publishing.
8. CI publishes the container with immutable version and digest plus optional moving minor/latest
   tags according to release policy.
9. CI publishes SHA-256 checksums, CycloneDX/SPDX SBOMs, build provenance, and signatures.
10. Run post-publish installation and container smoke tests against the public artifacts.
11. Publish release notes with links to artifacts and compatibility information.

Production publication requires an explicit protected-environment approval. Pull requests and
ordinary branch builds publish only retained CI artifacts or an internal test index.

Adapter releases use their own version and tag namespace, for example
`signal-generator-opamp-sim-v0.1.0`. An adapter release selects already published compatible core
and OpAMP dependency versions, runs its full wheel and integration matrix, and publishes only the
adapter wheel/source distribution and unified image. A core release does not automatically publish
a new adapter version; compatibility CI determines whether an adapter update is necessary.

## 10. Container version alignment

- The image label `org.opencontainers.image.version` equals the Python distribution version.
- `org.opencontainers.image.revision` records the release commit.
- The image contains the exact released wheel and records its SHA-256 digest.
- `signal-generator --version` inside the image matches the image tag.
- The unified adapter image records adapter, simulator-client, and SignalGenerator versions. The
  provider image does not include SignalGenerator or the adapter.

## 11. Release failure and rollback

- A bad Python release is yanked rather than silently overwritten; versions are immutable.
- A fixed package receives a new patch version.
- Container tags are never mutated to hide a faulty immutable version; moving tags may be rolled
  back while the incident is documented.
- The previous compatibility matrix remains available.
- If an adapter release is incompatible, withdraw that adapter version or disable its supervised or
  unified runtime mode and document the affected version combination.

## 12. Release evidence

Each release retains:

- test, coverage, complexity, and security reports,
- wheel/source manifests and clean-install logs,
- standalone and embedded E2E results,
- SBOMs, provenance, signatures, and checksums,
- dependency lock and build-tool versions,
- compatibility matrix for SignalGenerator, adapter, Python, Quart, `opamp-consumer`, and
  `opamp-consumer-sim`.

