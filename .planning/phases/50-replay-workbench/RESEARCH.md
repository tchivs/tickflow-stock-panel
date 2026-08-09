# Phase 50 Research: Replay Workbench & Release Hardening

**Phase:** 50 — Replay Workbench & Release Hardening
**Requirements:** AF-REQ-18, AF-REQ-20, AF-REQ-22, AF-REQ-24, AF-REQ-25
**Research flag:** NO dedicated research phase (ROADMAP.md:169). This document is
**implementation verification**, not greenfield design: it audits what Phases 45–49
already expose, names the concrete gaps each Success Criterion must close, and fixes
the contract for new SSE / lineage / compare / stress / guard surfaces.

---

## Verdict (TL;DR)

Phase 50 is a **projection + guard layer**, not a new engine. ~75% of the data it
needs already exists as durable, server-owned facts from Phases 45–49. The real work
is five additive seams:

1. **Durable Last-Event-ID SSE stream** over the existing monotonic event ledger (the
   current `walkforward_sse.py` replays *everything* on reconnect — it ignores
   `Last-Event-ID`; SC1 needs resume-from-`seq+1`).
2. **Lineage READ API** — `append_candidate_lineage` is **write-only** today; no read
   method exists. SC2 needs a read projection over `research_alpha_candidate_lineage`.
3. **Clone + branch-replay** built on `AlphaFactory.replay_to(k)` and the immutable
   snapshot; `create()` already rejects digest-changing mutation, so clone = create
   with declared overrides (the "unchanged inputs keep their hashes" property is free).
4. **Stress-matrix + comparison projection** — fold evidence, cost diagnostics, and
   admission verdicts exist; SC3 needs a read-only projection that assembles them
   side-by-side and a bounded read-only re-evaluation path for declared stress axes
   (no admission-threshold touch).
5. **Release-hardening guard test** — extend the `test_phase{45,49}_guard.py` AST/regex
   pattern to a Phase-50 module set; the Phase 45 guard **explicitly defers SSE to
   Phase 50** (`test_phase45_guard.py:201`), so it must be amended, not just added to.

**Zero new runtime deps.** `sse-starlette>=2.0` is already a base dep
(`pyproject.toml:15`); the workbench uses native `EventSource` + React Query already
in the tree.

---

## Q1 — Durable monotonic SSE replay (SC1, AF-REQ-18 partial)

### What exists today

| Capability | Evidence |
|---|---|
| Monotonic per-run event `seq`, allocated under `BEGIN IMMEDIATE` over `last_event_seq+1` (no `MAX(seq)` race, no gaps/dupes) | `repository.py:1939`, `:2269-2273`, `:2308-2351` |
| Paginated event replay from a sequence: `after_seq` + `limit`, returns events `seq > after_seq ORDER BY seq` | `repository.py:2180-2202` |
| Service replay with continuation markers (`next_sequence`, `truncated`) | `run_service.py:459-491` |
| REST replay endpoint (`after_sequence` Query, `events_after_sequence`, `next_sequence`) | `research_alpha.py:99-125` |
| REST events list with `X-Next-Sequence` cursor header | `research_alpha.py:197-216` |
| Existing SSE endpoint (`/api/research/wf/plans/{id}/stream`) | `walkforward_sse.py:145-188` |
| Native `EventSource` consumer (auto-sends `Last-Event-ID` on reconnect) | `WalkForward.tsx:30,36-54` |

### The gap (the only non-trivial SSE work)

The walk-forward SSE stream **replays from cursor 0 every reconnect**
(`walkforward_sse.py:168` — `cursor = 0`). It is in-memory, module-level, TTL 300s,
and ignores `Last-Event-ID`. That is acceptable for a short fold simulation but
**fails SC1** ("without missing, duplicating, or inventing events; reconnect/restart
never becomes UI authority") for long-lived Alpha runs that may survive a process
restart. SC1 requires resume-from-`last_event_seq+1`.

Native browser `EventSource` already sends the `Last-Event-ID` request header on every
reconnect — **the client side is done**; the gap is purely server-side honoring of it.

### Design (durable, restart-safe)

New endpoint **`GET /api/research/alpha/runs/{run_id}/stream`** in a new module
`app/api/research_alpha_sse.py` (sibling to `research_alpha.py`, same router prefix):

- Resolve `Last-Event-ID` header (FastAPI `Request.headers.get("last-event-id")`).
  If present and a valid int `k`, start from `after_seq = k`; else `after_seq = 0`.
- Generator: poll `service.list_events(run_id, after_seq=cursor, limit=N)` (the
  **durable SQLite ledger**, not a module-level dict), emit one SSE event per row
  with `id: <seq>` + `event: <event_type>` + `data: <projected event>`, advance
  `cursor = last_seq`, keepalive (`: ping`) on empty polls, terminate on a terminal
  run status (`completed`/`failed`/`cancelled`) by reading `service.get(run_id)`.
- **No module-level state** — every cursor position is recovered from the durable
  ledger, so a server restart mid-stream resumes exactly where the client's last
  acknowledged `seq` left off. This is the decisive difference from `walkforward_sse.py`.
- Bounded polling fallback: if the stream is unavailable or the client cannot use SSE,
  the existing `GET /runs/{id}/progress` (`research_alpha.py:243-256`, four counters)
  and `GET /runs/{id}/events?after_sequence=` remain the bounded-poll path. SC1 is
  "SSE *or* bounded polling" — both already exist; SSE just needs the cursor.

**Concurrency:** the generator only *reads* the append-only ledger; writes still go
through `run_service` (the sole lifecycle writer, `run_service.py:1-12`). No new write
authority is introduced — SC1 "reconnect/restart never becomes UI authority."

### Precedent to amend

`test_phase45_guard.py:198-206` asserts `StreamingResponse`/`text/event-stream` are
**absent** from `research_alpha.py` ("out of scope (Phase 50)"). Phase 50 lands SSE in
a *new* file (`research_alpha_sse.py`), so the Phase 45 guard stays green; the Phase 50
guard (Q5) instead asserts the stream module owns no execution authority.

---

## Q2 — Lineage inspection, branch replay, clone (SC2, AF-REQ-18)

### What exists today

| Capability | Evidence |
|---|---|
| Lineage **append** with child/parent/edge_ordinal/operation, atomic attempt fence, same-run FK enforced | `repository.py:2447-2509`, `run_service.py:599-622` |
| Lineage table: append-only (no UPDATE/DELETE triggers), child + parent indexes | `migrations.py:1972-1987` |
| Deterministic re-derivation: `AlphaFactory.replay_to(k)` rebuilds a fresh factory from the frozen seed, equal to the live prefix for any `k` | `alpha_factory.py:349-365` |
| `GenerationResult`: `step, operation, canonical_expression, parent_steps, seed, digest, attempt_ordinal` | `alpha_factory.py:201-230` |
| Candidate rows store `canonical_expression, operation, seed, step, status, candidate_digest, dsl_version` | `projections.py:91-104` |
| Immutable snapshot + manifest; digest-changing mutation creates a new run | `run_service.py:107-147`, `run_contract.py:160-162` |

### The gap

**There is NO lineage READ method.** `append_candidate_lineage`
(`repository.py:2447`) is write-only; nothing queries
`research_alpha_candidate_lineage` for display. SC2's "inspect parent-to-child
mutation/crossover lineage, canonical expression diffs, seed/step" has no read path.

`AlphaFactory.replay_to(k)` exists but is a **generation** primitive — it reproduces
candidates, it does not "replay one branch as a new run." Branch replay and clone are
new run-creation flows built on the existing immutable `create()`.

### Design

**(a) Lineage READ** — add `repository.list_run_lineage(run_id, *, principal)` and
`service.list_lineage(run_id, *, principal)` returning ordered edges joined to their
child/parent candidate rows (canonical_expression, operation, seed, step, status). Add
a deny-by-default `projections.lineage(edge, child, parent)` exposing only the
bounded fields (mirror `projections.candidate`). Endpoint:
`GET /api/research/alpha/runs/{run_id}/lineage` → `AlphaLineageDTO`.

**(b) Expression diffs** — pure projection: for a parent→child edge, diff the two
`canonical_expression` strings (token-level diff over the canonical DSL form). No new
storage; both expressions are already on the candidate rows.

**(c) Branch replay** — `POST /api/research/alpha/runs/{run_id}/replay-branch` with a
bounded body `{parent_step: int, max_candidates: int}`. The handler: read the frozen
snapshot + seed, call `AlphaFactory(seed).replay_to(parent_step+1)` to re-establish the
PRNG frontier, then continue generation into a **new immutable child run** via the
existing `run_worker`/`run_service` path (same as a normal run, sharing the parent's
frozen inputs). Because generation is deterministic, "replay one branch under the same
frozen inputs" is exactly the seed re-derivation contract already proven in
`alpha_factory.py:349-365`. The child run records its own lineage pointing back to the
parent run's candidates.

**(d) Clone completed run** — `POST /api/research/alpha/runs/{run_id}/clone` with a
bounded `{overrides: mapping}` body. Handler: read the parent's frozen manifest,
deep-merge only the declared override dimensions, and call `service.create()` with the
resulting manifest. The existing digest idempotency gives the SC2 guarantee for free:
**unchanged inputs hash identically** (same sub-digests), a *changed* dimension
changes the canonical digest and produces a new run (never mutates the parent,
`run_contract.py:160-162`). A `GET .../compare-clones?run_id=a&run_id=b` projection
shows field-level diffs + parent/child manifest hashes (reuse `projections.snapshot`).

---

## Q3 — Candidate comparison + stress matrix (SC3, AF-REQ-22, AF-REQ-20)

### What exists today

| Capability | Evidence |
|---|---|
| Per-fold evidence: IC/RankIC/ICIR/coverage/monthly robustness/group-stats + `declared_fingerprints` + `stats`, INSERT-only | `repository.py:1185-1310` (`append/find/list_alpha_fold_evidence`) |
| Cost/turnover diagnostic (single frozen config): turnover_per_rebalance, total_turnover, cost_rate, cost_drag, net_long_short_return — **diagnostic, not execution P&L** | `evaluation.py:105-168` |
| Admission verdicts with per-gate observed value/threshold/reason; `gate_trail_digest` | `admission.py`, `promotion_service.py:67-72` |
| Diversity/redundancy: field/operator overlap, IC-series correlation, structural signature, `most_similar_step` | `alpha_factory.py:889-924` |
| Fold evidence labels: `selection_fold` vs `selection_oos` (consumed exactly once) | `alpha_scoring.py:708-730` |
| Manifest freezes scoring + costs (`scoring.rebalance/n_groups/warmup_days`, `costs.commission/stamp/slippage_bps`) | `run_contract.py:155-198` |

### The gap

There is **no side-by-side comparison projection** and **no stress-trial concept**.
SC3 ("compare candidate families + experiment snapshots side by side ... no opaque
hidden winner") and AF-REQ-20 ("stress matrix across declared rebalance/fee/slippage/
calendar-regime/coverage/symbol-subset ... without rewriting admission thresholds")
need new read projections and a bounded read-only stress path.

### Design

**(a) Comparison projection** — `GET /api/research/alpha/runs/{run_id}/compare?candidates=a,b,c`
returns, per candidate: config (canonical_expression, seed/step/operation), per-fold
evidence (`list_alpha_fold_evidence`), admission verdict + gate trail, artifact refs,
and diversity/redundancy outcome — **all values exposed equally**, so there is never an
opaque single "winner score" (SC3). A cross-run variant
`?run_id=a&run_id=b` compares retained experiment snapshots (snapshots already carry
identical fingerprint fields, `projections.snapshot`, so cross-run config/evidence
comparison is a pure join). The `FactorRevision`/catalog rows from Phase 49 are the
"retained experiment snapshot" source.

**(b) Stress matrix** — AF-REQ-20 requires evaluating a candidate family under
**declared** stress axes. Two design tiers:

- **Tier 1 (read-only assembly, no new compute):** the existing `cost_diagnostics`
  already varies with `rebalance` and `costs` (`evaluation.py:109`); a "stress matrix"
  view that re-projects the *frozen* evidence under alternative declared cost/rebalance
  assumptions is a pure arithmetic projection (recompute `cost_drag` at alt rates over
  the stored `turnover_per_rebalance`). This satisfies fee/slippage and rebalance axes
  with **zero recomputation of factor values**.
- **Tier 2 (bounded read-only re-evaluation):** for calendar-regime / coverage /
  symbol-subset axes, the candidate must be re-scored through the shared
  `FactorSignalChain` under a declared sub-window or sub-universe. This is a **new
  append-only stress-trial table** (`research_alpha_stress_trials`: run_id,
  candidate_digest, axis, variant, evidence_artifact_id, created_at — INSERT-only,
  no admission write) whose results are labeled `stress` (never `selection_oos`,
  never re-entering admission). Admission thresholds are untouched by construction:
  stress trials record observed values only (mirrors `cost_diagnostics`'s
  "diagnostic, not P&L" boundary, `evaluation.py:111-124`).

**Recommendation:** Tier 1 first (covers fee/slippage/rebalance — the data already
exists); Tier 2 (calendar-regime/coverage/symbol-subset) as a follow-up task with the
stress-trial table. Both stay read-only w.r.t. admission.

---

## Q4 — Temporal / degradation labels (SC4, AF-REQ-24)

### What exists today

Every data-quality signal SC4 needs is **already a declared fingerprint** on the
frozen snapshot or fold evidence:

| SC4 label | Source |
|---|---|
| data date | `measured_window.start/end/calendar` (`projections.snapshot:55`) |
| source/provider | `source_field` fingerprint in `declared_fingerprints` (`signal_chain.py:352-396`) |
| cache/degradation | `panel`, `partition`, `data` fingerprints (`projections.snapshot:48-53`); missing/suspended/stale/source_quality excluded counts in `declared_fingerprints.missing_data` (`signal_chain.py:369-371`) |
| missing fields | `required_source_fields` + `declared_fingerprints` (`signal_chain.py:65-66`) |
| membership coverage | `membership_fingerprint` + resolved universe coverage (`projections.snapshot:50`, `signal_chain.py:78-83`) |
| exploratory vs selection-fold vs `selection_oos` | fold evidence `fold_index` + candidate status `selection_oos` (`alpha_scoring.py:708-730`); promotion ticket `selection_oos_status` (`promotion_service.py:67-72`) |
| unavailable final-blind | explicit non-goal (ROADMAP.md:171); UI must label it *unavailable*, never fake it |

### The gap

No frontend **data-quality banner** surfaces these. The values exist but are not
projected into a single "evidence classification" the UI can render as
clean / stale / partial / blocked / fixture.

### Design

Add a deny-by-default `projections.evidence_classification(snapshot, candidate,
fold_evidence, fixture_flag)` returning a bounded classification record:
`{data_date, source_label, cache_state (fresh/stale/degraded), missing_fields[],
membership_coverage (0..1), evidence_role (exploratory|selection_fold|selection_oos|
final_blind_unavailable), fixture (bool), clean (bool)}`. The `clean` flag is false
iff any of: stale/degraded cache, non-empty missing_fields, low coverage, fixture, or
`final_blind_unavailable`. The Agent fixture path already labels itself
(`REQUIREMENTS.md` AF-REQ-26); the projection propagates that label. Endpoint:
embed in the candidate/evidence responses or a dedicated
`GET /runs/{id}/candidates/{cid}/evidence-classification`.

The guardrail is the SC4 invariant: **stale/partial/blocked/fixture results cannot
look like clean production** — enforced by the `clean` boolean the UI binds the banner
to (red = not clean).

---

## Q5 — Release hardening (SC5, AF-REQ-25)

### What exists today

| Check | Evidence |
|---|---|
| Per-phase AST/import boundary guard: prohibited tokens (broker, order, position, portfolio, monitor, execution, provider, llm, evaluator, oos, redis/kafka/nats/celery), prohibited calls (`eval(`/`exec(`/`__import__`/`place_order`...), prohibited attrs (`subprocess.`/`pickle.`/`marshal.`/`ctypes.`) | `test_phase45_guard.py:48-90`, `test_phase49_guard.py:52-90` |
| Promotion-module import allowlist (may import only factor_registry/catalog/run_contract/admission/repository) | `test_phase49_guard.py:95-100` |
| Runtime fake-collaborator proof (execution collaborator raises if called) | `test_phase45_guard.py:222-422`, `test_phase49_guard.py:208-390` |
| License: MIT (`LICENSE:1`); deps pinned in `pyproject.toml` (`sse-starlette>=2.0` already base) | `LICENSE`, `pyproject.toml:8-39` |
| CI release workflow | manual `workflow_dispatch`, builds only — **does not run tests/guards** | `release.yml` |

### The gap

SC5 wants **documented smoke evidence** proving (a) no AGPL-derived source, (b) no
prohibited new base runtime dep, (c) no arbitrary code path, (d) no broker/execution
import/call in Alpha/Agent/promotion. Today these checks are scattered across two
per-phase guards; Phase 50 needs a **single Phase-50 guard + a release-evidence doc
generator**.

### Design

New `tests/test_phase50_guard.py` following the established pattern:

1. **Module set:** the new SSE + projection modules (`api/research_alpha_sse.py`,
   any new `projections`/`lineage`/`compare` functions, the stress-trial module if
   Tier 2 lands) + re-assert the Alpha/Agent/promotion modules (Phase 45–49 set)
   remain clean. Phase 50 *adds* surfaces; it must not weaken the prior boundary.
2. **Prohibited import/call/attr scan** — reuse the Phase 45 token regex
   (`test_phase45_guard.py:48-90`) over the union module set. The SSE module *must*
   import `StreamingResponse`/`text/event-stream`, so unlike Phase 45 these are
   permitted tokens *in the SSE module only* (the Phase 45 guard stays scoped to its
   own module set, `test_phase45_guard.py:200`).
3. **Broker/execution scan** — extend the AST walk to assert no Alpha/Agent/promotion/
   workbench module imports or calls anything from the execution surface
   (`portfolio/`, `strategy/` engine, broker, order). This is the exact SC5 clause.
4. **Dependency check** — parse `pyproject.toml [project.dependencies]` and assert the
   Phase-50 base set is unchanged (no new base runtime dep); `sse-starlette` is the
   pre-existing SSE dep, not new. Zero new deps is a hard constraint (ROADMAP.md:12).
5. **AGPL source scan** — a content scan over `backend/app/research/**` and the new
   workbench modules asserting no file header/body carries AGPL/AlphaMaster/PA_Agent
   provenance strings (REQUIREMENTS.md:19,76). MIT headers only.
6. **Smoke-evidence doc** — a test that *generates* (or asserts the existence of)
   `docs/phase50_release_evidence.md` recording: the guard pass, the dependency
   manifest diff (empty), the no-execution runtime proof, and the research-only action
   surface (inspect/compare/replay/clone/promote — no order/position/portfolio).
   This is the "documented smoke evidence" SC5 names.

The runtime fake-collaborator pattern (`_RaisingFake`,
`test_phase49_guard.py:208-228`) is reused: inject a raising fake into every new
workbench/SSE handler and assert no execution collaborator is touched across
inspect/compare/replay/clone/stream.

---

## Q6 — Frontend workbench (UI hint: yes)

### What exists today

| Pattern | Evidence |
|---|---|
| React Router, lazy pages, route table | `router.tsx:1-114` |
| React Query (`@tanstack/react-query`) for server state | `AdvancedResearchPanels.tsx:2-90` |
| `request<T>(path, init)` fetcher with typed error + toast | `api.ts:22-52` |
| Native `EventSource` SSE consumer with reconnect state | `WalkForward.tsx:21,30-54` |
| Page shell pattern (status chips, sections) | `WalkForward.tsx:94-102` |

### Design

New page **`frontend/src/pages/backtest/AlphaWorkbench.tsx`** (sibling to
`WalkForward.tsx`) + route `{ path: 'backtest/alpha-workbench', element: <AlphaWorkbench /> }`
in `router.tsx`. Sub-views (tabs, single page):

- **Runs list + live progress** — React Query for `GET /runs` + `GET /runs/{id}/progress`;
  native `EventSource` on `GET /runs/{id}/stream` honoring `Last-Event-ID` (auto), with
  the `idle|running|done|error|reconnecting` chip pattern from `WalkForward.tsx:11,94`.
- **Lineage tree** — `GET /runs/{id}/lineage` rendered as parent→child graph with
  expression diffs + seed/step + branch-replay/clone actions.
- **Compare panel** — `GET /runs/{id}/compare?candidates=...` side-by-side evidence +
  gate trail + stress matrix (Tier 1 projection first).
- **Data-quality banner** — binds `evidence_classification` (Q4): red banner when
  `clean=false`, with the specific reason (stale/partial/fixture/unavailable-blind).

**Watchlist.tsx is zero-touch** (explicit non-goal, ROADMAP.md:171). The new page
imports nothing from `Watchlist.tsx`; the Phase 50 guard asserts no Watchlist
reference leaks into the new modules (mirror `test_phase45_guard.py:190-196`).

---

## Q7 — Recommended plan split

Three to four plans, dependency-ordered. **Wave 1** is the foundation (SSE + lineage
read + release guard); **Wave 2** depends on Wave 1's read APIs.

### 50-01 — Durable SSE stream + lineage/evidence read APIs (Wave 1)
- `GET /api/research/alpha/runs/{id}/stream` (Last-Event-ID resume, durable ledger, no module state).
- `repository.list_run_lineage` + `service.list_lineage` + `projections.lineage` + `GET /runs/{id}/lineage`.
- `projections.evidence_classification` + the SC4 `clean` flag.
- Amend `test_phase45_guard.py` scope note (SSE now lives in a Phase-50 file, not `research_alpha.py`).
- **SCs covered:** SC1 (SSE), part of SC2 (lineage read), SC4 (labels data).

### 50-02 — Compare, branch replay, clone, stress matrix (Wave 2, blocked on 50-01)
- `GET /runs/{id}/compare?candidates=...` (config + evidence + gates + diversity, no opaque winner).
- `POST /runs/{id}/replay-branch` (seed re-derivation → new child run) and `POST /runs/{id}/clone` (manifest overrides → `create()`).
- Tier-1 stress projection (fee/slippage/rebalance, pure arithmetic over stored turnover).
- Optional Tier-2 `research_alpha_stress_trials` table + read-only re-evaluation (calendar-regime/coverage/symbol-subset).
- **SCs covered:** SC2 (replay/clone/diffs), SC3 (compare + stress).

### 50-03 — Frontend workbench page (Wave 2, blocked on 50-01 + 50-02 contracts)
- `AlphaWorkbench.tsx` + route + React Query hooks + `EventSource` stream + lineage tree + compare panel + data-quality banner.
- `api.ts` typed fetchers for the new endpoints.
- **SCs covered:** SC1–SC4 (the UI projection of all backend seams). Watchlist zero-touch.

### 50-04 — Release hardening + smoke evidence (Wave 1 or parallel)
- `tests/test_phase50_guard.py`: AST/import/call/attr scan over new + prior module set; broker/execution scan; dependency-manifest diff assertion; AGPL-source scan.
- Runtime fake-collaborator proof across all new handlers.
- `docs/phase50_release_evidence.md` generator/assertion.
- **SC covered:** SC5.

---

## Risks

1. **SSE backpressure on long runs.** The generator polls the ledger every keepalive
   interval; a very long event tail could stall a single connection. Mitigation: bound
   the in-flight event page (`limit`), emit `id:` per event so a dropped client resumes
   precisely, and rely on the existing terminal-status termination.
2. **Branch-replay determinism across worker timing.** `replay_to(k)` is proven
   single-threaded (`alpha_factory.py:349-365`); branch replay must reuse the *same*
   token-fenced worker path so parallelism cannot change the candidate stream
   (`alpha_factory.py:1093-1214`). Do not introduce a second generation path.
3. **Stress matrix drifting into admission.** Tier-2 stress trials must never write
   admission verdicts or be labeled `selection_oos`. The stress-trial table is
   INSERT-only with a `stress` label and no gate-threshold write; guard test asserts it.
4. **SSE module and the Phase 45 guard.** The Phase 45 guard forbids SSE in
   `research_alpha.py` specifically (`test_phase45_guard.py:200-206`). Keep SSE in a
   *separate* file so Phase 45 stays green; do not edit `research_alpha.py` to add the
   stream, and do not broaden the Phase 45 assertion.
5. **Clone digest surprises.** A clone that overrides a dimension must change the
   canonical digest (else idempotency returns the parent). Verify overrides actually
   perturb a digested field, or the clone silently returns the parent run.

## Confidence

**High.** All five Success Criteria map to either (a) existing durable facts needing a
read projection, or (b) a single new durable seam (SSE cursor, lineage read, stress
trial) with a clear precedent in the codebase. No new base dependency, no second
transport, no new engine, no execution authority — every design decision above stays
inside the ROADMAP locked boundaries. The only item needing a judgment call is the
Tier-2 stress-trial table scope (Q3), which can be deferred without blocking SC3's
Tier-1 fee/slippage/rebalance comparison.

---

*Researched 2026-08-09 — Phase 50 implementation verification. All file:line citations
refer to the current `main` (Phases 45–49 complete).*
