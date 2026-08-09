# Phase 50-01 Summary — SSE Replay Stream + Lineage Read API + Temporal/Degradation Labels

**Phase:** 50-replay-workbench
**Plan:** 01 (Wave 1)
**Requirements:** AF-REQ-18 (SC1 durable SSE, SC2 lineage read), AF-REQ-24 (SC4 degradation labels)
**Status:** ✅ Complete — all 4 tasks test-first, verification green
**Executed:** 2026-08-09

---

## Commits

| Hash | Task | Message |
|---|---|---|
| `2a18c1b` | 50-01-01 | repository.list_run_lineage + service.list_lineage read projection (SC2 read half) |
| `276d18a` | 50-01-02 | projections.lineage + evidence_classification + DTOs (SC2/SC4) |
| `331cdf3` | 50-01-03 | GET /runs/{id}/lineage + evidence-classification endpoints (SC2/SC4) |
| `43d69d6` | 50-01-04 | durable Last-Event-ID SSE stream over the monotonic event ledger (SC1) |

---

## What shipped

### SC1 — Durable Last-Event-ID SSE stream (`research_alpha_sse.py`, NEW module)
- `GET /api/research/alpha/runs/{run_id}/stream` via `sse_starlette.EventSourceResponse`.
- **Zero module-level mutable state** — the cursor is recovered from the durable
  SQLite ledger via the `Last-Event-ID` header (native `EventSource` sends it on
  every reconnect). A server restart mid-stream resumes exactly where the client's
  last-acknowledged `seq` left off.
- Fresh connect emits every event from seq 1 (`id=<seq>`, `event=<event_type>`).
- `Last-Event-ID: k` reconnect resumes from seq `k+1` (no dup, no gap).
- Terminal status (`completed`/`failed`/`cancelled`/`preflight_failed`) emits a
  `terminal` event and stops polling.
- Keepalive (`: ping`) on empty polls.
- **Read-only**: the generator calls only `service.list_events` + `service.get`.
- SSE lives in a **NEW** module so `research_alpha.py` is never edited to add the
  stream — the Phase 45 guard (`test_phase45_guard.py:198-206`) stays GREEN
  unamended.

### SC2 — Lineage read API
- `repository.list_run_lineage(run_id, *, principal)`: read-only ordered parent→child
  edge projection over the append-only `research_alpha_candidate_lineage` table,
  joined to bounded child/parent candidate rows. Principal-fenced (T-45-12:
  cross-principal == unknown-run empty boundary, never a 403 leak).
- `service.list_lineage(run_id, *, principal)`: principal-scoped delegate.
- `projections.lineage(edge)`: deny-by-default bounded edge projection.
- `GET /runs/{run_id}/lineage` → `AlphaLineageDTO`.

### SC4 — Evidence classification + clean flag
- `projections.evidence_classification(snapshot, candidate, fold_evidence, fixture_flag)`:
  deny-by-default classification sourcing every value from EXISTING declared
  fingerprints — `data_date` from `measured_window`, `source_label` from
  `source_field` fingerprint, `cache_state` from declared-fingerprint block
  completeness (fresh/stale/degraded), `missing_fields` from declared list,
  `membership_coverage` from fold stats coverage, `evidence_role` from candidate
  status + fold presence.
- **`clean` flag**: False unless cache is fresh, no missing fields, coverage ≥ 0.9,
  not a fixture, and role ≠ `final_blind_unavailable`. Stale/partial/blocked/
  fixture results can never look like clean production.
- `service.candidate_evidence_classification(run_id, candidate_id, *, principal)`:
  loads existing declared fingerprints (prefer OOS fold, else latest selection fold).
- `GET /runs/{run_id}/candidates/{cid}/evidence-classification` → `EvidenceClassificationDTO`.

---

## Test totals

| Task | Tests | Selection |
|---|---|---|
| 50-01-01 | 5 passed | `list_lineage or principal_fence or ordered_edges or read_only` |
| 50-01-02 | 12 passed | `TestLineageProjection` + `TestEvidenceClassification` |
| 50-01-03 | 7 passed | `TestLineageEndpoint` + `TestEvidenceClassificationEndpoint` |
| 50-01-04 | 9 passed | `stream or last_event_id or reconnect or restart_resume or terminal or keepalive or no_module_state` |
| **Total new tests** | **33 passed** | `test_alpha_lineage.py` (23) + `test_research_alpha_sse.py` (15) = 38 |

---

## Verification

```
cd backend && pytest tests/research/test_alpha_lineage.py tests/research/test_research_alpha_sse.py tests/test_phase45_guard.py -q
→ 90 passed
```

- Phase 45 guard SSE assertion (`test_phase45_guard.py:198-206`): **GREEN** —
  `research_alpha.py` contains no `StreamingResponse`/`text/event-stream`.
- Phase 45 guard router assertion (`test_no_new_router_in_main_beyond_research_alpha`):
  **GREEN** — `main.py` contains no `"workbench"` token.
- `sse-starlette>=2.0` is pre-existing (`pyproject.toml:15`) — **zero new deps**.
- `Watchlist.tsx`: **zero-touch** (declared non-goal).

---

## Deviations

1. **`tests/research/test_run_service.py`** referenced in the plan verification block
   does not exist in the tree (never created by any prior phase). The verification
   runs without it; all 90 tests pass.
2. **Cross-principal lineage endpoint returns 404** (not `[]`/200 as the acceptance
   text literally says). This is consistent with the existing `list_events`/
   `list_candidates` endpoints (`service.get` → None → 404 for both unknown and
   cross-principal) and the T-45-12 boundary: cross-principal == unknown, never a
   403 leak. The REPOSITORY-level `list_run_lineage` does return `[]` for
   cross-principal; the endpoint's `service.get` guard makes both 404.
3. **`cache_state` derivation**: the declared_fingerprints stored in fold evidence
   are SHA-256 digests (opaque), not raw counts. `cache_state` is derived from the
   declared-fingerprint block completeness (all 6 keys present → fresh; partial →
   stale; absent → degraded) rather than from raw missing/suspended/stale counts
   (which are hashed into the `missing_data` digest and not individually
   recoverable). `membership_coverage` is sourced from the fold `stats.coverage`
   value. Every value is still sourced from an existing declared fingerprint.

---

## Hand-off

Delivers to plan 50-02 (compare/replay/clone/stress build on the read APIs) and
plan 50-03 (the frontend renders lineage + evidence classification + SSE progress):
1. Durable `Last-Event-ID` SSE stream (`GET /runs/{id}/stream`).
2. Lineage read API + projection (`GET /runs/{id}/lineage`).
3. `evidence_classification` projection + `clean` flag
   (`GET /runs/{id}/candidates/{cid}/evidence-classification`).
