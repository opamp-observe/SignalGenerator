# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Convert original LogGenerator properties into versioned SignalGenerator JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from signal_generator.constants import SCHEMA_VERSION

KNOWN_PROPERTIES = {
    "SOURCE",
    "SOURCEFORMAT",
    "SOURCEDTG",
    "SOURCE-SEPARATOR",
    "TARGETFORMAT",
    "TARGETDTG",
    "TARGET-SEPARATOR",
    "OUTPUTTYPE",
    "TARGETFILE",
    "TARGETIP",
    "TARGETPORT",
    "TARGETURL",
    "REPEAT",
    "ACCELERATEBY",
    "DEFAULTTIMEOFFSET",
    "FIRSTOFMULTILINEREGEX",
    "ALLOWNL",
    "CUSTOMOUTPUT",
    "DEFAULT-PROPCESS",
    "DEFAULT-LOCATION",
    "DEFAULT-LOGLEVEL",
    "VERBOSE",
}

OUTPUT_TYPE_MAP = {
    "FILE": "file",
    "HTTP": "http",
    "TCP": "tcp",
    "JUL": "python_logging",
    "STDOUT": "stdout",
    "ERROUT": "stderr",
    "STDERR": "stderr",
    "CUSTOM": "plugin",
}


def read_properties(path: str | Path) -> dict[str, str]:
    """Read simple Java-style key/value properties without executing interpolation."""

    properties: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8") as properties_file:
        for raw_line in properties_file:
            line = raw_line.strip()
            if not line or line.startswith(("#", "!")):
                continue
            separator_index = _separator_index(line)
            key = line[:separator_index].strip()
            value = line[separator_index + 1 :].strip()
            properties[key] = value
    return properties


def _separator_index(line: str) -> int:
    """Locate the first supported property delimiter and reject malformed lines."""

    indexes = [index for delimiter in ("=", ":") if (index := line.find(delimiter)) >= 0]
    if not indexes:
        raise ValueError(f"property line has no '=' or ':' delimiter: {line}")
    return min(indexes)


def convert_properties(
    properties: dict[str, str], *, strict: bool = False
) -> tuple[dict[str, Any], list[str]]:
    """Convert legacy properties and return warnings for keys that have no supported mapping."""

    unknown = sorted(set(properties) - KNOWN_PROPERTIES)
    if strict and unknown:
        raise ValueError(f"unsupported legacy properties: {', '.join(unknown)}")
    source: dict[str, Any] = {
        "path": properties.get("SOURCE", "log_events.txt"),
        "format": properties.get("SOURCEFORMAT", "%t %m"),
        "datetime_format": properties.get("SOURCEDTG", "yyyy/MM/dd HH:mm:ss"),
        "unescape_newlines": _parse_boolean(properties.get("ALLOWNL", "false")),
    }
    if "SOURCE-SEPARATOR" in properties:
        source["separator"] = properties["SOURCE-SEPARATOR"]
    if "FIRSTOFMULTILINEREGEX" in properties:
        source["multiline"] = {"first_line_pattern": properties["FIRSTOFMULTILINEREGEX"]}
    output = _convert_output(properties)
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "runtime": {
            "log_level": "DEBUG",
            "diagnostics": _parse_boolean(properties.get("VERBOSE", "false")),
        },
        "deployment": {"mode": "standalone", "failure_policy": "fail_process"},
        "logs": {
            "enabled": True,
            "source": source,
            "format": properties.get("TARGETFORMAT", "%t %m"),
            "datetime_format": properties.get("TARGETDTG", "yyyy/MM/dd HH:mm:ss"),
            "separator": properties.get("TARGET-SEPARATOR", " "),
            "defaults": {
                "process": properties.get("DEFAULT-PROPCESS", "Thread-1"),
                "location": properties.get("DEFAULT-LOCATION", "signal_generator"),
                "log_level": properties.get("DEFAULT-LOGLEVEL", "INFO"),
            },
            "replay": {
                "cycles": int(properties.get("REPEAT", "1")),
                "default_interval_ms": int(properties.get("DEFAULTTIMEOFFSET", "1000")),
                "acceleration": float(properties.get("ACCELERATEBY", "1")),
            },
            "outputs": [output],
        },
    }
    warnings = [f"unsupported legacy property ignored: {key}" for key in unknown]
    return document, warnings


def _convert_output(properties: dict[str, str]) -> dict[str, Any]:
    """Translate legacy output-specific fields into one built-in or plugin output mapping."""

    output_name = OUTPUT_TYPE_MAP.get(properties.get("OUTPUTTYPE", "STDOUT").upper())
    if output_name is None:
        raise ValueError(f"unsupported OUTPUTTYPE: {properties['OUTPUTTYPE']}")
    output: dict[str, Any] = {"type": output_name}
    if output_name == "file":
        output["path"] = properties.get("TARGETFILE", "signal-generator.log")
    elif output_name == "http":
        output["url"] = properties.get("TARGETURL", "")
    elif output_name == "tcp":
        output.update(
            {
                "host": properties.get("TARGETIP", "127.0.0.1"),
                "port": int(properties.get("TARGETPORT", "28080")),
            }
        )
    elif output_name == "plugin":
        output["plugin_name"] = properties.get("CUSTOMOUTPUT", "")
        output["options"] = {}
    return output


def _parse_boolean(value: str) -> bool:
    """Parse the legacy true/false spelling and reject ambiguous values."""

    normalized = value.strip().casefold()
    if normalized not in {"true", "false"}:
        raise ValueError(f"expected true or false, received: {value}")
    return normalized == "true"
