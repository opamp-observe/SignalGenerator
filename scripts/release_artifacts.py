# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Create deterministic SHA-256 and JSON manifests for release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ARTIFACT_SUFFIXES = (".whl", ".tar.gz", ".spdx.json", ".cdx.json", ".intoto.jsonl")
KEY_ARTIFACTS = "artifacts"
KEY_NAME = "name"
KEY_SHA256 = "sha256"
KEY_SIZE = "size"
KEY_SCHEMA_VERSION = "schema_version"
KEY_SOURCE_DATE_EPOCH = "source_date_epoch"
MANIFEST_SCHEMA_VERSION = 1


def create_release_evidence(artifact_directories: list[Path], output_directory: Path) -> dict[str, Any]:
    """Hash unique release artifacts and write machine- and human-readable manifests."""

    artifacts = _discover_artifacts(artifact_directories)
    if not artifacts:
        raise ValueError("no release artifacts found")
    output_directory.mkdir(parents=True, exist_ok=True)
    records = [_artifact_record(path) for path in artifacts]
    manifest = {
        KEY_SCHEMA_VERSION: MANIFEST_SCHEMA_VERSION,
        KEY_SOURCE_DATE_EPOCH: os.environ.get("SOURCE_DATE_EPOCH"),
        KEY_ARTIFACTS: records,
    }
    checksum_lines = [f"{record[KEY_SHA256]}  {record[KEY_NAME]}" for record in records]
    (output_directory / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n"
    )
    (output_directory / "release_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def _discover_artifacts(artifact_directories: list[Path]) -> list[Path]:
    """Return a stable artifact list while rejecting ambiguous duplicate file names."""

    files = sorted(
        (
            path
            for directory in artifact_directories
            for path in directory.rglob("*")
            if path.is_file() and path.name.endswith(ARTIFACT_SUFFIXES)
        ),
        key=lambda path: path.name,
    )
    names = [path.name for path in files]
    if len(names) != len(set(names)):
        raise ValueError("release artifact file names must be unique")
    return files


def _artifact_record(path: Path) -> dict[str, Any]:
    """Return one artifact's immutable release identity."""

    digest = hashlib.sha256()
    with path.open("rb") as artifact_file:
        for block in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(block)
    return {KEY_NAME: path.name, KEY_SHA256: digest.hexdigest(), KEY_SIZE: path.stat().st_size}


def main(arguments: list[str] | None = None) -> int:
    """Parse artifact directories and write release evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_directories", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=Path("release-evidence"))
    options = parser.parse_args(arguments)
    try:
        create_release_evidence(options.artifact_directories, options.output)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
