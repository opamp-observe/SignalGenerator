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
