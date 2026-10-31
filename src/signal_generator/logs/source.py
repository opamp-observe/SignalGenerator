# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Read source files and group physical lines into logical log records."""

from __future__ import annotations

import re
from pathlib import Path

from signal_generator.config.models import LogSourceConfig


def read_records(config: LogSourceConfig) -> list[str]:
    """Read and group records according to the optional first-line regular expression."""

    source_path = Path(config.path)
    with source_path.open("r", encoding=config.encoding, newline=None) as source_file:
        lines = [line.rstrip("\r\n") for line in source_file]
    if config.first_line_pattern is None:
        return lines
    return _group_multiline(lines, re.compile(config.first_line_pattern))


def _group_multiline(lines: list[str], first_line_pattern: re.Pattern[str]) -> list[str]:
    """Append continuation lines to the preceding first line while preserving newlines."""

    records: list[str] = []
    current: list[str] = []
    for line in lines:
        if first_line_pattern.search(line) and current:
            records.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
        else:
            current = [line]
    if current:
        records.append("\n".join(current))
    return records
