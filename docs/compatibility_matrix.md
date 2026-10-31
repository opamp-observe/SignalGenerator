# Compatibility matrix

## Released package compatibility

| Component | Version | Supported Python | Required peer range | Quart usage |
|---|---|---|---|---|
| `signal-generator` | 0.1.x | 3.10–3.13 | — | Optional `quart` extra |
| `signal-generator-opamp-sim` | 0.1.x | 3.10–3.13 | `signal-generator >=0.1,<0.2` | Only the `unified` extra |
| `opamp-consumer` | 0.6.x | 3.10–3.13 | Adapter requires `>=0.6,<0.7` | Not required by base adapter |
| Quart | 0.19 or later | As supported by Quart | Optional for core; required for unified mode | One worker |

The adapter and core have independent versions. A compatible range means the public API and schema
contract is supported; it does not mean every package must be released together.

## Deployment compatibility

| Deployment | Packages | Process model | Supported |
|---|---|---|---|
| Standalone | `signal-generator` | One SignalGenerator process | Yes |
| Embedded library | `signal-generator[quart]` plus host | Host owns lifecycle and listener | Yes |
| OpAMP supervised | Base adapter plus OpAMP consumer | Consumer supervises a child process | Yes |
| OpAMP unified Quart | Adapter `unified` extra plus `opamp-consumer` | One process, listener, worker, and event loop | Yes |
| Built into OpAMP provider | None | Provider-owned | No |

## Compatibility change policy

- Patch releases preserve the CLI, JSON schemas, plugin entry point, and public runtime API.
- Minor releases may add optional keys and capabilities but preserve existing valid configuration.
- Major releases may change replay semantics or remove configuration and require migration notes.
- Candidate adapter CI installs the lower and upper supported dependency lines before publication.
- The OpAMP provider remains outside the dependency graph and is not changed by this integration.
