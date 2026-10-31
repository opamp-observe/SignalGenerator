# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Prometheus collectors and isolated registries for replayed metric frames."""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import Metric

from signal_generator.constants import KEY_BUCKET_BOUND, KEY_QUANTILE
from signal_generator.metrics.models import MetricFamily, MetricFrame, MetricSample
from signal_generator.metrics.source import numeric_as_float
from signal_generator.metrics.store import FrameCursor

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@dataclass(frozen=True, slots=True)
class SelfMetricSnapshot:
    """Atomic diagnostic counters rendered beside scenario metrics."""

    pull_scrapes: int
    pull_failures: int
    push_attempts: int
    push_successes: int
    push_failures: int


class ReplaySelfMetrics:
    """Maintain replay diagnostics without registering process-global collectors."""

    def __init__(self) -> None:
        """Create zeroed counters protected for pull and push concurrency."""

        self._values = [0, 0, 0, 0, 0]
        self._lock = threading.Lock()

    def increment(self, index: int) -> None:
        """Increment one internal counter selected by its private stable index."""

        with self._lock:
            self._values[index] += 1

    def snapshot(self) -> SelfMetricSnapshot:
        """Return all diagnostic counters consistently."""

        with self._lock:
            return SelfMetricSnapshot(*self._values)

    def pull_scrape(self) -> None:
        """Record one pull exposition request."""

        self.increment(0)

    def pull_failure(self) -> None:
        """Record one pull exposition failure."""

        self.increment(1)

    def push_attempt(self) -> None:
        """Record one Pushgateway request attempt."""

        self.increment(2)

    def push_success(self) -> None:
        """Record one successfully delivered push frame."""

        self.increment(3)

    def push_failure(self) -> None:
        """Record one failed Pushgateway request attempt."""

        self.increment(4)


class ReplayCollector:
    """Advance one pull frame for each isolated-registry collection."""

    def __init__(
        self,
        cursor: FrameCursor,
        self_metrics: ReplaySelfMetrics,
        include_self_metrics: bool,
    ) -> None:
        """Bind a pull cursor and diagnostic source to the collector."""

        self._cursor = cursor
        self._self_metrics = self_metrics
        self._include_self_metrics = include_self_metrics

    def collect(self) -> Iterable[Metric]:
        """Collect exactly one frame, followed by optional generator diagnostics."""

        self._self_metrics.pull_scrape()
        frame = self._cursor.next_frame()
        if frame is not None:
            yield from metrics_for_frame(frame)
        if self._include_self_metrics:
            yield from self_metrics_for_snapshot(self._self_metrics.snapshot(), self._cursor)


def create_pull_registry(
    cursor: FrameCursor,
    self_metrics: ReplaySelfMetrics,
    include_self_metrics: bool = True,
) -> CollectorRegistry:
    """Create an isolated registry containing only this replay runtime's collector."""

    registry = CollectorRegistry()
    registry.register(ReplayCollector(cursor, self_metrics, include_self_metrics))
    return registry


def render_registry(registry: CollectorRegistry) -> bytes:
    """Render a pull registry using the Prometheus text exposition format."""

    return generate_latest(registry)


def render_frame(frame: MetricFrame) -> bytes:
    """Render one explicit frame for push without advancing any cursor."""

    registry = CollectorRegistry()
    registry.register(StaticFrameCollector(frame))
    return generate_latest(registry)


class StaticFrameCollector:
    """Expose one immutable frame to a temporary Pushgateway registry."""

    def __init__(self, frame: MetricFrame) -> None:
        """Retain the already validated frame."""

        self._frame = frame

    def collect(self) -> Iterable[Metric]:
        """Yield every family without changing runtime state."""

        yield from metrics_for_frame(self._frame)


def metrics_for_frame(frame: MetricFrame) -> Iterable[Metric]:
    """Convert every supported family type to prometheus-client metric objects."""

    for family in frame.metrics:
        metric = Metric(family.name, family.help, family.type, family.unit)
        for sample in family.samples:
            _add_family_sample(metric, family, sample)
        yield metric


def _add_family_sample(metric: Metric, family: MetricFamily, sample: MetricSample) -> None:
    """Add the Prometheus wire samples generated by one source sample."""

    if family.type in {"counter", "gauge", "untyped"}:
        metric.add_sample(family.name, sample.labels, numeric_as_float(sample.value))
        return
    if family.type == "info":
        metric.add_sample(f"{family.name}_info", {**sample.labels, **(sample.info or {})}, 1)
        return
    if family.type == "histogram":
        _add_histogram_sample(metric, family.name, sample)
        return
    _add_summary_sample(metric, family.name, sample)


def _add_histogram_sample(metric: Metric, name: str, sample: MetricSample) -> None:
    """Add bucket, sum, and count series for a histogram sample."""

    for bound, count in sample.buckets:
        labels = {**sample.labels, KEY_BUCKET_BOUND: _format_bound(bound)}
        metric.add_sample(f"{name}_bucket", labels, count)
    metric.add_sample(f"{name}_sum", sample.labels, sample.sum_value or 0.0)
    metric.add_sample(f"{name}_count", sample.labels, sample.count or 0)


def _add_summary_sample(metric: Metric, name: str, sample: MetricSample) -> None:
    """Add quantile, sum, and count series for a summary sample."""

    for quantile, value in sample.quantiles:
        labels = {**sample.labels, KEY_QUANTILE: format(quantile, "g")}
        metric.add_sample(name, labels, numeric_as_float(value))
    metric.add_sample(f"{name}_sum", sample.labels, sample.sum_value or 0.0)
    metric.add_sample(f"{name}_count", sample.labels, sample.count or 0)


def _format_bound(bound: int | float | str) -> str:
    """Format histogram bounds with Prometheus-compatible infinity spelling."""

    return str(bound) if isinstance(bound, str) else format(bound, "g")


def self_metrics_for_snapshot(
    snapshot: SelfMetricSnapshot, cursor: FrameCursor
) -> Iterable[Metric]:
    """Build generator-owned counters and cursor state without global registration."""

    values = (
        ("signal_generator_pull_scrapes_total", "Pull scrape requests.", snapshot.pull_scrapes),
        ("signal_generator_pull_failures_total", "Pull scrape failures.", snapshot.pull_failures),
        ("signal_generator_push_attempts_total", "Push request attempts.", snapshot.push_attempts),
        (
            "signal_generator_push_successes_total",
            "Successfully pushed frames.",
            snapshot.push_successes,
        ),
        ("signal_generator_push_failures_total", "Failed push attempts.", snapshot.push_failures),
    )
    for name, help_text, value in values:
        metric = Metric(name, help_text, "counter")
        metric.add_sample(name, {}, value)
        yield metric
    cursor_metric = Metric(
        "signal_generator_cursor_delivered", "Frames delivered by cursor.", "gauge"
    )
    cursor_metric.add_sample(
        "signal_generator_cursor_delivered", {"cursor": cursor.name}, cursor.snapshot().delivered
    )
    yield cursor_metric
