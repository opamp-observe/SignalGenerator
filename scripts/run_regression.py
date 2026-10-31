# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Run isolated pull, push, and unified container regressions with guaranteed teardown."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ALL_PROFILES = ("pull", "push", "unified")
CommandRunner = Callable[..., subprocess.CompletedProcess[Any]]
KEY_CLOUD = "cloud"
KEY_PASSED = "passed"
KEY_RESULTS = "results"


@dataclass(frozen=True, slots=True)
class RegressionResult:
    """Record the outcome and duration of one independently isolated Compose profile."""

    profile: str
    passed: bool
    elapsed_seconds: float
    failed_stage: str | None
    return_code: int


def run_regression(
    profiles: tuple[str, ...],
    compose_file: Path,
    verifier: Path,
    opamp_core_context: Path,
    cloud: str,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    """Run requested profiles sequentially so fixed demo ports never collide."""

    invalid_profiles = sorted(set(profiles) - set(ALL_PROFILES))
    if invalid_profiles:
        raise ValueError(f"unsupported regression profiles: {', '.join(invalid_profiles)}")
    environment = os.environ.copy()
    environment["OPAMP_CORE_CONTEXT"] = str(opamp_core_context.resolve())
    results = [
        _run_profile(profile, compose_file, verifier, environment, command_runner)
        for profile in profiles
    ]
    return {
        KEY_CLOUD: cloud,
        KEY_RESULTS: [asdict(result) for result in results],
        KEY_PASSED: all(result.passed for result in results),
    }


def _run_profile(
    profile: str,
    compose_file: Path,
    verifier: Path,
    environment: dict[str, str],
    command_runner: CommandRunner,
) -> RegressionResult:
    """Start, verify, diagnose, and always tear down one scoped Compose project."""

    project_name = f"signal-generator-regression-{profile}"
    base_command = ["docker", "compose", "-p", project_name, "-f", str(compose_file)]
    started = time.perf_counter()
    failed_stage: str | None = None
    return_code = 0
    try:
        up_result = _run(
            [*base_command, "--profile", profile, "up", "--build", "--detach", "--wait"],
            environment,
            command_runner,
        )
        if up_result.returncode:
            failed_stage, return_code = "startup", up_result.returncode
        else:
            verify_result = _run(
                [sys.executable, str(verifier), profile], environment, command_runner
            )
            if verify_result.returncode:
                failed_stage, return_code = "verification", verify_result.returncode
        if failed_stage:
            _run([*base_command, "--profile", profile, "logs", "--no-color"], environment, command_runner)
    finally:
        down_result = _run(
            [*base_command, "--profile", profile, "down", "--remove-orphans", "--volumes"],
            environment,
            command_runner,
        )
        if down_result.returncode and failed_stage is None:
            failed_stage, return_code = "teardown", down_result.returncode
    elapsed = round(time.perf_counter() - started, 3)
    return RegressionResult(profile, failed_stage is None, elapsed, failed_stage, return_code)


def _run(
    command: list[str], environment: dict[str, str], command_runner: CommandRunner
) -> subprocess.CompletedProcess[Any]:
    """Run a fixed regression command with live logs and no shell interpolation."""

    print(f"Running: {' '.join(command)}", flush=True)
    return command_runner(command, check=False, env=environment)


def main(arguments: list[str] | None = None) -> int:
    """Parse suite selection, run profiles, and retain a JSON summary."""

    repository_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=(*ALL_PROFILES, "all"), default="all")
    parser.add_argument("--cloud", choices=("local", "aws", "azure"), default="local")
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=repository_root / "tests" / "test-containers" / "phase5" / "compose.yaml",
    )
    parser.add_argument(
        "--verifier",
        type=Path,
        default=repository_root / "tests" / "test-containers" / "phase5" / "verify.py",
    )
    parser.add_argument(
        "--opamp-core-context", type=Path, default=repository_root.parent / "opamp2"
    )
    parser.add_argument("--output", type=Path, default=repository_root / "test-results" / "regression.json")
    options = parser.parse_args(arguments)
    profiles = ALL_PROFILES if options.profile == "all" else (options.profile,)
    result = run_regression(
        profiles,
        options.compose_file.resolve(),
        options.verifier.resolve(),
        options.opamp_core_context,
        options.cloud,
    )
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result[KEY_PASSED] else 1


if __name__ == "__main__":
    raise SystemExit(main())
