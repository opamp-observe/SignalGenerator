# UML package and deployment architecture

## 1. Purpose and notation

These diagrams show which installable packages belong to SignalGenerator, which come from
`opamp-observe/opamp-core`, and how those packages are deployed in each supported permutation. They
complement the behavioral flows in [solution_design.md](solution_design.md) and the detailed
integration contracts in [opamp_integration_design.md](opamp_integration_design.md).

The diagrams use UML stereotypes inside Mermaid so they render with the rest of the Markdown
documentation. Solid arrows represent package or construction dependencies. Dashed arrows represent
runtime protocols, optional attachment, or supervision rather than package ownership.

| Colour | Ownership or role |
|---|---|
| Blue | SignalGenerator core distribution and runtime |
| Green | Independently built SignalGenerator OpAMP adapter |
| Amber | Consumer packages from `opamp-observe/opamp-core` |
| Purple | Third-party Python packages |
| Grey | External clients or generic runtime infrastructure |
| Red | External OpAMP provider; never a SignalGenerator host |

## 2. UML package dependency diagram

```mermaid
classDiagram
    direction LR

    namespace SignalGeneratorProject {
        class SignalGeneratorCore["signal-generator"] {
            <<distribution>>
            +package signal_generator
            +CLI signal-generator
            +replay runtime
            +optional Quart attachment
        }
        class SignalGeneratorAdapter["signal-generator-opamp-sim"] {
            <<distribution>>
            +package signal_generator_opamp_sim
            +CLI signal-generator-opamp-sim
            +supervised plugin
            +unified Quart composition
        }
    }

    namespace OpAMPObserveCore {
        class OpAMPConsumer["opamp-consumer"] {
            <<distribution>>
            +OpAMP transport
            +plugin API
            +SimulatorOpAMPClient
        }
        class OpAMPConsumerSim["opamp-consumer-sim"] {
            <<distribution>>
            +optional process launcher
            +packaged launcher resources
        }
    }

    namespace ThirdParty {
        class Quart {
            <<distribution>>
            +ASGI application host
        }
        class JsonSchema["jsonschema"] {
            <<distribution>>
            +Draft 2020-12 validation
        }
    }

    class OpAMPProvider["OpAMP provider"] {
        <<external service>>
        +remote configuration
        +custom messages
    }

    SignalGeneratorAdapter --> SignalGeneratorCore : direct dependency
    SignalGeneratorAdapter --> OpAMPConsumer : direct dependency
    OpAMPConsumerSim --> OpAMPConsumer : direct dependency
    SignalGeneratorCore --> JsonSchema : direct dependency
    SignalGeneratorAdapter --> JsonSchema : direct dependency
    SignalGeneratorCore ..> Quart : optional quart extra
    SignalGeneratorAdapter ..> Quart : unified extra
    OpAMPConsumer ..> OpAMPProvider : OpAMP protocol

    style SignalGeneratorCore fill:#dbeafe,stroke:#2563eb,color:#172554,stroke-width:2px
    style SignalGeneratorAdapter fill:#dcfce7,stroke:#16a34a,color:#052e16,stroke-width:2px
    style OpAMPConsumer fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-width:2px
    style OpAMPConsumerSim fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-width:2px
    style Quart fill:#f3e8ff,stroke:#9333ea,color:#3b0764,stroke-width:2px
    style JsonSchema fill:#f3e8ff,stroke:#9333ea,color:#3b0764,stroke-width:2px
    style OpAMPProvider fill:#fee2e2,stroke:#dc2626,color:#450a0a,stroke-width:2px
```

The adapter is part of this repository but remains a separate distribution. Both amber packages are
released from `opamp-observe/opamp-core`, but only `opamp-consumer` is an adapter dependency. The
companion process launcher does not become a SignalGenerator package. The external provider
participates through the OpAMP protocol and is absent from the Python dependency graph.

## 3. UML deployment diagram: standalone utility

```mermaid
flowchart LR
    Scraper["«external client»<br/>Prometheus scraper"]
    Pushgateway["«external service»<br/>Prometheus Pushgateway"]

    subgraph Host["«device» SignalGenerator host"]
        subgraph Process["«executionEnvironment» Python process"]
            Core["«artifact» signal-generator<br/>CLI + SignalGeneratorRuntime"]
            Listener["«component» standalone HTTP listener"]
            Core -->|constructs| Listener
        end
    end

    Scraper -.->|GET /metrics| Listener
    Core -.->|optional scheduled push| Pushgateway

    classDef core fill:#dbeafe,stroke:#2563eb,color:#172554,stroke-width:2px
    classDef external fill:#f1f5f9,stroke:#64748b,color:#0f172a,stroke-width:2px
    class Core,Listener core
    class Scraper,Pushgateway external
    style Host fill:#ffffff,stroke:#64748b,color:#0f172a
    style Process fill:#f8fafc,stroke:#94a3b8,color:#0f172a
```

Only `signal-generator` is required. No adapter, OpAMP consumer package, Quart host, or OpAMP
provider participates in this deployment.

## 4. UML deployment diagram: OpAMP-supervised process

```mermaid
flowchart LR
    Provider["«external service»<br/>OpAMP provider"]
    Scraper["«external client»<br/>Prometheus scraper"]

    subgraph ControlHost["«device» simulator host"]
        subgraph ControlProcess["«executionEnvironment» adapter control process"]
            Adapter["«artifact»<br/>signal-generator-opamp-sim"]
            Consumer["«artifact»<br/>opamp-consumer"]
            Adapter -->|uses plugin API| Consumer
        end

        subgraph ChildProcess["«executionEnvironment» supervised child process"]
            Core["«artifact» signal-generator"]
            Runtime["«component» replay runtime<br/>standalone HTTP listener"]
            Core -->|constructs| Runtime
        end
    end

    Adapter -.->|spawn / validate / health / restart| Core
    Consumer -.->|OpAMP protocol| Provider
    Scraper -.->|GET /metrics| Runtime

    classDef core fill:#dbeafe,stroke:#2563eb,color:#172554,stroke-width:2px
    classDef adapter fill:#dcfce7,stroke:#16a34a,color:#052e16,stroke-width:2px
    classDef opamp fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-width:2px
    classDef external fill:#f1f5f9,stroke:#64748b,color:#0f172a,stroke-width:2px
    classDef provider fill:#fee2e2,stroke:#dc2626,color:#450a0a,stroke-width:2px
    class Core,Runtime core
    class Adapter adapter
    class Consumer opamp
    class Scraper external
    class Provider provider
    style ControlHost fill:#ffffff,stroke:#64748b,color:#0f172a
    style ControlProcess fill:#f8fafc,stroke:#94a3b8,color:#0f172a
    style ChildProcess fill:#f8fafc,stroke:#94a3b8,color:#0f172a
```

This is the only supported two-process permutation. The green adapter owns child lifecycle and
health polling. The amber consumer owns the OpAMP connection; the red provider still does not host
SignalGenerator.

## 5. UML deployment diagram: unified Quart simulator

```mermaid
flowchart LR
    Provider["«external service»<br/>OpAMP provider"]
    Scraper["«external client»<br/>Prometheus scraper"]

    subgraph UnifiedHost["«device» unified simulator host"]
        subgraph UnifiedProcess["«executionEnvironment» one Python process + event loop"]
            Adapter["«artifact»<br/>signal-generator-opamp-sim"]
            Core["«artifact»<br/>signal-generator"]
            Consumer["«artifact»<br/>opamp-consumer"]
            Quart["«artifact» quart"]
            App["«component» unified Quart application"]
            SimulatedClients["«component» simulated OpAMP clients"]
            Runtimes["«component» SignalGenerator runtimes"]

            Adapter -->|constructs| App
            Adapter -->|creates| SimulatedClients
            Adapter -->|attaches| Runtimes
            Core -->|provides| Runtimes
            Consumer -->|provides simulator client + transport| SimulatedClients
            Quart -->|hosts| App
            App -->|owns lifecycle| SimulatedClients
            App -->|owns lifecycle| Runtimes
        end
    end

    SimulatedClients -.->|OpAMP connections| Provider
    Scraper -.->|GET prefixed /metrics route| App

    classDef core fill:#dbeafe,stroke:#2563eb,color:#172554,stroke-width:2px
    classDef adapter fill:#dcfce7,stroke:#16a34a,color:#052e16,stroke-width:2px
    classDef opamp fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-width:2px
    classDef thirdParty fill:#f3e8ff,stroke:#9333ea,color:#3b0764,stroke-width:2px
    classDef external fill:#f1f5f9,stroke:#64748b,color:#0f172a,stroke-width:2px
    classDef provider fill:#fee2e2,stroke:#dc2626,color:#450a0a,stroke-width:2px
    class Core,Runtimes core
    class Adapter,App adapter
    class Consumer,SimulatedClients opamp
    class Quart thirdParty
    class Scraper external
    class Provider provider
    style UnifiedHost fill:#ffffff,stroke:#64748b,color:#0f172a
    style UnifiedProcess fill:#f8fafc,stroke:#94a3b8,color:#0f172a
```

All artifacts share one process, event loop, listener, and coordinated Quart lifecycle. There is no
SignalGenerator child, supervisor, observer, PID polling, or local health polling. The adapter is
the composition root: the blue core and amber simulator packages remain unaware of one another.

## 6. Boundary summary

| Boundary | Allowed dependency direction | Prohibited coupling |
|---|---|---|
| Core and adapter | Adapter depends on core | Core importing adapter or OpAMP packages |
| Adapter and OpAMP consumer | Adapter depends on published consumer APIs | SignalGenerator-specific code in `opamp-core` |
| Optional process launcher and consumer | `opamp-consumer-sim` depends on consumer; adapter does not depend on launcher | Provider embedding SignalGenerator |
| Quart integration | Core exposes optional attachment; adapter composes it | Core requiring Quart for CLI-only use |
| External provider | Consumer communicates over OpAMP | Provider becoming a SignalGenerator deployment mode |

