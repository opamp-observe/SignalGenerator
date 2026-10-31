# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Immutable runtime models for parsed metric frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

NumericValue = int | float | str


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One labelled scalar, histogram, summary, or info sample."""

    labels: dict[str, str]
    value: NumericValue | None = None
    info: dict[str, str] | None = None
    buckets: tuple[tuple[NumericValue, int], ...] = ()
    quantiles: tuple[tuple[float, NumericValue], ...] = ()
    sum_value: float | None = None
    count: int | None = None


@dataclass(frozen=True, slots=True)
class MetricFamily:
    """One Prometheus metric descriptor and all samples in a frame."""

    name: str
    type: str
    help: str
    samples: tuple[MetricSample, ...]
    unit: str = ""


@dataclass(frozen=True, slots=True)
class MetricFrame:
    """One complete metric snapshot read from a JSON Lines record."""

    frame: int | str | None
    metrics: tuple[MetricFamily, ...]
    observed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
