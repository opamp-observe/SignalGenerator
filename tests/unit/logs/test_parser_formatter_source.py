# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Token parsing, formatting, datetime, and multiline source tests."""

from datetime import datetime
from pathlib import Path

import pytest

from signal_generator.config.models import LogDefaults, LogSourceConfig
from signal_generator.logs.formatter import LogFormatter
from signal_generator.logs.models import LogEvent
from signal_generator.logs.parser import TokenParser, translate_datetime_format
from signal_generator.logs.source import read_records


def test_all_tokens_and_defaults() -> None:
    """Source tokens populate fields while omitted process uses its configured default."""

    config = LogSourceConfig(Path("unused"), "%t|%l|%c|%m", separator="|")
    parser = TokenParser(config, LogDefaults(process="worker"))
    event = parser.parse("2026/01/02 03:04:05|WARN|demo.Class|hello", 1)
    assert event.timestamp == datetime(2026, 1, 2, 3, 4, 5)
    assert event.log_level == "WARN"
    assert event.location == "demo.Class"
    assert event.process == "worker"
    assert event.message == "hello"


def test_relative_delay_and_unescaped_newline() -> None:
    """Relative timestamps and optional literal newline expansion are preserved."""

    config = LogSourceConfig(Path("unused"), "%t %m", unescape_newlines=True)
    event = TokenParser(config, LogDefaults()).parse("+250 hello\\nworld", 2)
    assert event.relative_delay_ms == 250
    assert event.message == "hello\nworld"


def test_parser_failures_are_actionable() -> None:
    """Invalid formats, relative delays, timestamps, and records raise specific errors."""

    with pytest.raises(ValueError, match="supported token"):
        TokenParser(LogSourceConfig(Path("unused"), "literal"), LogDefaults())
    with pytest.raises(ValueError, match="repeats token"):
        TokenParser(LogSourceConfig(Path("unused"), "%m %m"), LogDefaults())
    parser = TokenParser(LogSourceConfig(Path("unused"), "%t %m"), LogDefaults())
    with pytest.raises(ValueError, match="invalid relative delay"):
        parser.parse("+bad event", 1)
    with pytest.raises(ValueError, match="does not match"):
        parser.parse("not-a-time event", 1)
    with pytest.raises(ValueError, match="does not match source format"):
        TokenParser(LogSourceConfig(Path("unused"), "[%l] %m"), LogDefaults()).parse("plain", 3)


def test_datetime_translation_rejects_unknown_java_parts() -> None:
    """The supported Java subset translates exactly and rejects unsupported pattern letters."""

    assert translate_datetime_format("yyyy-MM-dd HH:mm:ss.SSS") == "%Y-%m-%d %H:%M:%S.%f"
    with pytest.raises(ValueError, match="unsupported"):
        translate_datetime_format("yyyy DDD")


def test_formatter_all_output_tokens() -> None:
    """Formatter renders timestamps, fields, and one-based cycle/record counters byte-exactly."""

    event = LogEvent(1, "message", log_level="ERROR", process="worker", location="demo")
    formatter = LogFormatter(
        "%t|%l|%p|%c|%m|%i|%j",
        "yyyy/MM/dd HH:mm:ss",
        lambda: datetime(2026, 1, 1, 0, 0, 0),
    )
    assert formatter.render(event, 2, 3).text == "2026/01/01 00:00:00|ERROR|worker|demo|message|2|3"


def test_multiline_grouping(tmp_path: Path) -> None:
    """Continuation lines are grouped until the next matching first line."""

    source_path = tmp_path / "events.txt"
    source_path.write_text("START first\n detail\nSTART second\n", encoding="utf-8")
    config = LogSourceConfig(source_path, "%m", first_line_pattern="^START")
    assert read_records(config) == ["START first\n detail", "START second"]
