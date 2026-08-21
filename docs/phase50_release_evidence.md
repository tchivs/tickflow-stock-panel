# Phase 50 Release Evidence — Replay Workbench Release Hardening (AF-REQ-25 SC5)

**Phase:** 50 — Replay Workbench & Release Hardening
**Requirement:** AF-REQ-25 (SC5 — release hardening: documented smoke evidence)
**Guard:** `backend/tests/test_phase50_guard.py`
**Verified:** 2026-08-09 against `main` (Phases 45–50 complete)

This document is the single release-evidence artifact for SC5. It records the
four documented smoke facts the release gate mechanically proves: the guard
pass, the empty dependency diff, the no-execution runtime proof, and the
research-only action surface. Every claim below is asserted by
`test_phase50_guard.py`.

---

## 1. Guard pass — AST import/call/attr + broker/execution scan

The Phase-50 guard (`test_phase50_guard.py`) mechanically proves the shipped
workbench module graph is research-only over the **union** Phase-50 +
Phase 45–49 Alpha/Agent/promotion set:

- **AST import/call/attr boundary**
  (`TestPhase50ModuleGraphImportBoundary::test_import_boundary_prohibits_execution_imports`,
  `test_import_boundary_prohibits_calls_and_attrs`): no module imports or calls
  a prohibited execution/provider/evaluator/queue collaborator
  (broker/order/position/portfolio/monitor/execution/provider/llm/evaluator/oos/
  redis/kafka/nats/celery), and no arbitrary code path
  (`eval(`/`exec(`/`compile(`/`__import__`/`subprocess.`/`pickle.`/`marshal.`/`ctypes.`).
- **SSE-scoped streaming-token allowance**
  (`TestPhase50ModuleGraphImportBoundary::test_sse_scope_streaming_tokens_only_in_sse_module`):
  streaming tokens (`StreamingResponse`/`text/event-stream`/`EventSourceResponse`/
  `sse_starlette`) are permitted in `api/research_alpha_sse.py` **only**. The
  Phase 45 guard assertion on `research_alpha.py`
  (`test_phase45_guard.py:198-206`) stays **green unamended** because SSE lives
  in the separate Phase-50 file (risk #4 — the Phase 45 boundary is not
  broadened).
- **Broker/execution AST scan**
  (`TestNoExecutionSurfaceImport::test_execution_surface_not_imported`): no
  Alpha/Agent/promotion/workbench module imports the execution surface
  (`app.strategy`/`app.portfolio`/`app.broker`/`app.order`/`app.position`/
  `app.execution`/`app.monitor`).
- **Module-graph completeness**
  (`TestPhase50ModuleGraphCompleteness`): every Phase-50-owned module exists and
  parses; `main.py` wires `research_alpha_sse.router`.

**Result:** PASS — the union module graph is research-only; the Phase 45 and
Phase 49 guards remain green alongside it.

---

## 2. Dependency manifest diff — zero new base runtime dependencies

`TestNoNewBaseDependency::test_no_new_base_dependency_manifest_unchanged` parses
`backend/pyproject.toml` `[project.dependencies]` and asserts the parsed set
equals the frozen Phase-50 baseline captured in the guard. The diff is
**empty** — **zero new base runtime deps** (ROADMAP.md:12 hard constraint).

Phase 55 D-03 removed the SSE transport dep (`sse-starlette`) from the
baseline — all SSE/ndjson code deleted, WebSocket transport replaces it.
The workbench uses native browser WebSocket + React Query already in the tree —
no new npm/Python dependency was introduced.

**Result:** PASS — empty dependency diff (Phase 55 removed sse-starlette).

---

## 3. No-execution runtime proof — `_RaisingFake` across every handler

`TestRuntimeNoExecutionCollaborator` reuses the `_RaisingFake` fake-collaborator
pattern (from `test_phase49_guard.py:208-228`) — a fake that fails the test the
instant any execution-collaborator method is invoked. Raising fakes for
broker/order/position/portfolio/monitor/execution are injected onto the
repository + service, and every new workbench/SSE handler is exercised
end-to-end against a real durable fixture:

- **inspect** — `service.list_lineage` (lineage read projection, SC2)
- **evidence-classification** — `service.candidate_evidence_classification` (SC4)
- **compare** — `service.compare_candidates` (side-by-side, no opaque winner, SC3)
- **stress** — `service.stress_matrix` (Tier-1 pure arithmetic, AF-REQ-20)
- **replay-branch** — `service.replay_branch` (seed re-derivation into a child run, SC2)
- **clone** — `service.clone_run` (overridable manifest dimensions, SC2)
- **stream** — `research_alpha_sse._stream_events` (durable `Last-Event-ID` SSE, SC1)

The SSE generator invokes only read service methods (`list_events`/`get`); it
writes nothing and never reaches a write/create/append execution path.

**Result:** PASS — zero execution-collaborator methods invoked across inspect /
compare / stress / replay-branch / clone / stream.

---

## 4. Research-only action surface

The shipped workbench exposes **only** research-only actions:

| Action | Surface | Execution authority? |
|---|---|---|
| **inspect** | lineage read, evidence-classification | read-only |
| **compare** | side-by-side candidate comparison (no opaque winner) | read-only |
| **replay** | branch replay into a new immutable child run | research run creation |
| **clone** | overridable manifest dimensions into a new run | research run creation |
| **promote** | Phase 49 promotion ticket → immutable FactorRevision | catalog write (research) |

There is **no order / position / portfolio / monitor / live-execution** action.
The workbench cannot place, modify, or cancel an order; it cannot touch a
position, portfolio, or live/monitor surface. Writes flow exclusively through
the durable `run_service` (the sole research lifecycle writer); promotion is the
catalog revision seam (Phase 49), never a broker/order/position/portfolio path.

**Result:** PASS — the action surface is research-only (inspect / compare /
replay / clone / promote); no order, position, portfolio, monitor, or
live-execution surface is reachable.

---

## License

The project is **MIT-licensed** (`LICENSE`). The AGPL-derived-source content
scan (`TestNoAgplDerivedSource`) asserts no Phase-50 module carries
AGPL/AlphaMaster/PA_Agent/affero provenance strings (REQUIREMENTS.md:16,76 —
patterns only, no source copying); MIT headers only.
