# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Adapter-owned embeddable lifecycle for one public OpAMP simulator client."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENV_APP_ENABLE_DEV_FEATURES = "APP_ENABLE_DEV_FEATURES"
ENV_OPAMP_CONFIG_PATH = "OPAMP_CONFIG_PATH"
TRUE_VALUES = frozenset({"1", "on", "true", "yes"})
DEFAULT_STATUS_PORT = 1


@dataclass(frozen=True, slots=True)
class SimulatorIdentity:
    """Stable identity overrides applied to a simulator consumer configuration."""

    service_instance_uid: str
    client_version: str = "scripted"
    config_version: str = ""


@dataclass(frozen=True, slots=True)
class SimulatorResponsePlan:
    """Path to the scripted server-response sequence consumed by the client."""

    path: Path


@dataclass(frozen=True, slots=True)
class SimulatorInstanceConfig:
    """Configuration required to construct one embeddable simulator client."""

    name: str
    consumer_config_path: Path
    response_plan: SimulatorResponsePlan
    identity: SimulatorIdentity
    status_port: int = DEFAULT_STATUS_PORT


@dataclass(frozen=True, slots=True)
class SimulatorHealth:
    """Immutable lifecycle and error state used by host readiness aggregation."""

    name: str
    running: bool
    ready: bool
    restart_count: int
    last_error: str | None = None


ConfigLoader = Callable[[Path], Any]
ClientFactory = Callable[[str, Any], Any]


# The instance deliberately owns each injected dependency and lifecycle resource for deterministic
# teardown; collapsing these into an untyped state bag would obscure that ownership.
class SimulatorInstance:  # pylint: disable=too-many-instance-attributes
    """Run a scripted OpAMP client as cancellable tasks on the host event loop."""

    def __init__(
        self,
        config: SimulatorInstanceConfig,
        *,
        environ: Mapping[str, str] | None = None,
        config_loader: ConfigLoader | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        """Create a stopped instance with injectable construction seams."""

        self.config = config
        self._environ = os.environ if environ is None else environ
        self._config_loader = config_loader or _load_consumer_config
        self._client_factory = client_factory or _create_simulator_client
        self._client: Any | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._running = False
        self._ready = False
        self._restart_count = 0
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Connect once, then start the cancellable heartbeat and response loop."""

        async with self._lock:
            if self._running:
                return
            self._require_dev_features()
            try:
                consumer_config = self._build_consumer_config()
                self._client = self._client_factory(
                    str(consumer_config.server_url), consumer_config
                )
                self._client.launch_agent_process()
                self._client.add_agent_version(self.config.status_port)
                await self._client.send()
                self._heartbeat_task = asyncio.create_task(
                    self._client.run_heartbeat_loop(self.config.status_port),
                    name=f"opamp-simulator-{self.config.name}",
                )
            except Exception as error:
                self._last_error = str(error)
                await self._stop_unlocked()
                raise
            self._running = True
            self._ready = True
            self._last_error = None

    def _require_dev_features(self) -> None:
        """Enforce the simulator's explicit development-only startup gate."""

        configured = str(self._environ.get(ENV_APP_ENABLE_DEV_FEATURES, "")).strip().lower()
        if configured not in TRUE_VALUES:
            raise RuntimeError("simulator startup requires APP_ENABLE_DEV_FEATURES=true")

    def _build_consumer_config(self) -> Any:
        """Load consumer settings and apply identity and response-plan controls."""

        consumer_config = self._config_loader(self.config.consumer_config_path)
        consumer_config.service_type = "simulator"
        consumer_config.simulator_responses_path = str(self.config.response_plan.path)
        consumer_config.service_instance_id = self.config.identity.service_instance_uid
        consumer_config.config_version = self.config.identity.config_version
        consumer_config.agent_additional_params = [
            json.dumps(
                {
                    "client_version": self.config.identity.client_version,
                    "config_version": self.config.identity.config_version,
                    "service_instance_uid": self.config.identity.service_instance_uid,
                },
                sort_keys=True,
            )
        ]
        consumer_config.client_status_port = self.config.status_port
        if not consumer_config.server_url:
            raise ValueError("simulator consumer configuration requires server_url")
        return consumer_config

    async def stop(self) -> None:
        """Cancel heartbeat activity, disconnect, and release the client."""

        async with self._lock:
            await self._stop_unlocked()

    async def _stop_unlocked(self) -> None:
        """Stop resources while the lifecycle lock is already held."""

        self._ready = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
        if self._client:
            await self._client.finalize_async()
            self._client.terminate_agent_process()
            self._client = None
        self._running = False

    async def logical_restart(self) -> None:
        """Restart tasks without replacing the hosting process or event loop."""

        await self.stop()
        self._restart_count += 1
        await self.start()

    async def apply_config(self, candidate: SimulatorInstanceConfig) -> None:
        """Atomically apply a candidate and roll back when startup fails."""

        previous = self.config
        was_running = self._running
        if was_running:
            await self.stop()
        self.config = candidate
        self._restart_count += 1
        if not was_running:
            return
        try:
            await self.start()
        except Exception:
            self.config = previous
            await self.start()
            raise

    def health(self) -> SimulatorHealth:
        """Return passive state without network calls or task side effects."""

        task_healthy = self._heartbeat_task is None or not self._heartbeat_task.done()
        return SimulatorHealth(
            self.config.name,
            self._running,
            self._ready and task_healthy,
            self._restart_count,
            self._last_error,
        )


@contextmanager
def _opamp_import_config(path: Path) -> Iterator[None]:
    """Expose an explicit config path while importing the current OpAMP consumer."""

    previous = os.environ.get(ENV_OPAMP_CONFIG_PATH)
    os.environ[ENV_OPAMP_CONFIG_PATH] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(ENV_OPAMP_CONFIG_PATH, None)
        else:
            os.environ[ENV_OPAMP_CONFIG_PATH] = previous


def _load_consumer_config(path: Path) -> Any:
    """Load a consumer configuration through its public explicit-path API."""

    with _opamp_import_config(path):
        from opamp_consumer.config import (  # pylint: disable=import-outside-toplevel
            load_config_with_overrides,
        )

        return load_config_with_overrides(
            config_path=path,
            server_url=None,
            server_port=None,
            agent_config_path=None,
            agent_additional_params=None,
            heartbeat_frequency=None,
            log_level=None,
            full_update_controller=None,
        )


def _create_simulator_client(base_url: str, config: Any) -> Any:
    """Construct the public simulator client after explicit configuration loading."""

    from opamp_consumer.simulator.client import (  # pylint: disable=import-outside-toplevel
        SimulatorOpAMPClient,
    )

    return SimulatorOpAMPClient(base_url, config)
