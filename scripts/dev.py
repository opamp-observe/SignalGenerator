# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Run common local development checks through one cross-platform command."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
PHASE5_COMPOSE = REPOSITORY_ROOT / "tests" / "test-containers" / "phase5" / "compose.yaml"
PHASE5_VERIFY = REPOSITORY_ROOT / "tests" / "test-containers" / "phase5" / "verify.py"
OTEL_COMPOSE = REPOSITORY_ROOT / "tests" / "test-containers" / "otel-replay" / "compose.yaml"
OTEL_VERIFY = REPOSITORY_ROOT / "tests" / "test-containers" / "otel-replay" / "verify.py"
TASKS = ("unit", "containers", "audit", "pylint", "renovate")


@dataclass(frozen=True, slots=True)
class ContainerScenario:
    """Commands and project identity for one isolated Compose verification."""

    name: str
    compose_file: Path
    profile: str | None
    verifier_arguments: tuple[str, ...]


def _parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse selected checks and optional unified-container controls."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tasks",
        nargs="*",
        choices=(*TASKS, "all"),
        default=["all"],
        help="checks to run; defaults to all",
    )
    parser.add_argument(
        "--include-unified",
        action="store_true",
        help="include the OpAMP unified container scenario",
    )
    parser.add_argument(
        "--opamp-core-context",
        type=Path,
        default=REPOSITORY_ROOT.parent / "opamp2",
        help="companion opamp-core checkout used by the unified scenario",
    )
    return parser.parse_args(arguments)


def _run(command: list[str], *, cwd: Path = REPOSITORY_ROOT) -> int:
    """Run one argument-safe command with live output and return its status."""

    print(f"Running: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=cwd, check=False)  # noqa: S603
    return completed.returncode


def _python_module(module: str, *arguments: str) -> int:
    """Run a module with the active project interpreter."""

    return _run([sys.executable, "-m", module, *arguments])


def _unit_tests(_options: argparse.Namespace) -> int:
    """Run fast unit tests without applying repository-wide coverage thresholds."""

    return _python_module("pytest", "-q", "--no-cov", "tests/unit")


def _dependency_audit(_options: argparse.Namespace) -> int:
    """Audit the core runtime dependency graph declared by this project."""

    return _python_module("pip_audit", ".", "--progress-spinner", "off")


def _pylint(_options: argparse.Namespace) -> int:
    """Run Pylint against the core distribution."""

    return _python_module("pylint", "src/signal_generator")


def _renovate(_options: argparse.Namespace) -> int:
    """Run Renovate in dry-run mode when its executable is installed."""

    executable = shutil.which("renovate")
    if executable is None:
        print("Skipping Renovate: executable is not available on PATH", flush=True)
        return 0
    return _run(
        [
            executable,
            "--platform=local",
            "--dry-run=lookup",
            "--onboarding=false",
            "--require-config=optional",
        ]
    )


def _container_tests(options: argparse.Namespace) -> int:
    """Run isolated pull, push, OTLP, and optionally unified container scenarios."""

    scenarios = [
        ContainerScenario("pull", PHASE5_COMPOSE, "pull", (str(PHASE5_VERIFY), "pull")),
        ContainerScenario("push", PHASE5_COMPOSE, "push", (str(PHASE5_VERIFY), "push")),
        ContainerScenario("otel", OTEL_COMPOSE, None, (str(OTEL_VERIFY),)),
    ]
    if options.include_unified:
        scenarios.append(
            ContainerScenario(
                "unified", PHASE5_COMPOSE, "unified", (str(PHASE5_VERIFY), "unified")
            )
        )
    failures = [
        scenario.name
        for scenario in scenarios
        if _run_container_scenario(scenario, options.opamp_core_context)
    ]
    if failures:
        print(f"Failed container scenarios: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


def _run_container_scenario(scenario: ContainerScenario, opamp_context: Path) -> int:
    """Start, verify, and always tear down one Compose scenario."""

    base = [
        "docker",
        "compose",
        "-p",
        f"signal-generator-dev-{scenario.name}",
        "-f",
        str(scenario.compose_file),
    ]
    profile = ["--profile", scenario.profile] if scenario.profile else []
    environment = None
    if scenario.name == "unified":
        environment = {"OPAMP_CORE_CONTEXT": str(opamp_context.resolve())}
    try:
        status = _run_with_environment(
            [*base, *profile, "up", "--build", "--detach", "--wait"], environment
        )
        if status:
            return status
        return _run([sys.executable, *scenario.verifier_arguments])
    finally:
        _run_with_environment(
            [*base, *profile, "down", "--remove-orphans", "--volumes"], environment
        )


def _run_with_environment(command: list[str], overrides: dict[str, str] | None) -> int:
    """Run a command with optional environment additions used by unified Compose."""

    if not overrides:
        return _run(command)
    environment = os.environ.copy()
    environment.update(overrides)
    print(f"Running: {' '.join(command)}", flush=True)
    completed = subprocess.run(  # noqa: S603
        command, cwd=REPOSITORY_ROOT, check=False, env=environment
    )
    return completed.returncode


RUNNERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "unit": _unit_tests,
    "containers": _container_tests,
    "audit": _dependency_audit,
    "pylint": _pylint,
    "renovate": _renovate,
}


def main(arguments: Sequence[str] | None = None) -> int:
    """Run selected tasks in stable order and report every failed task."""

    options = _parse_arguments(arguments)
    selected = TASKS if "all" in options.tasks else tuple(dict.fromkeys(options.tasks))
    failures: list[str] = []
    for task in selected:
        print(f"\n== {task} ==", flush=True)
        if RUNNERS[task](options):
            failures.append(task)
    if failures:
        print(f"Development checks failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("Development checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

