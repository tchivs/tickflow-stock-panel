# Phase 50-04 Summary — Release Verification Guard + License/Dep/Execution Scan + Smoke Evidence

**Phase:** 50-replay-workbench
**Plan:** 04 (final wave; runs after 50-01/02/03 — all Alpha/Agent/promotion/SSE/workbench modules exist)
**Requirement:** AF-REQ-25 (SC5 — release hardening: documented smoke evidence)
**Status:** COMPLETE — all four tasks test-first, all verification green

## What landed

The cumulative release-hardening gate for Phase 50 (SC5), modeled on the
established `test_phase{45,49}_guard.py` scaffold. A single
`test_phase50_guard.py` mechanically proves the shipped replay workbench exposes
research-only actions and preserves the no-execution boundary, **and**
re-asserts the prior Phase 45–49 Alpha/Agent/promotion module graph remains
clean. Phase 50 *adds* surfaces; it must not weaken the existing boundary.

### Task 50-04-01 — PHASE50 module set + AST import/call/attr scan + SSE-scoped streaming-token allowance (SC5 a/c/d)
`PHASE50_MODULES` = the new `api/research_alpha_sse.py` **UNION** the Phase 45
Alpha run-contract graph (9 modules) **UNION** the Phase 49 promotion graph
(2 modules) — the lineage/compare/stress/replay/clone/evidence-classification
surfaces landed inside the already-guarded Phase 45 modules, so the only
genuinely new file is `research_alpha_sse.py`. The prohibited-import token set
is the Phase-49 set (`promotion` dropped, since the union includes the
promotion modules). The AST scan asserts no module imports/calls a prohibited
execution/provider/evaluator/queue collaborator or arbitrary code path
(`eval(`/`exec(`/`compile(`/`__import__`/`subprocess.`/`pickle.`/`marshal.`/`ctypes.`).
Streaming tokens (`StreamingResponse`/`text/event-stream`/`EventSourceResponse`/
`sse_starlette`) are permitted in `research_alpha_sse.py` **only** — the Phase 45
assertion on `research_alpha.py` (`test_phase45_guard.py:198-206`) stays **green
unamended** because SSE lives in the separate Phase-50 file (risk #4 — the
Phase 45 boundary is not broadened).

### Task 50-04-02 — broker/execution AST scan + runtime `_RaisingFake` proof (SC5d)
`TestNoExecutionSurfaceImport` AST-scans the union set for imports reaching the
execution engine packages (`app.strategy`/`app.portfolio`/`app.broker`/
`app.order`/`app.position`/`app.execution`/`app.monitor`). `TestRuntimeNoExecutionCollaborator`
reuses `_RaisingFake` (from `test_phase49_guard.py:208-228`), injects raising
broker/order/position/portfolio/monitor/execution fakes onto the repository +
service, and exercises every new handler end-to-end against a real durable
fixture — **inspect** (lineage), **evidence-classification**, **compare**,
**stress**, **replay-branch**, **clone**, and the durable **SSE stream**
(`_stream_events`) — asserting zero execution-collaborator methods are invoked.
The SSE generator invokes only read service methods (`list_events`/`get`).

### Task 50-04-03 — dependency-manifest diff + AGPL-derived-source scan (SC5a/b)
`TestNoNewBaseDependency` parses `backend/pyproject.toml`
`[project.dependencies]` (tomllib) and asserts the parsed set **equals** the
frozen Phase-50 baseline captured in the guard. The diff is **empty** — zero
new base runtime deps (ROADMAP.md:12); `sse-starlette>=2.0` is **pre-existing**
(pyproject.toml:15), deliberately in the baseline. `TestNoAgplDerivedSource`
content-scans the module graph for AGPL/AlphaMaster/PA_Agent/affero provenance
strings (REQUIREMENTS.md:16,76 — patterns only, no source copying) and confirms
the LICENSE is MIT.

### Task 50-04-04 — release-evidence document + test assertion (SC5)
`docs/phase50_release_evidence.md` records the four SC5 documented smoke facts:
guard pass, empty dependency diff, no-execution runtime proof, and the
research-only action surface. `TestReleaseEvidenceDocument` asserts the doc's
existence + required sections (test-first: written red → green).

## Commits

| hash | task | subject |
|---|---|---|
| `a55fe3c` | 50-04-01 | PHASE50 module set + AST import/call/attr boundary + SSE-scoped streaming-token allowance (SC5 a/c/d) |
| `c7ff4d8` | 50-04-02 | broker/execution AST scan + runtime `_RaisingFake` proof across all new handlers (SC5d) |
| `ab72f30` | 50-04-03 | dependency-manifest diff (zero new base deps) + AGPL-derived-source scan (SC5a/b) |
| `cce8be4` | 50-04-04 | release-evidence doc + test-asserted smoke evidence (SC5) |

Each commit used explicit `git add <file>`. `frontend/src/pages/Watchlist.tsx`
was zero-touch (never read, never staged).

## Test totals

- `test_phase50_guard.py`: **79** new tests, all green.
  - T1 import/call/attr boundary + SSE scope + module graph: **50**
  - T2 execution-surface scan + runtime `_RaisingFake` proof: **14**
  - T3 dependency diff + AGPL/license scan: **14**
  - T4 release-evidence document assertion: **1**

## Verification (run, green)

```
# Per-task focused selections (the plan's four -k selectors)
T1 import_boundary|second_database|sse_scope|module_graph : 50 passed
T2 execution_surface|runtime_no_execution|raising_fake     : 14 passed
T3 no_new_base_dependency|agpl|license                     : 14 passed
T4 release_evidence                                        :  1 passed

# Plan verification block — Phase 50 guard AND prior Phase 45/49 guards green
pytest tests/test_phase50_guard.py tests/test_phase45_guard.py \
      tests/test_phase49_guard.py -q   → 141 passed
```

The Phase 50 guard passes **and** the prior Phase 45/49 guards remain green —
Phase 50 adds surfaces without weakening the existing boundary; the Phase 45 SSE
assertion stays green because SSE is in a separate file.

## Deviations from the plan (all benign, documented)

1. **AGPL scan scoped to the module graph (mirrors the Phase 45 Watchlist test).**
   Task 50-04-03's prose named "backend/app/research/**" as the scan surface,
   but `backend/app/research/alpha_factory.py:50` carries a benign design-
   reference comment ("AlphaMaster `FORMULA_VOCAB.verify()` pattern adapted for
   the existing DSL, not StackVM") — exactly the legitimate "patterns only, no
   source copying" case (REQUIREMENTS.md:16,76). Mirroring the Phase 45 guard's
   Watchlist test (`test_phase45_guard.py:190-196`), the scan iterates the
   `PHASE50_MODULES` graph (every Phase-50-owned/extended + re-asserted
   Phase 45–49 module) rather than the whole tree. This is the surface where
   this phase could introduce provenance; `alpha_factory.py` is outside it. No
   weakening: the module-graph scan is mechanically precise and matches the
   import/call/attr scan scope.

2. **Prohibited-import set is the Phase-49 set (`promotion` dropped).** The union
   module graph includes the Phase 49 promotion modules (which legitimately
   import `promotion_service`), so `promotion` cannot be a prohibited token here
   (it would false-positive on `promotion_service.py`/`research_promotion.py`).
   This is exactly the Phase 49 guard's choice; the Phase 45 `promotion` exemption
   for `repository.py` is therefore unnecessary in this guard. No execution/
   second-engine token is exempted.

3. **SSE runtime drain via a disconnect callback.** The durable SSE generator
   polls forever on a non-terminal run, so the runtime proof drains one ledger
   page (the run-creation event) then flips an `is_disconnected` callback to stop
   — exercising the real `list_events`/`get` read path without an infinite loop.

## Non-goals honoured

- No AGPL-derived source; MIT only (content-scan asserted).
- No prohibited new base runtime dependency; `sse-starlette` pre-existing (manifest diff asserted).
- No arbitrary code path (`eval(`/`exec(`/`__import__`/`subprocess.`/`pickle.`/`marshal.`/`ctypes.` — AST asserted).
- No broker/execution import/call in Alpha/Agent/promotion/workbench surfaces (AST + runtime `_RaisingFake` asserted).
- The Phase 45 and Phase 49 guards remain green (SSE scoped to the new file; the Phase 45 SSE assertion is not broadened).
- Zero new runtime deps. `Watchlist.tsx` zero-touch.

## Hand-off

Phase 50 (AF-REQ-18/20/22/24/25) is now complete end-to-end: the replay
workbench projects durable progress, lineage, comparison, stress, and
degradation views through research-only seams (50-01/02/03), and this
release-hardening guard + smoke evidence (50-04) prove the no-execution,
no-new-dep, no-AGPL, MIT-licensed boundary holds. Ready for the phase
verification/summary and milestone close-out.
