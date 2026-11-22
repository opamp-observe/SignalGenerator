# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Developer CLI task selection and cleanup tests."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from scripts import dev


def test_main_runs_selected_tasks_once_and_reports_success(monkeypatch, capsys) -> None:
    """Explicit tasks retain order, discard duplicates, and aggregate success."""

    called: list[str] = []
    monkeypatch.setitem(dev.RUNNERS, "unit", lambda _options: called.append("unit") or 0)
    monkeypatch.setitem(dev.RUNNERS, "pylint", lambda _options: called.append("pylint") or 0)
    assert dev.main(["unit", "pylint", "unit"]) == 0
    assert called == ["unit", "pylint"]
    assert "Development checks passed" in capsys.readouterr().out


def test_renovate_is_optional(monkeypatch, capsys) -> None:
    """A machine without Renovate receives an explicit non-failing skip."""

    monkeypatch.setattr(dev.shutil, "which", lambda _name: None)
    assert dev._renovate(Namespace()) == 0  # pylint: disable=protected-access
    assert "Skipping Renovate" in capsys.readouterr().out


def test_container_start_failure_still_tears_down(monkeypatch) -> None:
    """Compose teardown runs even when startup fails before verification."""

    commands: list[list[str]] = []

    def run(command: list[str], _environment: dict[str, str] | None) -> int:
        commands.append(command)
        return 7 if "up" in command else 0

    monkeypatch.setattr(dev, "_run_with_environment", run)
    scenario = dev.ContainerScenario("pull", Path("compose.yaml"), "pull", ("verify.py",))
    assert dev._run_container_scenario(  # pylint: disable=protected-access
        scenario, Path("opamp-core-local")
    ) == 7
    assert "down" in commands[-1]


def test_opamp_build_context_preserves_git_url_and_resolves_local_path(tmp_path: Path) -> None:
    """Unified builds need no adjacent checkout but still accept an explicit local override."""

    remote = "https://github.com/opamp-observe/opamp-core.git#v0.6"
    assert dev._build_context_value(remote) == remote  # pylint: disable=protected-access
    assert dev._build_context_value(tmp_path) == str(  # pylint: disable=protected-access
        tmp_path.resolve()
    )

