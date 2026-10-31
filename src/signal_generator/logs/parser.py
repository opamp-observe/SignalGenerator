# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Parse original LogGenerator token formats into typed log events."""

from __future__ import annotations

import re
from datetime import datetime

from signal_generator.config.models import LogDefaults, LogSourceConfig
from signal_generator.logs.models import LogEvent

TOKEN_NAMES = {"%t": "time", "%m": "message", "%l": "level", "%p": "process", "%c": "location"}
TOKEN_PATTERN = re.compile("|".join(re.escape(token) for token in TOKEN_NAMES))
JAVA_DATETIME_PARTS = (
    ("yyyy", "%Y"),
    ("SSS", "%f"),
    ("MM", "%m"),
    ("dd", "%d"),
    ("HH", "%H"),
    ("mm", "%M"),
    ("ss", "%S"),
    ("XXX", "%z"),
)


class TokenParser:
    """Compile one source token format and parse all records with it."""

    def __init__(self, config: LogSourceConfig, defaults: LogDefaults) -> None:
        """Create a parser for ``config`` and fallback fields from ``defaults``."""

        self.config = config
        self.defaults = defaults
        self._pattern = _compile_source_pattern(config.format, config.separator)
        self._datetime_format = translate_datetime_format(config.datetime_format)

    def parse(self, record: str, source_index: int) -> LogEvent:
        """Parse one logical record and report its one-based source index on failure."""

        match = self._pattern.fullmatch(record)
        if match is None:
            raise ValueError(
                f"record {source_index} does not match source format {self.config.format!r}"
            )
        fields = match.groupdict()
        timestamp, relative_delay = _parse_time(fields.get("time"), self._datetime_format)
        message = fields.get("message", record)
        if self.config.unescape_newlines:
            message = message.replace("\\n", "\n")
        return LogEvent(
            source_index=source_index,
            message=message,
            timestamp=timestamp,
            relative_delay_ms=relative_delay,
            log_level=fields.get("level") or self.defaults.log_level,
            process=fields.get("process") or self.defaults.process,
            location=fields.get("location") or self.defaults.location,
        )


def _compile_source_pattern(source_format: str, separator: str | None) -> re.Pattern[str]:
    """Translate a token format into a named regular expression without executing arbitrary code."""

    matches = list(TOKEN_PATTERN.finditer(source_format))
    if not matches:
        raise ValueError("source format must contain at least one supported token")
    seen: set[str] = set()
    pattern_parts: list[str] = []
    position = 0
    for token_index, token_match in enumerate(matches):
        pattern_parts.append(
            _literal_pattern(source_format[position : token_match.start()], separator)
        )
        format_marker = token_match.group(0)
        field_name = TOKEN_NAMES[format_marker]
        if field_name in seen:
            raise ValueError(f"source format repeats token {format_marker}")
        seen.add(field_name)
        is_last = token_index == len(matches) - 1
        expression = ".*" if format_marker == "%m" or is_last else ".*?"
        pattern_parts.append(f"(?P<{field_name}>{expression})")
        position = token_match.end()
    pattern_parts.append(_literal_pattern(source_format[position:], separator))
    return re.compile("".join(pattern_parts), re.DOTALL)


def _literal_pattern(literal: str, separator: str | None) -> str:
    """Escape literal format text, applying configured separator behavior to whitespace."""

    if separator is None:
        return re.sub(r"\\\s+", r"\\s+", re.escape(literal))
    if literal.isspace() and literal:
        return re.escape(separator)
    return re.escape(literal)


def translate_datetime_format(java_format: str) -> str:
    """Translate the documented Java datetime subset into Python ``strptime`` syntax."""

    remaining = java_format
    for java_part, _ in JAVA_DATETIME_PARTS:
        remaining = remaining.replace(java_part, "")
    if re.search(r"[A-Za-z]", remaining):
        raise ValueError(f"unsupported Java datetime pattern: {java_format}")
    translated = java_format
    for java_part, python_part in JAVA_DATETIME_PARTS:
        translated = translated.replace(java_part, python_part)
    return translated


def _parse_time(value: str | None, datetime_format: str) -> tuple[datetime | None, int | None]:
    """Parse absolute timestamps or ``+N`` millisecond relative delays."""

    if value is None or not value:
        return None, None
    if value.startswith("+"):
        try:
            delay = int(value[1:])
        except ValueError as error:
            raise ValueError(f"invalid relative delay: {value}") from error
        if delay < 0:
            raise ValueError(f"relative delay must not be negative: {value}")
        return None, delay
    try:
        return datetime.strptime(value, datetime_format), None
    except ValueError as error:
        raise ValueError(f"timestamp {value!r} does not match {datetime_format!r}") from error
