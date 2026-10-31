# SignalGenerator Python design

This folder defines the design for a Python successor to
[mp3monster/LogGenerator](https://github.com/mp3monster/LogGenerator). No runtime implementation
should begin until these documents have been reviewed.

## Documents

- [Solution design](solution_design.md): goals, architecture, component boundaries, replay
  semantics, and operational behavior.
- [Configuration design](configuration_design.md): versioned schemas, CLI validation and diagnostics,
  and metrics JSON Lines contracts.
- [Testing and demo strategy](testing_and_demo_strategy.md): unit, integration, container, and NGINX
  metrics demonstration plans.
- [Packaging and release design](packaging_and_release_design.md): TOML metadata, wheel production,
  artifact verification, versioning, and release controls.
- [OpAMP integration design](opamp_integration_design.md): package provenance and dependency
  diagrams, deployment-permutation views, plugin contract, and the separately owned adapter module
  for supervised-process and unified-simulator Quart deployments.
- [Implementation plan](implementation_plan.md): phased delivery, acceptance gates, risks, and
  decisions that must remain visible during implementation.
- [Startup scripts](../scripts/README.md): PowerShell, Windows Command Prompt, and Bash launchers
  for the standalone deployment.
- [Log compatibility](log_compatibility.md): implemented original behavior and deliberate Python
  differences.
- [Migration guide](migration_guide.md): legacy property conversion and upgrade checks.

## Design status

Status: **accepted; implementation in progress through Phase 2**

The design deliberately separates five concerns:

1. Log-event replay compatible with the intent of the original LogGenerator.
2. Deterministic Prometheus metric-frame replay from JSON Lines.
3. Standalone and unified-simulator Quart packaging, health, and container operation.
4. Optional OpAMP process supervision or in-process consumer-simulator attachment through an
   independently built adapter distribution rather than either core package.
5. Enforced test coverage, cyclomatic-complexity limits, reproducible wheels, and a controlled
   release process.

## Source material

- [Original LogGenerator repository](https://github.com/mp3monster/LogGenerator)
- [Original configuration reference](https://github.com/mp3monster/LogGenerator/blob/master/docs/readme.md)
- [OpAMP Observe core repository](https://github.com/opamp-observe/opamp-core)
- [OpAMP consumer plugin loader](https://github.com/opamp-observe/opamp-core/blob/main/consumer/src/opamp_consumer/plugin_loader.py)
- [OpAMP plugin configuration hook](https://github.com/opamp-observe/opamp-core/blob/main/consumer/src/opamp_consumer/plugin_config.py)
- [Consumer simulator design](https://github.com/opamp-observe/opamp-core/blob/main/consumer-sim/simulator_design.md)
- [Vector reference plugin](https://github.com/opamp-observe/opamp-core/blob/main/consumer/src/opamp_consumer/vector/client.py)

