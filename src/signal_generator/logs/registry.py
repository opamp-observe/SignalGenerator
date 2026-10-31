# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Create built-in outputs and discover explicitly installed output plugins."""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points

from signal_generator.config.models import OutputConfig
from signal_generator.logs.outputs.base import LogOutput
from signal_generator.logs.outputs.file import FileOutput
from signal_generator.logs.outputs.http import HttpOutput
from signal_generator.logs.outputs.python_logging import PythonLoggingOutput
from signal_generator.logs.outputs.streams import stderr_output, stdout_output
from signal_generator.logs.outputs.tcp import TcpOutput

PLUGIN_GROUP = "signal_generator.log_outputs"
OutputFactory = Callable[[dict[str, object]], LogOutput]


def create_output(config: OutputConfig) -> LogOutput:
    """Create one output using a fixed built-in map or installed plugin entry point."""

    if config.type == "plugin":
        return _load_plugin(
            str(config.options["plugin_name"]), dict(config.options.get("options", {}))
        )
    factory = BUILTIN_FACTORIES.get(config.type)
    if factory is None:
        raise ValueError(f"unsupported output type: {config.type}")
    return factory(config)


def _file_output(config: OutputConfig) -> LogOutput:
    """Create a file adapter from validated file-specific options."""

    return FileOutput(
        str(config.options["path"]),
        str(config.options.get("mode", "append")),
        bool(config.options.get("flush_each_event", True)),
    )


def _http_output(config: OutputConfig) -> LogOutput:
    """Create an HTTP adapter from validated request options."""

    headers = config.options.get("headers")
    return HttpOutput(
        str(config.options["url"]),
        str(config.options.get("method", "POST")),
        headers if isinstance(headers, dict) else None,
        str(config.options.get("content_type", "text/plain; charset=utf-8")),
        config.timeout_seconds,
    )


def _tcp_output(config: OutputConfig) -> LogOutput:
    """Create a TCP adapter from validated address and delimiter options."""

    return TcpOutput(
        str(config.options["host"]),
        int(config.options["port"]),
        float(config.options.get("connect_timeout_seconds", config.timeout_seconds)),
        str(config.options.get("delimiter", "\n")),
    )


def _python_logging_output(config: OutputConfig) -> LogOutput:
    """Create a Python logging adapter from logger name and level options."""

    return PythonLoggingOutput(
        str(config.options.get("logger_name", "signal_generator.replay")),
        str(config.options.get("level", "INFO")),
    )


def _stdout_output(config: OutputConfig) -> LogOutput:
    """Create the process standard-output adapter."""

    del config
    return stdout_output()


def _stderr_output(config: OutputConfig) -> LogOutput:
    """Create the process standard-error adapter."""

    del config
    return stderr_output()


BUILTIN_FACTORIES: dict[str, Callable[[OutputConfig], LogOutput]] = {
    "stdout": _stdout_output,
    "stderr": _stderr_output,
    "file": _file_output,
    "http": _http_output,
    "tcp": _tcp_output,
    "python_logging": _python_logging_output,
}


def _load_plugin(plugin_name: str, options: dict[str, object]) -> LogOutput:
    """Load a named installed entry point without accepting arbitrary filesystem imports."""

    candidates = entry_points(group=PLUGIN_GROUP, name=plugin_name)
    if not candidates:
        raise ValueError(f"output plugin is not installed: {plugin_name}")
    factory: OutputFactory = candidates[0].load()
    output = factory(options)
    if not isinstance(output, LogOutput):
        raise TypeError(f"output plugin {plugin_name} did not return LogOutput")
    return output
