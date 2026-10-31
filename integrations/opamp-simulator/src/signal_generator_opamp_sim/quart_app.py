# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Single-process Quart composition using only public dependency lifecycle APIs."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from opamp_consumer_sim import (
    SimulatorIdentity,
    SimulatorInstance,
    SimulatorInstanceConfig,
    SimulatorResponsePlan,
)
from signal_generator.config.loader import load_configuration, load_configuration_mapping
from signal_generator.embedding.quart import attach_signal_generator_runtime
from signal_generator.runtime import SignalGeneratorRuntime

from signal_generator_opamp_sim.config import (  # pylint: disable=wrong-import-order
    AdapterConfig,
    InstanceConfig,
    load_adapter_config,
)

ENV_APP_ENABLE_DEV_FEATURES = "APP_ENABLE_DEV_FEATURES"
EXTENSION_KEY = "signal_generator_opamp_sim.controller"
KEY_ERROR = "error"
KEY_INSTANCES = "instances"
KEY_NAME = "name"
KEY_READY = "ready"
KEY_RESTART_COUNT = "restart_count"
KEY_RUNNING = "running"
KEY_RUNTIMES = "runtimes"
TRUE_VALUES = frozenset({"1", "on", "true", "yes"})
SimulatorFactory = Callable[[SimulatorInstanceConfig], Any]


class UnifiedController:
    """Own runtime/client startup, ordered shutdown, health, and logical reconfiguration."""

    def __init__(
        self,
        config: AdapterConfig,
        runtimes: Mapping[str, SignalGeneratorRuntime],
        instances: Mapping[str, Any],
    ) -> None:
        """Retain app-scoped objects without creating tasks during construction."""

        self.config = config
        self.runtimes = dict(runtimes)
        self.instances = dict(instances)

    async def start(self) -> None:
        """Start replay runtimes before simulated clients according to failure policy."""

        for runtime in self.runtimes.values():
            await self._start_owned(runtime)
        for instance in self.instances.values():
            await self._start_owned(instance)

    async def _start_owned(self, owned: Any) -> None:
        """Start one object and isolate it unless all-or-nothing startup is requested."""

        try:
            await owned.start()
        except Exception:
            if self.config.failure_policy == "fail_host":
                raise

    async def stop(self) -> None:
        """Disconnect simulated clients before stopping and flushing replay runtimes."""

        for instance in reversed(tuple(self.instances.values())):
            await instance.stop()
        for runtime in reversed(tuple(self.runtimes.values())):
            await runtime.stop()

    def ready(self) -> bool:
        """Aggregate passive readiness without HTTP calls or metric collection."""

        owned_items = (*self.runtimes.values(), *self.instances.values())
        health_items = [owned.health() for owned in owned_items]
        return bool(health_items) and all(item.ready for item in health_items)

    def health_payload(self) -> dict[str, Any]:
        """Serialize app-scoped state for development diagnostics."""

        return {
            KEY_READY: self.ready(),
            KEY_RUNTIMES: [
                self._health_dict(runtime.health()) for runtime in self.runtimes.values()
            ],
            KEY_INSTANCES: [
                self._health_dict(instance.health()) for instance in self.instances.values()
            ],
        }

    async def apply_runtime_config(
        self,
        runtime_id: str,
        document: Mapping[str, Any],
        *,
        base_path: str | Path,
    ) -> None:
        """Validate in memory and atomically logical-restart one owned signal runtime."""

        runtime = self.runtimes[runtime_id]
        loaded = load_configuration_mapping(document, base_path=base_path)
        await runtime.apply_config(loaded.model)

    @staticmethod
    def _health_dict(health: Any) -> dict[str, Any]:
        """Normalize dependency health dataclasses into stable API fields."""

        return {
            KEY_NAME: getattr(health, "name", getattr(health, "runtime_id", "")),
            KEY_RUNNING: health.running,
            KEY_READY: health.ready,
            KEY_RESTART_COUNT: health.restart_count,
            KEY_ERROR: getattr(health, "last_error", getattr(health, "error", None)),
        }


# Route closures intentionally retain the app-scoped controller and serializer.
# pylint: disable-next=too-many-locals
def create_app(
    config_path: str | Path,
    *,
    simulator_factory: SimulatorFactory = SimulatorInstance,
) -> Any:
    """Create a unified Quart app without binding a listener or spawning a process."""

    try:
        from quart import Quart, jsonify  # pylint: disable=import-outside-toplevel
    except ModuleNotFoundError as error:  # pragma: no cover - clean base-wheel contract.
        raise RuntimeError("unified mode requires signal-generator-opamp-sim[unified]") from error
    configured_flag = os.environ.get(ENV_APP_ENABLE_DEV_FEATURES, "").strip().lower()
    if configured_flag not in TRUE_VALUES:
        raise RuntimeError("unified simulator requires APP_ENABLE_DEV_FEATURES=true")
    adapter_config = load_adapter_config(config_path)
    if adapter_config.mode != "unified_quart":
        raise ValueError("create_app requires mode unified_quart")
    app = Quart(__name__)
    runtimes = _attach_runtimes(app, adapter_config)
    instances = _build_instances(adapter_config, simulator_factory)
    controller = UnifiedController(adapter_config, runtimes, instances)
    app.extensions[EXTENSION_KEY] = controller

    @app.before_serving
    async def start_unified_components() -> None:
        """Start all in-process components after Quart owns the event loop."""

        await controller.start()

    @app.after_serving
    async def stop_unified_components() -> None:
        """Await clients and replay tasks before the event loop is released."""

        await controller.stop()

    @app.get("/healthz")
    async def health_route() -> Any:
        """Report process liveness without touching replay cursors."""

        return jsonify({KEY_RUNNING: True})

    @app.get("/readyz")
    async def readiness_route() -> Any:
        """Report aggregate passive readiness for all required components."""

        status = 200 if controller.ready() else 503
        return jsonify(controller.health_payload()), status

    @app.get("/api/simulator/instances")
    async def instances_route() -> Any:
        """Expose development-only instance and runtime state."""

        return jsonify(controller.health_payload())

    return app


def _simulator_config(instance: InstanceConfig) -> SimulatorInstanceConfig:
    """Translate adapter-owned models into the generic opamp-core public API."""

    return SimulatorInstanceConfig(
        instance.name,
        instance.consumer_config_path,
        SimulatorResponsePlan(instance.responses_path),
        SimulatorIdentity(
            instance.service_instance_uid,
            instance.client_version,
            instance.config_version,
        ),
        instance.status_port,
    )


def _attach_runtimes(
    app: Any, adapter_config: AdapterConfig
) -> dict[str, SignalGeneratorRuntime]:
    """Attach every validated route set while the unified controller retains lifecycle ownership."""

    runtimes: dict[str, SignalGeneratorRuntime] = {}
    for runtime_config in adapter_config.runtimes:
        scenario = load_configuration(runtime_config.config_path)
        runtimes[runtime_config.runtime_id] = attach_signal_generator_runtime(
            app,
            runtime_id=runtime_config.runtime_id,
            config=scenario.model,
            route_prefix=runtime_config.route_prefix,
            manage_lifecycle=False,
        )
    return runtimes


def _build_instances(
    adapter_config: AdapterConfig, simulator_factory: SimulatorFactory
) -> dict[str, Any]:
    """Construct generic simulator services without starting their network tasks."""

    return {
        instance.name: simulator_factory(_simulator_config(instance))
        for instance in adapter_config.instances
    }
