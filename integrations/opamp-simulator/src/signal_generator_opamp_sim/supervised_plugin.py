# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Installed OpAMP consumer plugin for the separate supervised-process permutation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import pathlib
import shutil
import subprocess
from typing import Any

from opamp_consumer import config as consumer_config
from opamp_consumer.abstract_client import AbstractOpAMPClient
from opamp_consumer.client_bootstrap import (
    build_common_cli_parser,
    configure_logging_for_config,
    configure_observability_for_config,
    load_config_from_cli_args,
    run_client,
    validate_runtime_server_config,
)
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.config_metadata import ConfigMetadata
from opamp_consumer.plugin_config import (
    ConsumerPluginConfigContext,
    resolve_optional_executable_from_config,
)
from signal_generator.config.validation import validate_config_mapping

DEFAULT_EXECUTABLE = "signal-generator"
DEFAULT_HEALTH_HOST = "127.0.0.1"
DEFAULT_HEALTH_PORT = 9108
DEFAULT_STATUS_TIMEOUT_SECONDS = 5.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0
ENV_EXECUTABLE = "OPAMP_SIGNAL_GENERATOR_EXECUTABLE_PATH"
ENV_HEALTH_HOST = "OPAMP_SIGNAL_GENERATOR_HEALTH_HOST"
ENV_HEALTH_PORT = "OPAMP_SIGNAL_GENERATOR_HEALTH_PORT"
HEALTH_PATH = "/healthz"
VALUE_AGENT_TYPE = "SignalGenerator"


def process_consumer_config(context: ConsumerPluginConfigContext) -> dict[str, Any]:
    """Resolve plugin fields with explicit environment-over-file precedence."""

    raw = context.raw_section
    executable = os.environ.get(
        ENV_EXECUTABLE, raw.get("executable_path", DEFAULT_EXECUTABLE)
    )
    return {
        "signal_generator_executable_path": resolve_optional_executable_from_config(
            raw_value=executable,
            config_path=context.config_path,
        ),
        "signal_generator_health_host": str(
            os.environ.get(ENV_HEALTH_HOST, raw.get("health_host", DEFAULT_HEALTH_HOST))
        ),
        "signal_generator_health_port": int(
            os.environ.get(ENV_HEALTH_PORT, raw.get("health_port", DEFAULT_HEALTH_PORT))
        ),
        "signal_generator_status_timeout_seconds": float(
            raw.get("status_timeout_seconds", DEFAULT_STATUS_TIMEOUT_SECONDS)
        ),
        "signal_generator_shutdown_timeout_seconds": float(
            raw.get("shutdown_timeout_seconds", DEFAULT_SHUTDOWN_TIMEOUT_SECONDS)
        ),
    }


class SignalGeneratorLifecycle:
    """Start and stop only the SignalGenerator child owned by one OpAMP client."""

    def __init__(self, owner: SignalGeneratorOpAMPClient) -> None:
        """Retain the client that owns process state and configuration."""

        self._owner = owner

    def launch_agent_process(self) -> bool:
        """Launch a shell-free child argv and retain its process handle."""

        executable = str(
            getattr(self._owner.config, "signal_generator_executable_path", DEFAULT_EXECUTABLE)
            or DEFAULT_EXECUTABLE
        )
        config_path = self._owner.config.agent_config_path
        if not config_path:
            raise ValueError("agent_config_path is required for SignalGenerator")
        command = [executable, "run", "--config", str(config_path)]
        command.extend(self._owner.config.agent_additional_params or [])
        # The lifecycle retains this shell-free child across method calls.
        # pylint: disable-next=consider-using-with
        self._owner.data.agent_process = subprocess.Popen(  # noqa: S603
            command
        )
        return True

    def terminate_agent_process(self) -> None:
        """Terminate gracefully and kill only after the configured bounded wait."""

        process = self._owner.data.agent_process
        if process is None:
            return
        process.terminate()
        timeout = float(
            getattr(
                self._owner.config,
                "signal_generator_shutdown_timeout_seconds",
                DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
            )
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=DEFAULT_STATUS_TIMEOUT_SECONDS)
        self._owner.data.agent_process = None

    def restart_agent_process(self) -> bool:
        """Replace the owned child using the normal stop/start contract."""

        self.terminate_agent_process()
        return self.launch_agent_process()


class SignalGeneratorOpAMPClient(AbstractOpAMPClient):
    """Report a supervised SignalGenerator as a distinct OpAMP agent."""

    _runtime_agent_command = DEFAULT_EXECUTABLE
    _runtime_config_flag = "--config"
    _heartbeat_paths = (HEALTH_PATH,)
    _value_agent_type = VALUE_AGENT_TYPE
    SUPPORTED_AGENT_CAPABILITY_NAMES = (
        *consumer_config.MANDATORY_AGENT_CAPABILITY_NAMES,
        "AcceptsRemoteConfig",
        "ReportsEffectiveConfig",
        "ReportsHeartbeat",
    )

    def __init__(self, base_url: str, config: ConsumerConfig) -> None:
        """Create an OpAMP client with SignalGenerator health endpoint ownership."""

        super().__init__(base_url, config)
        self.data.agent_type_name = VALUE_AGENT_TYPE
        host = str(
            getattr(config, "signal_generator_health_host", DEFAULT_HEALTH_HOST)
            or DEFAULT_HEALTH_HOST
        )
        self._localhost_base = f"http://{host}"
        self._http_timeout_seconds = float(
            getattr(
                config,
                "signal_generator_status_timeout_seconds",
                DEFAULT_STATUS_TIMEOUT_SECONDS,
            )
        )

    def _create_runtime_process_lifecycle(self) -> SignalGeneratorLifecycle:
        """Select the adapter-owned supervised child lifecycle."""

        return SignalGeneratorLifecycle(self)

    def get_custom_handler_folder(self) -> pathlib.Path:
        """Use the shared consumer handlers because the adapter defines none."""

        return pathlib.Path(__file__).resolve().parent / "custom_handlers"

    def get_config_metadata(self) -> ConfigMetadata:
        """Report exact scenario text and a stable SHA-256 configuration version."""

        path = pathlib.Path(str(self.config.agent_config_path))
        config_data = path.read_text(encoding="utf-8")
        config_version = hashlib.sha256(config_data.encode("utf-8")).hexdigest()
        return ConfigMetadata(config_data=config_data, config_version=config_version)

    def add_agent_version(self, port: int) -> None:
        """Read package version without polling or consuming a metric frame."""

        del port
        executable = str(
            getattr(self.config, "signal_generator_executable_path", DEFAULT_EXECUTABLE)
            or DEFAULT_EXECUTABLE
        )
        executable = shutil.which(executable) or executable
        try:
            completed = subprocess.run(  # noqa: S603 - configured executable, fixed argument.
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=DEFAULT_STATUS_TIMEOUT_SECONDS,
                check=False,
            )
            self.data.agent_version = (completed.stdout or completed.stderr).strip()
        except (OSError, subprocess.SubprocessError) as error:
            logging.getLogger(__name__).warning("failed to read SignalGenerator version: %s", error)

    def write_config_file(self, filename: str, body: bytes) -> None:
        """Reject invalid remote configuration before the shared atomic file handling."""

        document = json.loads(body.decode("utf-8"))
        if not isinstance(document, dict):
            raise ValueError("remote SignalGenerator configuration root must be an object")
        result = validate_config_mapping(document, base_path=pathlib.Path(filename).parent)
        if not result.valid:
            raise ValueError("; ".join(diagnostic.message for diagnostic in result.errors))
        super().write_config_file(filename, body)


async def _run(config: ConsumerConfig) -> None:
    """Connect, then retain control in the public cancellable heartbeat loop."""

    client = SignalGeneratorOpAMPClient(config.server_url or "", config)
    client.launch_agent_process()
    port = int(
        getattr(config, "signal_generator_health_port", DEFAULT_HEALTH_PORT)
        or DEFAULT_HEALTH_PORT
    )
    client.add_agent_version(port)
    try:
        await run_client(client)
        await client.run_heartbeat_loop(port)
    finally:
        await client.finalize_async()
        client.terminate_agent_process()


def main() -> None:
    """Run the installed plugin through the shared OpAMP consumer CLI contract."""

    parser = build_common_cli_parser()
    arguments = parser.parse_args()
    config = load_config_from_cli_args(arguments)
    configure_logging_for_config(config)
    config = validate_runtime_server_config(
        config=config,
        localhost_base="http://127.0.0.1",
        missing_status_port_error="SignalGenerator health port is required",
    )
    configure_observability_for_config(
        config=config,
        default_service_name="opamp-consumer-signal-generator",
    )
    asyncio.run(_run(config))
