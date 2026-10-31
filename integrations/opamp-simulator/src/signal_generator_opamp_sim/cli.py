# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Console interface for validation, supervised mode, and unified Quart mode."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from collections.abc import Sequence

from signal_generator_opamp_sim import __version__
from signal_generator_opamp_sim.config import load_adapter_config, validate_adapter_file


def build_parser() -> argparse.ArgumentParser:
    """Build the side-effect-free adapter command parser."""

    parser = argparse.ArgumentParser(prog="signal-generator-opamp-sim")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate adapter and referenced configs")
    validate.add_argument("--config", required=True)
    validate.add_argument("--format", choices=("text", "json"), default="text")
    validate.add_argument("--schema-only", action="store_true")
    for command_name in ("supervised", "unified"):
        command = commands.add_parser(command_name)
        command.add_argument("--config", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one command and return a process-compatible status code."""

    arguments = build_parser().parse_args(argv)
    if arguments.command == "validate":
        return _validate(arguments)
    if arguments.command == "supervised":
        return _supervised(arguments.config)
    return _unified(arguments.config)


def _validate(arguments: argparse.Namespace) -> int:
    """Render shared-envelope validation diagnostics in text or JSON form."""

    result = validate_adapter_file(arguments.config, schema_only=arguments.schema_only)
    if arguments.format == "json":
        print(json.dumps(result.to_dict(), sort_keys=True))
    elif result.valid:
        print(f"valid: {arguments.config}")
    else:
        for diagnostic in result.errors:
            location = diagnostic.instance_path or "/"
            print(f"{diagnostic.code} {location}: {diagnostic.message}")
    return 0 if result.valid else 2


def _supervised(config_path: str) -> int:
    """Run the adapter-owned SignalGenerator child until it exits or is interrupted."""

    config = load_adapter_config(config_path)
    if config.mode != "supervised" or config.supervised is None:
        raise ValueError("supervised command requires mode supervised")
    # Retain the process beyond this scope; shell is never enabled.
    # pylint: disable-next=consider-using-with
    child = subprocess.Popen(  # noqa: S603
        [
            config.supervised.executable_path,
            "run",
            "--config",
            str(config.supervised.config_path),
        ]
    )
    try:
        return child.wait()
    except KeyboardInterrupt:
        child.terminate()
        try:
            return child.wait(timeout=config.supervised.shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            child.kill()
            return child.wait()


def _unified(config_path: str) -> int:
    """Run the one-worker Hypercorn/Quart deployment in the foreground."""

    try:
        from hypercorn.asyncio import serve  # pylint: disable=import-outside-toplevel
        from hypercorn.config import (  # pylint: disable=import-outside-toplevel
            Config as HypercornConfig,
        )
    except ModuleNotFoundError as error:  # pragma: no cover - clean base-wheel contract.
        raise RuntimeError("unified mode requires signal-generator-opamp-sim[unified]") from error
    from signal_generator_opamp_sim.quart_app import (  # pylint: disable=import-outside-toplevel
        create_app,
    )

    config = load_adapter_config(config_path)
    if config.quart is None:
        raise ValueError("unified command requires quart settings")
    server_config = HypercornConfig()
    server_config.bind = [f"{config.quart.host}:{config.quart.port}"]
    server_config.workers = 1
    asyncio.run(serve(create_app(config_path), server_config))
    return 0


if __name__ == "__main__":  # pragma: no cover - console entry point owns process exit.
    raise SystemExit(main())
