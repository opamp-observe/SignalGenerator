# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Run source, quality, complexity, test, and dependency gates before packaging."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ADAPTER_ROOT = REPOSITORY_ROOT / "integrations" / "opamp-simulator"
SCOPE_ALL = "all"
SCOPE_CORE = "core"
CORE_COMMANDS = (
    (REPOSITORY_ROOT, "ruff", "check", "src", "tests", "scripts"),
    (REPOSITORY_ROOT, "pylint", "src/signal_generator"),
    (REPOSITORY_ROOT, "pytest", "-q"),
    (
        REPOSITORY_ROOT,
        "xenon",
        "--max-absolute",
        "B",
        "--max-modules",
        "A",
        "--max-average",
        "A",
        "src/signal_generator",
    ),
)
ADAPTER_COMMANDS = (
    (ADAPTER_ROOT, "ruff", "check", "src", "tests"),
    (ADAPTER_ROOT, "pylint", "src/signal_generator_opamp_sim"),
    (ADAPTER_ROOT, "pytest", "-q"),
    (
        ADAPTER_ROOT,
        "xenon",
        "--max-absolute",
        "B",
        "--max-modules",
        "A",
        "--max-average",
        "A",
        "src/signal_generator_opamp_sim",
    ),
)
AUDIT_COMMANDS = (
    (REPOSITORY_ROOT, "pip_audit", "--progress-spinner", "off", "--skip-editable"),
)


def _parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    """Parse the package scope whose installed dependency set is available."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=(SCOPE_ALL, SCOPE_CORE),
        default=SCOPE_ALL,
        help="run all repository gates or only core gates before the dependency audit",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run selected gates with the current interpreter and stop at the first failure."""

    options = _parse_arguments(arguments)
    commands = CORE_COMMANDS
    if options.scope == SCOPE_ALL:
        commands += ADAPTER_COMMANDS
    commands += AUDIT_COMMANDS

    for working_directory, module_name, *module_arguments in commands:
        command = [sys.executable, "-m", module_name, *module_arguments]
        print(f"Running: {' '.join(command)}", flush=True)
        # Command modules and arguments are the fixed allow-list above, never user input.
        completed = subprocess.run(command, cwd=working_directory, check=False)  # noqa: S603
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
