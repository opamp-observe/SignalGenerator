# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Shared test fixtures for configuration and replay scenarios."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def log_config_factory(tmp_path: Path):
    """Return a helper that writes a minimal valid log configuration and source file."""

    def create(overrides: dict | None = None) -> Path:
        """Create one scenario under the test temporary directory."""

        source_path = tmp_path / "events.txt"
        source_path.write_text("+0 first\n+100 second\n", encoding="utf-8")
        document = {
            "schema_version": 1,
            "logs": {
                "enabled": True,
                "source": {"path": "events.txt", "format": "%t %m"},
                "format": "%m:%i:%j",
                "replay": {"cycles": 1, "default_interval_ms": 0},
                "outputs": [{"type": "stdout"}],
            },
        }
        if overrides:
            _deep_update(document, overrides)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(document), encoding="utf-8")
        return config_path

    return create


def _deep_update(target: dict, update: dict) -> None:
    """Recursively apply nested test overrides without mutating shared fixture data."""

    for key, value in update.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
