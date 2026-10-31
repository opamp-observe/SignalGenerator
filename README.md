# SignalGenerator Python

SignalGenerator replays log events from deterministic source files. The project is an enhanced
Python successor to [mp3monster/LogGenerator](https://github.com/mp3monster/LogGenerator), with
Prometheus metric replay planned in later phases.

The implemented CLI currently supports configuration validation, effective-configuration output,
legacy property conversion, and Phase 2 log replay. See [the design index](docs/index.md) and the
[startup script guide](scripts/README.md).

```text
signal-generator validate --config examples/logs/basic/config.json
signal-generator run --config examples/logs/basic/config.json
```
