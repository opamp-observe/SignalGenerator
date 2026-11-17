# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Convert metric replay frames to OTLP/HTTP JSON export requests."""

from __future__ import annotations

from typing import Any

from signal_generator.metrics.models import MetricFamily, MetricFrame, MetricSample, NumericValue

AGGREGATION_TEMPORALITY_CUMULATIVE = 2
OTLP_SCOPE_NAME = "signal_generator.metrics"
OTLP_SERVICE_NAME = "signal-generator"


def metric_frame_to_otlp_json(frame: MetricFrame, timestamp_unix_nano: int) -> dict[str, Any]:
    """Build one JSON-encoded OTLP ``ExportMetricsServiceRequest`` from a frame."""

    metrics = [
        _metric_family(family, timestamp_unix_nano) for family in frame.metrics
    ]
    return {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": OTLP_SERVICE_NAME},
                        }
                    ]
                },
                "scopeMetrics": [
                    {
                        "scope": {"name": OTLP_SCOPE_NAME},
                        "metrics": metrics,
                    }
                ],
            }
        ]
    }


def _metric_family(family: MetricFamily, timestamp_unix_nano: int) -> dict[str, Any]:
    """Map one supported Prometheus-style family to its OTLP metric data type."""

    metric: dict[str, Any] = {
        "name": family.name,
        "description": family.help,
        "unit": family.unit,
    }
    if family.type == "counter":
        metric["sum"] = {
            "aggregationTemporality": AGGREGATION_TEMPORALITY_CUMULATIVE,
            "isMonotonic": True,
            "dataPoints": [
                _number_point(sample, timestamp_unix_nano) for sample in family.samples
            ],
        }
    elif family.type == "histogram":
        metric["histogram"] = {
            "aggregationTemporality": AGGREGATION_TEMPORALITY_CUMULATIVE,
            "dataPoints": [
                _histogram_point(sample, timestamp_unix_nano) for sample in family.samples
            ],
        }
    elif family.type == "summary":
        metric["summary"] = {
            "dataPoints": [
                _summary_point(sample, timestamp_unix_nano) for sample in family.samples
            ]
        }
    else:
        metric["gauge"] = {
            "dataPoints": [
                _number_point(sample, timestamp_unix_nano, family.type == "info")
                for sample in family.samples
            ]
        }
    return metric


def _number_point(
    sample: MetricSample, timestamp_unix_nano: int, info_metric: bool = False
) -> dict[str, Any]:
    """Build an OTLP number point, representing info families as a gauge of one."""

    attributes = dict(sample.labels)
    if info_metric and sample.info:
        attributes.update(sample.info)
    if not info_metric and sample.value is None:
        raise ValueError("scalar metric sample requires a value")
    value: NumericValue = 1 if info_metric else sample.value
    return {
        "attributes": _attributes(attributes),
        "timeUnixNano": str(timestamp_unix_nano),
        "asDouble": _otlp_number(value),
    }


def _histogram_point(sample: MetricSample, timestamp_unix_nano: int) -> dict[str, Any]:
    """Convert cumulative source buckets to OTLP per-bucket counts and explicit bounds."""

    bucket_counts: list[str] = []
    explicit_bounds: list[float] = []
    previous_count = 0
    for bound, cumulative_count in sample.buckets:
        bucket_counts.append(str(cumulative_count - previous_count))
        previous_count = cumulative_count
        if bound != "+Inf":
            explicit_bounds.append(float(bound))
    return {
        "attributes": _attributes(sample.labels),
        "timeUnixNano": str(timestamp_unix_nano),
        "count": str(sample.count),
        "sum": sample.sum_value,
        "bucketCounts": bucket_counts,
        "explicitBounds": explicit_bounds,
    }


def _summary_point(sample: MetricSample, timestamp_unix_nano: int) -> dict[str, Any]:
    """Build an OTLP summary point with JSON-safe quantile values."""

    return {
        "attributes": _attributes(sample.labels),
        "timeUnixNano": str(timestamp_unix_nano),
        "count": str(sample.count),
        "sum": sample.sum_value,
        "quantileValues": [
            {"quantile": quantile, "value": _otlp_number(value)}
            for quantile, value in sample.quantiles
        ],
    }


def _attributes(values: dict[str, str]) -> list[dict[str, Any]]:
    """Return deterministically ordered OTLP string attributes."""

    return [
        {"key": key, "value": {"stringValue": value}}
        for key, value in sorted(values.items())
    ]


def _otlp_number(value: NumericValue) -> int | float | str:
    """Translate source special values to the protobuf JSON double representation."""

    special_values = {"NaN": "NaN", "+Inf": "Infinity", "-Inf": "-Infinity"}
    return special_values.get(value, value)
