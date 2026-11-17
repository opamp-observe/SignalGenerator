# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Tiny test receiver that persists OTLP/HTTP JSON trace and metric receipts."""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

RECEIPT_PATH = Path("/tmp/otel-receipts.ndjson")  # noqa: S108 - isolated test container


def _spans(payload: dict[str, Any]):
    """Yield spans from the OTLP JSON resource/scope hierarchy."""

    for resource in payload.get("resourceSpans", []):
        for scope in resource.get("scopeSpans", []):
            yield from scope.get("spans", [])


def _metrics(payload: dict[str, Any]):
    """Yield metrics from the OTLP JSON resource/scope hierarchy."""

    for resource in payload.get("resourceMetrics", []):
        for scope in resource.get("scopeMetrics", []):
            yield from scope.get("metrics", [])


def _metric_timestamps(metric: dict[str, Any]) -> list[int]:
    """Collect point timestamps from whichever OTLP metric data type is present."""

    timestamps: list[int] = []
    for data_type in ("gauge", "sum", "histogram", "summary"):
        for point in metric.get(data_type, {}).get("dataPoints", []):
            timestamps.append(int(point["timeUnixNano"]))
    return timestamps


class ReceiptHandler(BaseHTTPRequestHandler):
    """Accept configured replay requests and expose persisted receipt summaries."""

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        """Serve health or the current receipt file."""

        if self.path == "/healthz":
            self._respond(200, b"healthy\n", "text/plain")
            return
        if self.path == "/receipts":
            payload = RECEIPT_PATH.read_bytes() if RECEIPT_PATH.exists() else b""
            self._respond(200, payload, "application/x-ndjson")
            return
        self._respond(404, b"not found\n", "text/plain")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        """Persist one OTLP JSON trace or metric receipt."""

        if self.path not in {"/v1/traces", "/v1/metrics"}:
            self._respond(404, b"not found\n", "text/plain")
            return
        payload = json.loads(self._body())
        if self.path == "/v1/metrics":
            metrics = list(_metrics(payload))
            self._append(
                {
                    "signal": "metrics",
                    "metric_names": sorted(metric["name"] for metric in metrics),
                    "timestamps": sorted(
                        timestamp
                        for metric in metrics
                        for timestamp in _metric_timestamps(metric)
                    ),
                    "received_at_unix_nano": time.time_ns(),
                }
            )
            self._respond(200, b"{}", "application/json")
            return
        spans = list(_spans(payload))
        self._append(
            {
                "signal": "traces",
                "trace_ids": sorted({span["traceId"] for span in spans}),
                "span_ids": sorted(span["spanId"] for span in spans),
                "starts": sorted(int(span["startTimeUnixNano"]) for span in spans),
                "received_at_unix_nano": time.time_ns(),
            }
        )
        self._respond(200, b"{}", "application/json")

    def log_message(self, message_format: str, *args: Any) -> None:
        """Keep container logs focused on persisted signal receipts."""

    def _body(self) -> bytes:
        """Read the request body using its declared byte length."""

        return self.rfile.read(int(self.headers.get("Content-Length", "0")))

    def _append(self, receipt: dict[str, Any]) -> None:
        """Append and flush one deterministic JSON receipt to the sink file."""

        with RECEIPT_PATH.open("a", encoding="utf-8") as receipt_file:
            receipt_file.write(json.dumps(receipt, sort_keys=True) + "\n")
        print(json.dumps(receipt, sort_keys=True), flush=True)

    def _respond(self, status: int, payload: bytes, content_type: str) -> None:
        """Write one bounded HTTP response."""

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 4318), ReceiptHandler).serve_forever()  # noqa: S104

