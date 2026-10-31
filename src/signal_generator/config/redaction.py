# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Redact secret-like values from effective configuration output."""

from __future__ import annotations

from typing import Any

from signal_generator.constants import REDACTED_VALUE, SECRET_KEY_FRAGMENTS


def redact_secrets(value: Any, parent_key: str = "") -> Any:
    """Return a recursively redacted copy of ``value`` based on documented secret key fragments."""

    if any(fragment in parent_key.casefold() for fragment in SECRET_KEY_FRAGMENTS):
        return REDACTED_VALUE
    redactor = _REDACTORS.get(type(value), _identity)
    return redactor(value, parent_key)


def _redact_mapping(value: dict[str, Any], parent_key: str) -> dict[str, Any]:
    """Redact every mapping value using its own key for secret detection."""

    del parent_key
    return {key: redact_secrets(child, str(key)) for key, child in value.items()}


def _redact_list(value: list[Any], parent_key: str) -> list[Any]:
    """Redact list members while retaining the owning field's key context."""

    return [redact_secrets(child, parent_key) for child in value]


def _identity(value: Any, parent_key: str) -> Any:
    """Return scalar non-secret values unchanged."""

    del parent_key
    return value


_REDACTORS = {dict: _redact_mapping, list: _redact_list}
