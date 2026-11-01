# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Protect performance evidence and immutable release-manifest contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts.benchmark_replay import (
    KEY_FRAME_COUNT,
    KEY_LOAD_FRAMES_PER_SECOND,
    KEY_PEAK_BYTES_PER_FRAME,
    KEY_RENDER_FRAMES_PER_SECOND,
    run_benchmark,
)
from scripts.release_artifacts import KEY_ARTIFACTS, create_release_evidence
from scripts.run_regression import KEY_PASSED, KEY_RESULTS, run_regression


def test_small_benchmark_measures_all_release_limits() -> None:
    """The benchmark must exercise both loading and rendering and report peak allocation."""

    result = run_benchmark(frame_count=3, iterations=1)
    assert result[KEY_FRAME_COUNT] == 3
    assert result[KEY_LOAD_FRAMES_PER_SECOND] > 0
    assert result[KEY_RENDER_FRAMES_PER_SECOND] > 0
    assert result[KEY_PEAK_BYTES_PER_FRAME] > 0


def test_release_evidence_is_stable_and_rejects_duplicate_names(tmp_path: Path) -> None:
    """Release checksums must be sorted, verifiable, and unambiguous after download."""

    wheel_directory = tmp_path / "wheel"
    source_directory = tmp_path / "source"
    output_directory = tmp_path / "evidence"
    wheel_directory.mkdir()
    source_directory.mkdir()
    (wheel_directory / "example-1.0.whl").write_bytes(b"wheel")
    (source_directory / "example-1.0.tar.gz").write_bytes(b"source")

    manifest = create_release_evidence(
        [source_directory, wheel_directory], output_directory=output_directory
    )
    names = [record["name"] for record in manifest[KEY_ARTIFACTS]]
    assert names == sorted(names)
    persisted = json.loads((output_directory / "release_manifest.json").read_text("utf-8"))
    assert persisted == manifest
    assert (output_directory / "SHA256SUMS").read_text("utf-8").count("\n") == 2

    duplicate_directory = tmp_path / "duplicate"
    duplicate_directory.mkdir()
    (duplicate_directory / "example-1.0.whl").write_bytes(b"different")
    with pytest.raises(ValueError, match="unique"):
        create_release_evidence(
            [wheel_directory, duplicate_directory], output_directory=output_directory
        )


def test_release_workflow_contains_required_supply_chain_controls() -> None:
    """The release workflow must retain signed-tag, scan, SBOM, provenance, and OIDC gates."""

    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    required_fragments = (
        "verify-tag",
        "pypa/gh-action-pypi-publish@release/v1",
        "aquasecurity/trivy-action@v0.36.0",
        "anchore/sbom-action@v0",
        "actions/attest@v4",
        "sigstore/cosign-installer@v4.1.2",
        "SHA256SUMS",
    )
    assert all(fragment in workflow for fragment in required_fragments)


def test_regression_runner_always_tears_down_and_records_failure(tmp_path: Path) -> None:
    """A failed profile must collect logs, tear down, and produce a failed result."""

    commands: list[list[str]] = []

    def command_runner(
        command: list[str], **_options: object
    ) -> subprocess.CompletedProcess[bytes]:
        """Fail startup while recording each shell-free command."""

        commands.append(command)
        return_code = 7 if "up" in command else 0
        return subprocess.CompletedProcess(command, return_code)

    result = run_regression(
        ("pull",),
        tmp_path / "compose.yaml",
        tmp_path / "verify.py",
        tmp_path / "opamp-core",
        "aws",
        command_runner,
    )
    assert not result[KEY_PASSED]
    assert result[KEY_RESULTS][0]["failed_stage"] == "startup"
    assert any("logs" in command for command in commands)
    assert "down" in commands[-1]


def test_cloud_workflow_selects_protected_aws_or_azure_runner() -> None:
    """Manual cloud regression must route only to the explicit provider runner labels."""

    workflow = Path(".github/workflows/cloud_regression.yml").read_text(encoding="utf-8")
    required_fragments = (
        "workflow_dispatch",
        "signal-generator-regression",
        "options: [aws, azure]",
        "check_cloud_runner.py",
        "run_regression.py",
        "if: always()",
    )
    assert all(fragment in workflow for fragment in required_fragments)


def test_unreleased_opamp_composite_test_is_explicitly_suppressed() -> None:
    """The temporary GitHub control must default closed without hiding supervisor tests."""

    workflow = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")
    testing_guide = Path("docs/testing_and_demo_strategy.md").read_text(encoding="utf-8")
    control = "ENABLE_OPAMP_CORE_SIMULATOR_INTEGRATION_TESTS"

    assert f"vars.{control} == 'true'" in workflow
    assert "python -m pytest -q" in workflow
    assert control in testing_guide
    assert "supervised plugin tests continue to run" in testing_guide


def test_roadmap_is_the_single_future_work_register() -> None:
    """Audit gaps and requested OpAMP file actions must remain explicit in one roadmap."""

    roadmap = Path("docs/roadmap.md").read_text(encoding="utf-8")
    implementation_plan = Path("docs/implementation_plan.md").read_text(encoding="utf-8")
    required_items = (
        "SG-001",
        "SG-002",
        "SG-003",
        "SG-017",
        "SG-018",
        "stage_bundle",
        "validate_bundle",
        "activate_bundle",
        "configuration plus referenced log, metric JSONL",
        "integrations/opamp-simulator",
        "signal-generator-opamp-sim-vX.Y.Z",
        "docs/library_usage.md",
    )
    assert all(item in roadmap for item in required_items)
    assert "## 12. Deferred features" not in implementation_plan
    assert "[roadmap.md](roadmap.md)" in implementation_plan


def test_uml_document_covers_packages_and_deployment_permutations() -> None:
    """The colour-coded UML guide must retain package boundaries and every supported mode."""

    uml_document = Path("docs/uml_architecture.md").read_text(encoding="utf-8")
    required_fragments = (
        "classDiagram",
        'class SignalGeneratorCore["signal-generator"]',
        'class SignalGeneratorAdapter["signal-generator-opamp-sim"]',
        'class OpAMPConsumer["opamp-consumer"]',
        'class OpAMPConsumerSim["opamp-consumer-sim"]',
        "UML deployment diagram: standalone utility",
        "UML deployment diagram: OpAMP-supervised process",
        "UML deployment diagram: unified Quart simulator",
        "style SignalGeneratorCore fill:#dbeafe",
        "style SignalGeneratorAdapter fill:#dcfce7",
        "style OpAMPConsumer fill:#fef3c7",
        "style Quart fill:#f3e8ff",
        "style OpAMPProvider fill:#fee2e2",
        "classDef core fill:#dbeafe",
        "classDef adapter fill:#dcfce7",
        "classDef opamp fill:#fef3c7",
        "classDef thirdParty fill:#f3e8ff",
        "classDef provider fill:#fee2e2",
        "Provider becoming a SignalGenerator deployment mode",
    )
    assert all(fragment in uml_document for fragment in required_fragments)
