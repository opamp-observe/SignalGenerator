# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Unified one-process Quart lifecycle and replay isolation tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from signal_generator_opamp_sim.quart_app import EXTENSION_KEY, create_app


@dataclass(frozen=True)
class FakeHealth:
    """Passive fake instance health matching the generic dependency contract."""

    name: str
    running: bool
    ready: bool
    restart_count: int
    last_error: str | None = None


class FakeSimulator:
    """Record unified lifecycle calls without connecting to an OpAMP provider."""

    created: list[FakeSimulator] = []

    def __init__(self, config) -> None:
        """Retain generic config and initialize stopped state."""

        self.config = config
        self.running = False
        self.stopped = False
        self.created.append(self)

    async def start(self) -> None:
        """Record in-process startup."""

        self.running = True

    async def stop(self) -> None:
        """Record awaited in-process shutdown."""

        self.running = False
        self.stopped = True

    def health(self) -> FakeHealth:
        """Return passive readiness without network access."""

        return FakeHealth(self.config.name, self.running, self.running, 0)


def _write_json(path: Path, document: object) -> None:
    """Write one JSON fixture."""

    path.write_text(json.dumps(document), encoding="utf-8")


def _create_config(tmp_path: Path) -> Path:
    """Build a two-frame scenario and unified adapter document."""

    frames = tmp_path / "frames.jsonl"
    frame_template = {
        "metrics": [
            {
                "name": "nginx_connections_active",
                "type": "gauge",
                "help": "Active NGINX connections.",
                "samples": [{"labels": {"instance": "demo"}, "value": 0}],
            }
        ]
    }
    first = dict(frame_template, frame=1)
    second = json.loads(json.dumps(dict(frame_template, frame=2)))
    second["metrics"][0]["samples"][0]["value"] = 7
    frames.write_text(f"{json.dumps(first)}\n{json.dumps(second)}\n", encoding="utf-8")
    _write_json(
        tmp_path / "signal.json",
        {
            "schema_version": 1,
            "metrics": {
                "enabled": True,
                "source": {"path": "frames.jsonl", "eof": "loop"},
                "pull": {"enabled": True, "path": "/metrics"},
                "push": {"enabled": False},
            },
        },
    )
    _write_json(tmp_path / "consumer.json", {"consumer": {"server_url": "http://provider"}})
    _write_json(tmp_path / "responses.json", {"responses": {"*": ["accept"]}})
    adapter = tmp_path / "adapter.json"
    _write_json(
        adapter,
        {
            "schema_version": 1,
            "mode": "unified_quart",
            "quart": {"host": "127.0.0.1", "port": 9108, "workers": 1},
            "signal_generator_runtimes": [
                {"id": "nginx", "config_path": "signal.json", "route_prefix": "/signals/nginx"}
            ],
            "instances": [
                {
                    "name": "sim-a",
                    "consumer_config_path": "consumer.json",
                    "responses_path": "responses.json",
                    "signal_generator_runtime": "nginx",
                    "identity": {"service_instance_uid": "sim-a"},
                }
            ],
        },
    )
    return adapter


@pytest.mark.asyncio
async def test_unified_routes_lifecycle_and_non_consuming_health(tmp_path: Path, monkeypatch) -> None:
    """One app owns all tasks; health does not consume the first NGINX metric frame."""

    monkeypatch.setenv("APP_ENABLE_DEV_FEATURES", "true")
    FakeSimulator.created.clear()
    app = create_app(_create_config(tmp_path), simulator_factory=FakeSimulator)
    async with app.test_app():
        client = app.test_client()
        health = await client.get("/healthz")
        assert health.status_code == 200
        ready = await client.get("/readyz")
        assert ready.status_code == 200
        first = await (await client.get("/signals/nginx/metrics")).get_data(as_text=True)
        second = await (await client.get("/signals/nginx/metrics")).get_data(as_text=True)
        assert 'nginx_connections_active{instance="demo"} 0.0' in first
        assert 'nginx_connections_active{instance="demo"} 7.0' in second
        controller = app.extensions[EXTENSION_KEY]
        assert controller.ready()
    assert FakeSimulator.created[0].stopped
    assert not app.extensions[EXTENSION_KEY].runtimes["nginx"].health().running


def test_unified_mode_requires_explicit_dev_gate(tmp_path: Path, monkeypatch) -> None:
    """The adapter fails before constructing Quart state when the simulator gate is absent."""

    monkeypatch.delenv("APP_ENABLE_DEV_FEATURES", raising=False)
    with pytest.raises(RuntimeError, match="APP_ENABLE_DEV_FEATURES"):
        create_app(_create_config(tmp_path), simulator_factory=FakeSimulator)
