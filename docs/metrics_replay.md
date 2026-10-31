# Metrics replay operations

## Phase 5 container demonstrations

The checked-in `tests/test-containers/phase5/compose.yaml` provides three independent profiles:

- `pull`: SignalGenerator plus Prometheus `v3.15.1`; the verifier queries Prometheus for
  `nginx_connections_active`.
- `push`: SignalGenerator plus Pushgateway `v1.11.3`; the verifier checks the pushed job and labels.
- `unified`: the separately built OpAMP adapter image plus Prometheus; the scraper targets the
  prefixed in-process runtime route.

Each image healthcheck targets `/healthz`, never `/metrics`, so health polling cannot consume a
frame. See the root README for commands and published host ports.

## Runtime behavior

SignalGenerator reads a UTF-8 JSON Lines source completely before becoming ready. Each non-empty
line is one metric frame. Startup rejects malformed JSON, invalid names or labels, duplicate series,
invalid histogram/summary structures, excessive line/sample counts, and descriptor changes between
frames.

Pull and push use separate cursors over the same immutable frame store:

- a request to the configured pull path consumes exactly one pull frame;
- `/`, `/healthz`, and `/readyz` report in-memory state and never consume a frame;
- the push scheduler reserves one push frame and retains it through every retry;
- only successful push delivery allows the push cursor to reserve its next frame.

The source `eof` policy applies independently to both cursors:

| Policy | Behavior after the last frame |
|---|---|
| `loop` | Return to the first frame. |
| `hold_last` | Continue exposing the final frame. |
| `stop` | Stop returning scenario frames. A push-only scheduler exits. |
| `error` | Report exhaustion as a replay failure. |

## Prometheus pull

Start the checked-in NGINX scenario:

```text
signal-generator validate --config examples/metrics/config.json
signal-generator run --config examples/metrics/config.json
```

The default example listens only on `127.0.0.1:9108`:

| Route | Purpose | Advances pull cursor? |
|---|---|---:|
| `/metrics` | Current NGINX frame and optional `signal_generator_*` diagnostics. | Yes |
| `/healthz` | Process liveness. | No |
| `/readyz` | Source/listener/task readiness. | No |
| `/` | Service and configured metric-path discovery. | No |

The registry is isolated per runtime; default Python process/platform metrics are not included.
The output is Prometheus text format with counter, gauge, untyped, info, histogram, and summary
families supported by the frame schema.

## Scheduled Pushgateway delivery

Enable `metrics.push` and configure `url`, `job`, and `interval_seconds`. The adapter uses HTTP PUT
replacement semantics at the deterministic grouping URL. Grouping-label names and values are URL
escaped.

Basic authentication references its password by environment-variable name:

```json
"basic_auth": {
  "username": "demo",
  "password_env": "SIGNAL_GENERATOR_PUSH_PASSWORD"
}
```

Alternatively, `bearer_token_env` names an environment variable containing a bearer token. The
modes are mutually exclusive and secret values do not appear in effective configuration output.
TLS verification is enabled by default; `tls.ca_file` selects a private CA. Disabling verification
is supported for controlled tests but is not recommended.

Retries use bounded exponential backoff. A frame that exhausts a retry batch remains pending for
the next batch, so a failed push never skips a frame. `use_source_timing: true` uses positive
`observed_at` deltas between successfully delivered frames; otherwise `interval_seconds` controls
the frequency.

## NGINX pull/push container verification

The profile builds the non-root project image, starts Pushgateway 1.11.3, verifies advancing pull
frames, and confirms the pushed NGINX series and grouping labels:

```text
docker compose -f tests/test-containers/metrics/compose.yaml up --build --detach --wait
python tests/test-containers/metrics/verify.py
docker compose -f tests/test-containers/metrics/compose.yaml down --remove-orphans
```

Host test ports are `19108` for SignalGenerator and `19091` for Pushgateway. The standalone image
continues to use port `9108` internally.
