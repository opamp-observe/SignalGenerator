# Trace replay operations

SignalGenerator accepts newline-delimited OTLP JSON trace export requests. Each non-empty line is
one JSON `ExportTraceServiceRequest` with a top-level `resourceSpans` array, matching the JSON
encoding accepted by an OTLP/HTTP `/v1/traces` endpoint. Downloaded capture files such as
`clean-slice.ndjson` can be used directly; source paths resolve relative to the configuration file.

```json
{
  "schema_version": 1,
  "traces": {
    "enabled": true,
    "source": {"path": "clean-slice.ndjson"},
    "replay": {"cycles": 2, "acceleration": 10, "loop_gap_ms": 100},
    "push": {"url": "http://collector:4318/v1/traces", "timeout_seconds": 5}
  }
}
```

## Time shifting and pacing

Before sending anything, SignalGenerator reads the first record and finds its earliest
`startTimeUnixNano`, `endTimeUnixNano`, or event `timeUnixNano`. At the start of each cycle it
calculates one nanosecond delta from that source timestamp to the current wall-clock time. The same
delta is applied to every span start, span end, and event timestamp in every record in that cycle,
so durations and cross-record relationships are preserved.

Records are delivered in file order. The difference between each record's earliest timestamp is
used as its delay; `acceleration` divides those delays. A negative source difference is treated as
no delay, preserving deterministic file order. `loop_gap_ms` is inserted between cycles.

## Loop identity rules

`cycles` is a positive integer or `"forever"`. Every cycle, including the first, replaces trace and
span identities with non-zero lowercase hexadecimal OTLP IDs (32 characters for trace IDs and 16
for span IDs). One mapping is shared across the complete cycle, so `parentSpanId` and link
references continue to point to the corresponding rewritten span and trace. A new mapping is
created for the next cycle, preventing collectors from merging repeated data into the prior trace.

## Validation and limits

`validate` reads the complete source, applies `maximum_line_bytes` (10 MiB by default), rejects
invalid JSON, and requires every record to contain `resourceSpans` and at least one OTLP timestamp.
The endpoint must use HTTP or HTTPS. Delivery uses OTLP/HTTP JSON (`Content-Type:
application/json`) and treats a non-success response as a replay failure.

The synchronized container test sends looping traces and metric frames to one file-backed dummy
receiver:

```text
docker compose -f tests/test-containers/otel-replay/compose.yaml up --build --detach --wait
python tests/test-containers/otel-replay/verify.py
docker compose -f tests/test-containers/otel-replay/compose.yaml down --remove-orphans --volumes
```

The receiver writes one JSON summary per request to `/tmp/otel-receipts.ndjson` inside its
container and also exposes those summaries at `http://127.0.0.1:14318/receipts` for verification.

