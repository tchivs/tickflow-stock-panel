# API Coverage — Phase 4 Advanced Capabilities

> Full coverage by default. This matrix records the sole external SDK surface actually used by Phase 4. The existing OpenAI-compatible provider remains a Phase 3 service and Phase 4's lifecycle draft adapter is deterministic, so it is not an integrated Phase 4 external surface.

## LangGraph SDK and SQLite Checkpointer

`backend/app/advanced/workflow.py` imports `StateGraph`, `AsyncSqliteSaver`, `interrupt`, and `Command`; the production lifecycle wires the resulting fixed graph. The matrix covers the LangGraph Python SDK together with its installed SQLite checkpointer package.

| capability | decision | reason |
|---|---|---|
| typed StateGraph topology | INTEGRATE | Fixed advanced workflow topology is built with StateGraph. |
| explicit node and edge execution | INTEGRATE | The workflow defines authorize, draft, gate, review, and record nodes. |
| deterministic conditional routing | INTEGRATE | Gate status routes only to review or recorded rejection. |
| async graph invocation | INTEGRATE | PersistentAdvancedGraph invokes the graph through ainvoke. |
| SQLite checkpoint persistence | INTEGRATE | AsyncSqliteSaver persists a per-invocation recovery cursor. |
| server-owned checkpoint thread binding | INTEGRATE | The workflow validates the server-generated thread ID against its job. |
| human interrupt pause | INTEGRATE | interrupt pauses only for the explicit human review decision. |
| Command-based resume | INTEGRATE | Command resume continues an approved or rejected human review. |
| graph state history and time travel | OPT-OUT | Phase 4 uses checkpoints only for recovery; history replay and forking are not user workflows. |
| state mutation and checkpoint forking | OPT-OUT | Immutable SQLite facts, not mutable checkpoint state, are authoritative. |
| nested subgraphs | OPT-OUT | The phase requires one fixed, auditable workflow topology. |
| prebuilt agents and tool calling | OPT-OUT | Authorization, gates, sandboxing, and writes stay in deterministic application services. |
| multi-agent orchestration | OPT-OUT | Phase 4 has one bounded research workflow, not collaborating agents. |
| model-provider integration | OPT-OUT | The wired lifecycle draft adapter is deterministic; no Phase 4 provider SDK call is made. |
| graph streaming | OPT-OUT | Shared SSE emits only committed allowlisted stages, never graph tokens or raw events. |
| managed cloud deployment and remote runtime | OPT-OUT | The phase remains a single-container local deployment with SQLite. |
| external memory or store backends | OPT-OUT | Operational SQLite and governed data boundaries hold the required state. |
| automatic retry policies | OPT-OUT | Retries and terminal outcomes are explicit audited domain transitions. |
