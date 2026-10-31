# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Verify that an AWS or Azure GitHub runner can execute the container regression suite."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

MINIMUM_CPU_COUNT = 2
MINIMUM_FREE_BYTES = 15 * 1024 * 1024 * 1024
KEY_CHECKS = "checks"
KEY_CLOUD = "cloud"
KEY_MESSAGE = "message"
KEY_NAME = "name"
KEY_PASSED = "passed"


def inspect_runner(cloud: str, workspace: Path) -> dict[str, Any]:
    """Return machine-readable prerequisite results without modifying the cloud runner."""

    checks = [
        _check("python", shutil.which("python") is not None, "python must be on PATH"),
        _check("docker", shutil.which("docker") is not None, "docker must be on PATH"),
        _command_check("docker-compose", ["docker", "compose", "version"]),
        _command_check("docker-buildx", ["docker", "buildx", "version"]),
        _check(
            "cpu",
            (os.cpu_count() or 0) >= MINIMUM_CPU_COUNT,
            f"at least {MINIMUM_CPU_COUNT} logical CPUs are required",
        ),
        _check(
            "disk",
            shutil.disk_usage(workspace).free >= MINIMUM_FREE_BYTES,
            "at least 15 GiB of free workspace storage is required",
        ),
    ]
    return {KEY_CLOUD: cloud, KEY_CHECKS: checks, KEY_PASSED: all(item[KEY_PASSED] for item in checks)}


def _check(name: str, passed: bool, message: str) -> dict[str, str | bool]:
    """Build one stable prerequisite diagnostic."""

    return {KEY_NAME: name, KEY_PASSED: passed, KEY_MESSAGE: "ok" if passed else message}


def _command_check(name: str, command: list[str]) -> dict[str, str | bool]:
    """Run one harmless version command and convert its exit status to a diagnostic."""

    try:
        completed = subprocess.run(  # noqa: S603 - fixed command allow-list from the caller.
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        return _check(name, False, str(error))
    return _check(name, completed.returncode == 0, f"{' '.join(command)} failed")


def main(arguments: list[str] | None = None) -> int:
    """Validate one labeled cloud runner and emit a JSON report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud", choices=("aws", "azure"), required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(arguments)
    result = inspect_runner(options.cloud, options.workspace)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result[KEY_PASSED] else 1


if __name__ == "__main__":
    raise SystemExit(main())
