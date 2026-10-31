# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Legacy property parsing and conversion tests."""

from pathlib import Path

import pytest

from signal_generator.config.legacy_properties import convert_properties, read_properties


def test_convert_all_output_shapes() -> None:
    """Legacy built-in output names map to safe Python adapter names and options."""

    cases = {
        "FILE": ("file", {"TARGETFILE": "out.log"}),
        "HTTP": ("http", {"TARGETURL": "http://localhost/events"}),
        "TCP": ("tcp", {"TARGETIP": "localhost", "TARGETPORT": "1234"}),
        "JUL": ("python_logging", {}),
        "STDOUT": ("stdout", {}),
        "ERROUT": ("stderr", {}),
        "CUSTOM": ("plugin", {"CUSTOMOUTPUT": "demo"}),
    }
    for legacy_name, (expected, extras) in cases.items():
        document, warnings = convert_properties({"OUTPUTTYPE": legacy_name, **extras})
        assert document["logs"]["outputs"][0]["type"] == expected
        assert warnings == []


def test_unknown_property_warning_and_strict_error() -> None:
    """Unknown keys warn normally and fail strict conversion."""

    _, warnings = convert_properties({"UNKNOWN": "value"})
    assert warnings == ["unsupported legacy property ignored: UNKNOWN"]
    with pytest.raises(ValueError, match="unsupported legacy"):
        convert_properties({"UNKNOWN": "value"}, strict=True)


def test_properties_reader_and_invalid_values(tmp_path: Path) -> None:
    """Properties support equals/colon delimiters and reject malformed or ambiguous values."""

    properties_path = tmp_path / "legacy.properties"
    properties_path.write_text("# comment\nSOURCE=file.txt\nOUTPUTTYPE:STDOUT\n", encoding="utf-8")
    assert read_properties(properties_path)["SOURCE"] == "file.txt"
    properties_path.write_text("bad line\n", encoding="utf-8")
    with pytest.raises(ValueError, match="delimiter"):
        read_properties(properties_path)
    with pytest.raises(ValueError, match="true or false"):
        convert_properties({"ALLOWNL": "maybe"})
