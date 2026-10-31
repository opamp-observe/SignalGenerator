# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Run source, quality, complexity, test, and dependency gates before packaging."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ADAPTER_ROOT = REPOSITORY_ROOT / "integrations" / "opamp-simulator"
COMMANDS = (
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
    (REPOSITORY_ROOT, "pip_audit", "--progress-spinner", "off", "--skip-editable"),
)


def main() -> int:
    """Run every gate with the current interpreter and stop at the first failure."""

    for working_directory, module_name, *arguments in COMMANDS:
        command = [sys.executable, "-m", module_name, *arguments]
        print(f"Running: {' '.join(command)}", flush=True)
        # Command modules and arguments are the fixed allow-list above, never user input.
        completed = subprocess.run(command, cwd=working_directory, check=False)  # noqa: S603
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
