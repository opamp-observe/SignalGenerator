# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""SignalGenerator command-line entry point and stable exit-code contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from signal_generator import __version__
from signal_generator.application import ApplicationStartupError, run_application
from signal_generator.config.legacy_properties import convert_properties, read_properties
from signal_generator.config.loader import ConfigurationLoadError, load_configuration
from signal_generator.config.redaction import redact_secrets
from signal_generator.config.validation import ValidationResult, validate_config_file
from signal_generator.constants import (
    DEFAULT_LOG_LEVEL,
    ENV_CONFIG,
    EXIT_RUNTIME,
    EXIT_STARTUP,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
)
from signal_generator.logs.scheduler import OutputStartupError, ReplayError

COMMAND_RUN = "run"
COMMAND_VALIDATE = "validate"
COMMAND_PRINT = "print-effective-config"
COMMAND_CONVERT = "convert-properties"


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI grammar once so commands and help remain contract-testable."""

    parser = argparse.ArgumentParser(prog="signal-generator")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser(COMMAND_RUN, help="run configured replay signals")
    _add_config_argument(run_parser)
    validate_parser = commands.add_parser(
        COMMAND_VALIDATE, help="validate configuration and sources"
    )
    _add_config_argument(validate_parser)
    validate_parser.add_argument(
        "--format", choices=("text", "json"), default="text", dest="result_format"
    )
    validate_parser.add_argument("--schema-only", action="store_true")
    validate_parser.add_argument("--strict", action="store_true")
    print_parser = commands.add_parser(COMMAND_PRINT, help="print redacted effective configuration")
    _add_config_argument(print_parser)
    convert_parser = commands.add_parser(COMMAND_CONVERT, help="convert legacy properties to JSON")
    convert_parser.add_argument("--input", required=True, type=Path)
    convert_parser.add_argument("--output", required=True, type=Path)
    convert_parser.add_argument("--strict", action="store_true")
    convert_parser.add_argument("--force", action="store_true")
    return parser


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared configuration path with the documented environment fallback."""

    parser.add_argument(
        "--config",
        type=Path,
        default=os.environ.get(ENV_CONFIG),
        required=ENV_CONFIG not in os.environ,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a CLI command and return its documented process exit code."""

    arguments = build_parser().parse_args(argv)
    if arguments.command == COMMAND_VALIDATE:
        return _validate_command(arguments)
    if arguments.command == COMMAND_PRINT:
        return _print_command(arguments)
    if arguments.command == COMMAND_CONVERT:
        return _convert_command(arguments)
    return _run_command(arguments)


def _validate_command(arguments: argparse.Namespace) -> int:
    """Render schema and source validation results without runtime side effects."""

    result = validate_config_file(
        arguments.config, schema_only=arguments.schema_only, strict=arguments.strict
    )
    if arguments.result_format == "json":
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        _print_text_result(result, Path(arguments.config))
    return EXIT_SUCCESS if result.valid else EXIT_VALIDATION


def _print_text_result(result: ValidationResult, path: Path) -> None:
    """Write a success summary to stdout or actionable diagnostics to stderr."""

    if result.valid:
        print(f"Configuration is valid: {path}")
        return
    for diagnostic in (*result.errors, *result.warnings):
        location = (
            f"{diagnostic.source}:{diagnostic.line}" if diagnostic.line else diagnostic.source
        )
        heading = f"{diagnostic.severity.upper()} {diagnostic.code} {location}"
        print(
            f"{heading} {diagnostic.instance_path}",
            file=sys.stderr,
        )
        print(f"  {diagnostic.message}", file=sys.stderr)
        if diagnostic.hint:
            print(f"  hint: {diagnostic.hint}", file=sys.stderr)


def _print_command(arguments: argparse.Namespace) -> int:
    """Print deterministic effective JSON with secret values redacted."""

    try:
        loaded = load_configuration(arguments.config)
    except ConfigurationLoadError as error:
        print(str(error), file=sys.stderr)
        return EXIT_VALIDATION
    print(json.dumps(redact_secrets(loaded.effective), indent=2, sort_keys=True))
    return EXIT_SUCCESS


def _convert_command(arguments: argparse.Namespace) -> int:
    """Convert a legacy property file without overwriting output unless explicitly requested."""

    output_path = arguments.output.resolve()
    if output_path.exists() and not arguments.force:
        print(f"output exists; use --force to replace it: {output_path}", file=sys.stderr)
        return EXIT_VALIDATION
    try:
        document, warnings = convert_properties(
            read_properties(arguments.input), strict=arguments.strict
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            f"{json.dumps(document, indent=2, sort_keys=True)}\n", encoding="utf-8"
        )
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_VALIDATION
    for warning in warnings:
        print(f"WARNING {warning}", file=sys.stderr)
    print(f"Converted configuration: {output_path}")
    return EXIT_SUCCESS


def _run_command(arguments: argparse.Namespace) -> int:
    """Validate, load, and run the standalone application with classified failures."""

    try:
        loaded = load_configuration(arguments.config)
        logging.basicConfig(level=loaded.model.runtime.log_level or DEFAULT_LOG_LEVEL)
        asyncio.run(run_application(loaded.model))
    except ConfigurationLoadError as error:
        print(str(error), file=sys.stderr)
        return EXIT_VALIDATION
    except (ApplicationStartupError, OutputStartupError, OSError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_STARTUP
    except (ReplayError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_RUNTIME
    except KeyboardInterrupt:
        return EXIT_SUCCESS
    return EXIT_SUCCESS
