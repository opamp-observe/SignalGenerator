# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Bounded JSON Lines loading and semantic validation for metric frames."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from signal_generator.config.models import MetricSourceConfig
from signal_generator.constants import (
    KEY_BUCKET_BOUND,
    KEY_BUCKETS,
    KEY_COUNT,
    KEY_FRAME,
    KEY_HELP,
    KEY_INFO,
    KEY_LABELS,
    KEY_METADATA,
    KEY_METRIC_FAMILIES,
    KEY_NAME,
    KEY_OBSERVED_AT,
    KEY_QUANTILE,
    KEY_QUANTILES,
    KEY_SAMPLES,
    KEY_SUM,
    KEY_TYPE,
    KEY_UNIT,
    KEY_VALUE,
)
from signal_generator.metrics.models import MetricFamily, MetricFrame, MetricSample, NumericValue

METRIC_NAME_PATTERN = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
LABEL_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
SPECIAL_VALUES = {"NaN", "+Inf", "-Inf"}
SCALAR_TYPES = {"counter", "gauge", "untyped"}


class MetricDataError(ValueError):
    """Report one actionable metric source contract violation."""


def load_metric_frames(config: MetricSourceConfig) -> tuple[MetricFrame, ...]:
    """Load, validate, and freeze every non-empty frame in a configured source."""

    frames: list[MetricFrame] = []
    descriptors: dict[str, tuple[str, str, str, tuple[str, ...]]] = {}
    with config.path.open("r", encoding=config.encoding) as source_file:
        for line_number, raw_line in enumerate(source_file, start=1):
            if not raw_line.strip():
                continue
            if len(raw_line.encode(config.encoding)) > config.maximum_line_bytes:
                raise MetricDataError(f"line {line_number} exceeds maximum_line_bytes")
            try:
                document = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise MetricDataError(f"line {line_number}: invalid JSON: {error.msg}") from error
            frame = parse_metric_frame(document, line_number, config.maximum_samples_per_frame)
            _validate_descriptors(frame, descriptors, line_number)
            frames.append(frame)
    if not frames:
        raise MetricDataError("metric source contains no frames")
    return tuple(frames)


def parse_metric_frame(document: Any, line_number: int, maximum_samples: int) -> MetricFrame:
    """Convert one schema-valid mapping into typed models with semantic checks."""

    if not isinstance(document, Mapping):
        raise MetricDataError(f"line {line_number}: frame must be an object")
    raw_metrics = _require_metric_documents(document, line_number, maximum_samples)
    families = tuple(_parse_family(item, line_number) for item in raw_metrics)
    _ensure_unique_family_names(families, line_number)
    observed_at = _parse_observed_at(document.get(KEY_OBSERVED_AT), line_number)
    return MetricFrame(
        document.get(KEY_FRAME),
        families,
        observed_at,
        dict(document.get(KEY_METADATA, {})),
    )


def _require_metric_documents(
    document: Mapping[str, Any], line_number: int, maximum_samples: int
) -> list[Any]:
    """Require a non-empty family array within the configured sample limit."""

    raw_metrics = document.get(KEY_METRIC_FAMILIES)
    if not isinstance(raw_metrics, list) or not raw_metrics:
        raise MetricDataError(f"line {line_number}: metrics must be a non-empty array")
    sample_counts = (
        len(item.get(KEY_SAMPLES, ())) for item in raw_metrics if isinstance(item, dict)
    )
    if sum(sample_counts) > maximum_samples:
        raise MetricDataError(f"line {line_number} exceeds maximum_samples_per_frame")
    return raw_metrics


def _ensure_unique_family_names(families: tuple[MetricFamily, ...], line_number: int) -> None:
    """Reject duplicate family descriptors in one frame."""

    names = [family.name for family in families]
    if len(names) != len(set(names)):
        raise MetricDataError(f"line {line_number}: duplicate metric family name")


def _parse_observed_at(value: Any, line_number: int) -> datetime | None:
    """Parse an optional RFC 3339 observation timestamp."""

    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise MetricDataError(f"line {line_number}: observed_at must be RFC 3339") from error


def _parse_family(document: Any, line_number: int) -> MetricFamily:
    """Validate one metric descriptor and dispatch its samples by type."""

    if not isinstance(document, Mapping):
        raise MetricDataError(f"line {line_number}: metric family must be an object")
    name = str(document.get(KEY_NAME, ""))
    metric_type = str(document.get(KEY_TYPE, ""))
    _validate_family_identity(name, metric_type, line_number)
    samples = document.get(KEY_SAMPLES)
    if not isinstance(samples, list) or not samples:
        raise MetricDataError(f"line {line_number}: {name} samples must be a non-empty array")
    parsed_samples = tuple(
        _parse_sample(sample, metric_type, line_number, name) for sample in samples
    )
    _reject_duplicate_label_sets(parsed_samples, line_number, name)
    return MetricFamily(
        name,
        metric_type,
        str(document.get(KEY_HELP, "")),
        parsed_samples,
        str(document.get(KEY_UNIT, "")),
    )


def _validate_family_identity(name: str, metric_type: str, line_number: int) -> None:
    """Validate the metric name namespace and supported family type."""

    if not METRIC_NAME_PATTERN.fullmatch(name) or name.startswith("signal_generator_"):
        raise MetricDataError(f"line {line_number}: invalid or reserved metric name '{name}'")
    supported_types = SCALAR_TYPES | {"histogram", "summary", "info"}
    if metric_type not in supported_types:
        raise MetricDataError(f"line {line_number}: unsupported metric type '{metric_type}'")


def _parse_sample(document: Any, metric_type: str, line_number: int, name: str) -> MetricSample:
    """Parse one sample according to its enclosing metric family type."""

    if not isinstance(document, Mapping):
        raise MetricDataError(f"line {line_number}: {name} sample must be an object")
    labels = _parse_labels(document.get(KEY_LABELS, {}), line_number, name)
    if metric_type in SCALAR_TYPES:
        value = _numeric(document.get(KEY_VALUE), line_number, name)
        if metric_type == "counter" and _as_float(value) < 0:
            raise MetricDataError(f"line {line_number}: counter {name} cannot be negative")
        return MetricSample(labels, value=value)
    if metric_type == "info":
        info = _parse_labels(document.get(KEY_INFO), line_number, name, allow_empty=False)
        return MetricSample(labels, info=info)
    if metric_type == "histogram":
        return _parse_histogram(document, labels, line_number, name)
    return _parse_summary(document, labels, line_number, name)


def _parse_labels(
    value: Any, line_number: int, name: str, *, allow_empty: bool = True
) -> dict[str, str]:
    """Validate Prometheus label names and require string values."""

    if not isinstance(value, Mapping) or (not allow_empty and not value):
        raise MetricDataError(f"line {line_number}: {name} labels must be an object of strings")
    labels: dict[str, str] = {}
    for label_name, label_value in value.items():
        if not _valid_label(label_name, label_value):
            raise MetricDataError(f"line {line_number}: {name} has an invalid label")
        labels[str(label_name)] = label_value
    return labels


def _valid_label(name: Any, value: Any) -> bool:
    """Return whether one label name/value pair follows Prometheus rules."""

    normalized_name = str(name)
    return bool(
        LABEL_NAME_PATTERN.fullmatch(normalized_name)
        and not normalized_name.startswith("__")
        and isinstance(value, str)
    )


def _numeric(value: Any, line_number: int, name: str) -> NumericValue:
    """Accept JSON numbers or explicit Prometheus special-value strings."""

    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise MetricDataError(f"line {line_number}: {name} value must be numeric")
    if isinstance(value, str) and value not in SPECIAL_VALUES:
        raise MetricDataError(f"line {line_number}: {name} has an invalid numeric string")
    if isinstance(value, float) and not math.isfinite(value):
        raise MetricDataError(f"line {line_number}: {name} non-finite values must use strings")
    return value


def _as_float(value: NumericValue) -> float:
    """Convert a validated value to the representation expected by prometheus-client."""

    return {"NaN": math.nan, "+Inf": math.inf, "-Inf": -math.inf}.get(value, float(value))


def _parse_histogram(
    document: Mapping[str, Any], labels: dict[str, str], line_number: int, name: str
) -> MetricSample:
    """Validate cumulative histogram buckets, count, and finite sum."""

    count = _non_negative_integer(document.get(KEY_COUNT), line_number, name)
    sum_value = _finite_float(document.get(KEY_SUM), line_number, name)
    raw_buckets = document.get(KEY_BUCKETS)
    if not isinstance(raw_buckets, list) or not raw_buckets:
        raise MetricDataError(f"line {line_number}: histogram {name} requires buckets")
    buckets: list[tuple[NumericValue, int]] = []
    previous_bound = -math.inf
    previous_count = -1
    for bucket in raw_buckets:
        bound, bucket_count, numeric_bound = _parse_bucket(bucket, line_number, name)
        if numeric_bound <= previous_bound or bucket_count < previous_count:
            raise MetricDataError(
                f"line {line_number}: histogram {name} buckets are not cumulative"
            )
        buckets.append((bound, bucket_count))
        previous_bound, previous_count = numeric_bound, bucket_count
    if buckets[-1][0] != "+Inf" or buckets[-1][1] != count:
        raise MetricDataError(f"line {line_number}: histogram {name} +Inf bucket must equal count")
    return MetricSample(labels, buckets=tuple(buckets), sum_value=sum_value, count=count)


def _parse_bucket(bucket: Any, line_number: int, name: str) -> tuple[NumericValue, int, float]:
    """Parse one histogram bucket into source and comparable bound values."""

    if not isinstance(bucket, Mapping):
        raise MetricDataError(f"line {line_number}: histogram {name} bucket is invalid")
    bound = _numeric(bucket.get(KEY_BUCKET_BOUND), line_number, name)
    count = _non_negative_integer(bucket.get(KEY_COUNT), line_number, name)
    return bound, count, _as_float(bound)


def _parse_summary(
    document: Mapping[str, Any], labels: dict[str, str], line_number: int, name: str
) -> MetricSample:
    """Validate summary quantiles, count, and finite sum."""

    count = _non_negative_integer(document.get(KEY_COUNT), line_number, name)
    sum_value = _finite_float(document.get(KEY_SUM), line_number, name)
    raw_quantiles = document.get(KEY_QUANTILES)
    if not isinstance(raw_quantiles, list):
        raise MetricDataError(f"line {line_number}: summary {name} requires quantiles")
    quantiles: list[tuple[float, NumericValue]] = []
    seen: set[float] = set()
    for item in raw_quantiles:
        quantile, value = _parse_quantile(item, line_number, name)
        if quantile < 0 or quantile > 1 or quantile in seen:
            raise MetricDataError(f"line {line_number}: summary {name} has an invalid quantile")
        seen.add(quantile)
        quantiles.append((quantile, value))
    return MetricSample(labels, quantiles=tuple(quantiles), sum_value=sum_value, count=count)


def _parse_quantile(item: Any, line_number: int, name: str) -> tuple[float, NumericValue]:
    """Parse one summary quantile and its value."""

    if not isinstance(item, Mapping):
        raise MetricDataError(f"line {line_number}: summary {name} quantile is invalid")
    quantile = _finite_float(item.get(KEY_QUANTILE), line_number, name)
    return quantile, _numeric(item.get(KEY_VALUE), line_number, name)


def _non_negative_integer(value: Any, line_number: int, name: str) -> int:
    """Require a non-negative JSON integer without accepting booleans."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MetricDataError(f"line {line_number}: {name} count must be a non-negative integer")
    return value


def _finite_float(value: Any, line_number: int, name: str) -> float:
    """Require a finite JSON numeric value."""

    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MetricDataError(f"line {line_number}: {name} sum/quantile must be finite")
    return float(value)


def _reject_duplicate_label_sets(
    samples: tuple[MetricSample, ...], line_number: int, name: str
) -> None:
    """Reject duplicate series identities inside one family and frame."""

    identities = [tuple(sorted(sample.labels.items())) for sample in samples]
    if len(identities) != len(set(identities)):
        raise MetricDataError(f"line {line_number}: {name} contains duplicate label sets")


def _validate_descriptors(
    frame: MetricFrame,
    descriptors: dict[str, tuple[str, str, str, tuple[str, ...]]],
    line_number: int,
) -> None:
    """Require stable type, help, unit, and label names across all source frames."""

    for family in frame.metrics:
        label_sets = {tuple(sorted(sample.labels)) for sample in family.samples}
        if len(label_sets) != 1:
            raise MetricDataError(
                f"line {line_number}: {family.name} label names vary within the frame"
            )
        descriptor = (family.type, family.help, family.unit, next(iter(label_sets)))
        existing = descriptors.setdefault(family.name, descriptor)
        if existing != descriptor:
            raise MetricDataError(f"line {line_number}: descriptor changed for {family.name}")


def numeric_as_float(value: NumericValue) -> float:
    """Expose validated numeric conversion to exposition adapters."""

    return _as_float(value)
