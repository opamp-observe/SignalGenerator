# Development setup

## Prerequisites

Install:

- Git;
- Python 3.10–3.13 (3.13 is the release-CI version);
- Docker Engine or Docker Desktop with Compose v2 and Buildx; and
- optionally `uv` for resolving the checked-in `uv.lock`.

For adapter and unified-mode development, clone the OpAMP core repository beside this repository:

```text
dev/
  SignalGenerator-Python/
  opamp2/                 # clone of opamp-observe/opamp-core
```

The directory may have another name when `--opamp-core-context` or `OPAMP_CORE_CONTEXT` is supplied.

## Create the project environment

From `SignalGenerator-Python`:

```text
# PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install -e "..\opamp2\consumer" -e "..\opamp2\consumer-sim"
python -m pip install -e ".\integrations\opamp-simulator[dev]"

# Bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install -e ../opamp2/consumer -e ../opamp2/consumer-sim
python -m pip install -e "./integrations/opamp-simulator[dev]"
```

Confirm the environment:

```text
python -m pip check
signal-generator --version
signal-generator-opamp-sim --version
```

`pyproject.toml` is the source of truth. `uv.lock` locks the complete core development resolution;
the adapter owns its separate compatibility lock and TOML metadata.

## Repository layout

| Path | Ownership |
|---|---|
| `src/signal_generator` | Core configuration, logs, metrics, runtime, and Quart attachment |
| `integrations/opamp-simulator` | Independently built OpAMP adapter |
| `examples` | Validated log, metric, and adapter scenarios |
| `tests` | Unit, contract, integration, and container tests |
| `scripts` | Startup, security, benchmark, release, and regression utilities |
| `docs` | Design, operation, development, security, and release contracts |

Only generic simulator-client APIs belong in `opamp-observe/opamp-core`. SignalGenerator-specific
logic remains in the adapter. Do not add the feature to the OpAMP provider.

## Daily development commands

```text
python -m ruff check src tests scripts
python -m pylint src/signal_generator
python -m pytest -q
python -m xenon --max-absolute B --max-modules A --max-average A src/signal_generator

cd integrations/opamp-simulator
python -m ruff check src tests
python -m pylint src/signal_generator_opamp_sim
python -m pytest -q
python -m xenon --max-absolute B --max-modules A --max-average A src/signal_generator_opamp_sim
```

The complete pre-package gate is:

```text
python scripts/security_checks.py
```

It covers both distributions, branch coverage, cyclomatic complexity, source-security rules, and
dependency auditing. Functions may be no worse than Radon B/McCabe 10, while module and package
averages must remain A. Core branch coverage must remain at least 90%.

## Build and smoke-test distributions

```text
python -m build --outdir dist/core .
python -m build --outdir dist/adapter integrations/opamp-simulator
python -m twine check dist/core/* dist/adapter/*
python scripts/release_artifacts.py dist/core dist/adapter --output dist/evidence
```

Install the built wheels into a fresh virtual environment. Verify that the base adapter discovers
the `opamp_consumer.plugins` entry point without installing Quart, then install its `unified` extra
and import `signal_generator_opamp_sim.quart_app`.

## Container and regression development

Run all profiles sequentially:

```text
python scripts/check_cloud_runner.py --cloud aws
python scripts/run_regression.py --profile all --opamp-core-context ../opamp2
```

The prerequisite checker is read-only; `--cloud` records the intended runner type. The regression
script scopes each Compose project by profile, emits a JSON report, captures service logs on
failure, and tears down in a `finally` path.

## AWS and Azure GitHub regression runners

`.github/workflows/cloud_regression.yml` is manually dispatched from GitHub Actions. It selects a
self-hosted Linux runner with all of these labels:

- `self-hosted`
- `linux`
- `signal-generator-regression`
- either `aws` or `azure`

Use an ephemeral EC2 instance/Auto Scaling runner for AWS or an ephemeral Azure VM/VM Scale Set
runner for Azure. Recommended minimums are 4 vCPU, 8 GiB RAM, and 30 GiB free storage. Install the
GitHub runner, Python, Docker Engine, Compose v2, and Buildx; allow outbound HTTPS and container
registry access, but no inbound application ports. Give the runner identity only repository-read
access. The regression itself requires no cloud API credentials.

In GitHub:

1. Open **Actions → cloud regression → Run workflow**.
2. Choose `aws` or `azure`, the source ref, and `all` or one profile.
3. Approve the matching `cloud-regression-aws` or `cloud-regression-azure` environment.
4. Download the JSON evidence artifact after completion.

The workflow checks out this repository plus `opamp-observe/opamp-core`, verifies runner capacity,
runs the selected profiles, uploads reports even on failure, and performs a final scoped cleanup.
Configure the cloud runner group so only this repository and protected workflow can target it.

## Contribution and release

Preserve unrelated working-tree changes, add tests with implementation changes, keep schemas and
examples synchronized, and update roadmap documentation whenever release notes defer work. See
[CONTRIBUTING.md](../CONTRIBUTING.md) and the [release process](release_process.md).
