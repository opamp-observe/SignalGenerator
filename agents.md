# SignalGenerator agent guide

## Purpose and scope

This file is the working contract for coding agents operating in `SignalGenerator-Python`. It is
specific to this repository; it is not inherited from `opamp-observe/opamp-core`.

The repository contains two Python distributions:

- `signal-generator` at the repository root; and
- `signal-generator-opamp-sim` under `integrations/opamp-simulator`.

The adjacent `opamp-observe/opamp-core` checkout is an external dependency used by adapter and
unified-mode development. Do not edit that checkout unless the user explicitly includes it in the
task. SignalGenerator-specific code must never be added to the generic OpAMP consumer core or the
OpAMP provider.

## Recommended Cortex workspace setup

Use the repository root as the Cortex/Codex workspace and keep the companion OpAMP checkout beside
it:

```text
dev/
  SignalGenerator-Python/
  opamp2/                 # opamp-observe/opamp-core checkout
```

Configure the IDE and agent terminal to use the project environment:

- Windows interpreter: `.venv/Scripts/python.exe`
- POSIX interpreter: `.venv/bin/python`
- workspace file: `SignalGenerator-Python.code-workspace`
- default working directory: the `SignalGenerator-Python` repository root

Before changing files, an agent should:

1. read this file completely;
2. inspect `git status --short` and preserve unrelated user changes;
3. read [docs/index.md](docs/index.md), then the design or operational document relevant to the
   task;
4. use the existing `.venv` rather than creating another environment; and
5. identify whether the change affects the core distribution, the adapter distribution, or both.

For a fresh checkout, follow [docs/development_setup.md](docs/development_setup.md). On PowerShell,
the expected bootstrap is:

```text
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install -e "..\opamp2\consumer"
python -m pip install -e ".\integrations\opamp-simulator[dev]"
```

Do not assume that global `python`, `pytest`, or other global tools resolve to this environment. Use
the activated environment or invoke `.venv/Scripts/python.exe -m <tool>` explicitly.

## Repository map

| Path | Responsibility |
|---|---|
| `src/signal_generator` | Core configuration, log replay, metric replay, runtime, and optional Quart attachment |
| `integrations/opamp-simulator` | Independently built OpAMP simulator adapter and unified Quart composition |
| `tests` | Core unit, contract, integration, and container tests |
| `examples` | Validated scenarios and NGINX demonstration data |
| `scripts` | Startup, quality, security, benchmark, regression, and release utilities |
| `docs` | Accepted design, user/developer guidance, release process, verification, and roadmap |
| `.github/workflows` | Quality, cloud regression, and signed release automation |

`pyproject.toml` is the core metadata and tool-configuration source of truth. The adapter owns a
separate `integrations/opamp-simulator/pyproject.toml`. Review both whenever a dependency, supported
Python version, test tool, build rule, or release contract changes across distributions.

## Architecture contracts

- Keep the core runtime independent of its HTTP host. Quart remains an optional attachment.
- Keep the OpAMP adapter independently buildable and versioned. It may depend on published core and
  OpAMP APIs; neither dependency may import the adapter.
- Never implement SignalGenerator as an OpAMP provider deployment mode.
- Health, readiness, and discovery routes must not advance metric frames.
- Pull and push cursors are independent unless a future roadmap item explicitly changes that rule.
- A failed push retry reuses the same frame; only a successful push advances its cursor.
- Resolve relative configuration and data paths relative to the configuration file, not the process
  working directory.
- Treat JSON schemas, typed models, validation, examples, and documentation as one contract. Change
  and test them together.
- Preserve deterministic ordering and use injectable clocks for scheduling tests; do not add
  sleep-based timing tests.
- Keep the base package usable without Quart or OpAMP dependencies.
- Public-library support is not implied by importing internal modules. Until roadmap item SG-018 is
  complete, only names explicitly exported from `signal_generator` are a compatibility promise.

## Coding standards

- Add the repository Apache 2.0 header with `Copyright 2026 opamp.info` to new, non-generated Python
  source files. Use `license.txt` as the licence reference.
- Use descriptive names; do not introduce single-letter variables.
- Give modules, public classes, public methods, and non-obvious internal operations useful
  docstrings that explain purpose, parameters, return values, and important lifecycle behavior.
- Describe class attributes when their meaning or ownership is not evident from their type.
- Prefer named constants or enums for protocol keys, structured payload keys, endpoint paths, and
  repeated policy values. Avoid unexplained magic numbers and strings.
- Keep imports sorted and code compatible with the Python versions declared in `pyproject.toml`.
- Keep functions at McCabe complexity 10 or lower and Radon grade B or better; module/package
  averages must remain grade A.
- Preserve async cancellation and deterministic cleanup. Await owned tasks and close transports,
  servers, and clients in reverse ownership order.
- Do not log secrets, bearer tokens, basic-auth passwords, received scenario contents, or unredacted
  effective configuration.
- Markdown filenames use lowercase snake_case. Link planned or deferred work to
  [docs/roadmap.md](docs/roadmap.md) rather than creating a second future-work list.

## Configuration and extension changes

For every configuration field, update the relevant schema, typed model, loader/validator,
redaction, effective-configuration output, documentation, and tests. Unknown fields remain rejected
in normal strict operation. Environment overrides, where supported, take precedence over file
configuration and must be documented and tested.

Third-party log outputs use the `signal_generator.log_outputs` entry-point group. The OpAMP adapter
uses `opamp_consumer.plugins`. Test extension discovery from an installed wheel, not only from an
editable checkout.

When adding a public API, export it deliberately through `__all__`, type it, document lifecycle and
compatibility expectations, and add installed-wheel contract tests. Do not turn a CLI helper into a
public API if it prints, exits the process, installs signal handlers, or mutates global logging.

## Testing and quality gates

Run the narrowest relevant tests while iterating, then run the complete gate for changes affecting
contracts, packaging, configuration, shared runtime behavior, the adapter, or releases.

Core checks:

```text
python -m ruff check src tests scripts
python -m pylint src/signal_generator
python -m pytest -q
python -m xenon --max-absolute B --max-modules A --max-average A src/signal_generator
```

Adapter checks:

```text
cd integrations/opamp-simulator
python -m ruff check src tests
python -m pylint src/signal_generator_opamp_sim
python -m pytest -q
python -m xenon --max-absolute B --max-modules A --max-average A src/signal_generator_opamp_sim
```

Repository-wide pre-package gate:

```text
python scripts/security_checks.py
```

The full gate covers both distributions, branch coverage, Ruff, Pylint, cyclomatic complexity, and
dependency auditing. Core and adapter branch coverage must each remain at least 90%. Add unit tests
for behavior, contract tests for schemas/packages, integration tests for real boundaries, and
container tests when process or protocol composition changes.

For release-affecting changes, also build both distributions and validate their metadata:

```text
python -m build --outdir dist/core .
python -m build --outdir dist/adapter integrations/opamp-simulator
python -m twine check dist/core/* dist/adapter/*
```

Use `python scripts/run_regression.py --profile all --opamp-core-context ../opamp2` for changes that
affect pull, push, containers, Quart composition, or the OpAMP adapter.

## Agent change workflow

1. Establish the current behavior from source and tests; do not rely on an old design claim alone.
2. State any material assumption before it changes scope or architecture.
3. Make focused edits and do not overwrite unrelated dirty-worktree content.
4. Add or update tests with implementation changes.
5. Keep schemas, examples, docs, package metadata, and automation synchronized.
6. Run targeted checks, then the proportional complete gate.
7. Inspect `git diff --check`, `git diff`, and `git status --short` before handing work back.
8. Report what changed, exact verification results, known limitations, and roadmap follow-ups.

Do not commit, tag, publish, push, delete material data, or change the adjacent OpAMP checkout unless
the user explicitly requests that action. Repository release publication follows
[docs/release_process.md](docs/release_process.md) and must originate from reviewed signed tags.

## Completion checklist

A change is ready only when:

- behavior and repository boundaries match the accepted design;
- relevant tests pass and coverage/complexity thresholds remain satisfied;
- configuration and packaging contracts are synchronized;
- user and developer instructions remain accurate;
- future work has one owned roadmap entry; and
- the final report distinguishes implemented behavior from proposals or external release setup.
