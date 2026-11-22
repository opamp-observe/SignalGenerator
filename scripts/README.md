# Startup scripts

The startup scripts run SignalGenerator from this project's `.venv`, set unbuffered Python output,
default `SIGNAL_GENERATOR_LOG_LEVEL` to `DEBUG`, and pass all arguments to
`python -m signal_generator run`. Existing environment-variable values are preserved.

The scripts do not create or modify the environment. Before first use, create the virtual
environment and install the project:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

On POSIX platforms, use `.venv/bin/python` in the installation command.

## PowerShell

```powershell
.\scripts\start_signal_generator.ps1 --config .\examples\nginx\config.json
```

## Windows Command Prompt

```bat
scripts\start_signal_generator.cmd --config examples\nginx\config.json
```

The CMD launcher is independent of PowerShell.

## Bash

```bash
./scripts/start_signal_generator.sh --config ./examples/nginx/config.json
```

The Bash launcher supports POSIX virtual environments and Windows virtual environments when run
from Git Bash. Each launcher preserves the SignalGenerator process exit code and resolves paths
relative to its own location, so it may be invoked from another working directory.

These launchers are for the standalone deployment. The separately packaged OpAMP adapter owns its
own supervised and unified startup commands.

## Developer check CLI

Use the active project interpreter to run the common local gates:

```text
python scripts/dev.py
python scripts/dev.py unit pylint audit renovate
python scripts/dev.py containers
python scripts/dev.py containers --include-unified
```

With no task arguments, the command runs unit tests, the pull/push/OTLP container scenarios,
`pip-audit`, Pylint, and a Renovate dry run in that order. Renovate is optional: when its executable
is not on `PATH`, the task reports a successful skip. The unified OpAMP container is excluded by
default because it is the heavier profile and exercises composite APIs. Every Compose scenario
uses an isolated project name and is torn down even after startup or verification failure.
The unified build uses the pinned upstream `opamp-core` v0.6 BuildKit Git context by default. Use
`--opamp-core-context PATH_OR_GIT_URL` only to test a different checkout or revision.
