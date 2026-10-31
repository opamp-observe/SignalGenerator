# SignalGenerator OpAMP simulator adapter

This independently built distribution connects the public `signal-generator`, `opamp-consumer`,
and `opamp-consumer-sim` APIs. It does not add SignalGenerator code to `opamp-core`, and it never
changes the OpAMP provider.

## Deployment modes

1. `supervised`: the installed `opamp_consumer.plugins` entry point represents a separately running
   SignalGenerator child as a distinct OpAMP agent. Health checks use `/healthz`, never `/metrics`.
2. `unified_quart`: simulated OpAMP clients and one or more SignalGenerator runtimes share one
   process, event loop, Quart listener, and worker. There is no SignalGenerator subprocess or
   supervisor/observer relationship in this mode.

The simulator is development-only. Set `APP_ENABLE_DEV_FEATURES=true` before starting unified mode.

## Build and install

Build this package separately from its directory:

```bash
python -m build
python -m pip install "dist/signal_generator_opamp_sim-0.1.0-py3-none-any.whl[unified]"
```

For a source checkout, first build or install the three first-party dependencies. The base adapter
does not declare Quart or Hypercorn; the `unified` extra adds those host dependencies.

`requirements.lock` records the tested direct runtime versions. First-party wheels should be
supplied from the release wheelhouse rather than a sibling source-directory import.

## Validate and run

```bash
signal-generator-opamp-sim validate --config examples/opamp/unified-config.json
signal-generator-opamp-sim validate --config examples/opamp/unified-config.json --format json
signal-generator-opamp-sim validate --config examples/opamp/unified-config.json --schema-only
signal-generator-opamp-sim unified --config examples/opamp/unified-config.json
```

Validation is side-effect-free: it does not bind Quart, connect an OpAMP client, or start a child.
Full validation checks all referenced SignalGenerator scenarios, consumer configurations, and
scripted response plans. Relative paths resolve from the adapter configuration file.

Unified routes are:

- `/healthz` for process liveness;
- `/readyz` for aggregate readiness;
- `/api/simulator/instances` for development state;
- each runtime's configured prefix with `/metrics`, `/healthz`, and `/readyz`.

Metric health polling is passive and cannot advance a replay cursor. A scrape of a prefixed
`/metrics` route advances only that runtime's pull cursor.

## Restart and remote configuration

Unified restart is logical: the adapter stops and awaits owned tasks, validates the candidate in
memory, applies it, and starts new task/cursor state on the existing event loop. Invalid candidates
leave the active runtime unchanged; startup failure rolls back to the previous typed configuration.
Shared runtimes are changed only through their explicit runtime ID.

Supervised remote configuration validates the received JSON before the shared OpAMP file
replacement lifecycle writes it. The plugin launches argv directly with no shell and uses bounded
terminate-then-kill shutdown.

## Compatibility

| Distribution | Supported range |
|---|---|
| `signal-generator` | `>=0.1.0,<0.2.0` |
| `opamp-consumer` | `>=0.6.0,<0.7.0` |
| `opamp-consumer-sim` | `>=0.6.0,<0.7.0` |
| Python | `>=3.10` |

The unified host enforces one worker. Multiple workers would duplicate replay cursors and simulated
agent identities.
