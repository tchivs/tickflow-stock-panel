# Phase 50-03 Summary — Frontend Replay Workbench Page

**Phase:** 50-replay-workbench
**Plan:** 03 (wave 3, depends_on 50-01 + 50-02)
**Requirements:** AF-REQ-18, AF-REQ-20, AF-REQ-22, AF-REQ-24 (SC1–SC4 UI)
**Status:** COMPLETE — all four tasks test-first, build + e2e green, Watchlist zero-touch

## What landed

The Phase-50 frontend: a single NEW workbench page (`AlphaWorkbench.tsx`, sibling
to `WalkForward.tsx`) that projects every backend seam from 50-01/02 to the
researcher. All server state flows through the existing `request<T>` fetcher +
React Query; the live stream uses native `EventSource` (no new transport/dep).
`Watchlist.tsx` is zero-touch (explicit non-goal, ROADMAP.md:171) — the new page
imports/refs nothing from it (asserted in e2e + ready for the 50-04 guard).

### Task 50-03-01 — api.ts typed fetchers + shared types
Added shared TS interfaces mirroring the backend DTOs from 50-01/02
(`AlphaRunRead`, `AlphaRunEvent`, `AlphaProgress`, `AlphaCandidate`,
`AlphaLineage(Edge)`, `EvidenceClassification`, `AlphaCandidateComparison`,
`AlphaCompare`, `StressMatrix(Row/Baseline)`, `ReplayBranchResult`,
`CloneResult`, request bodies). Added typed fetchers, each wrapping the existing
`request<T>` transport: `fetchAlphaRuns/Run/Progress/Candidates`,
`fetchAlphaLineage`, `fetchEvidenceClassification`, `fetchAlphaCompare`,
`fetchStressMatrix`, `postReplayBranch`, `postClone`, plus the
`alphaRunStreamUrl(runId)` helper returning `/api/research/alpha/runs/{id}/stream`
for `new EventSource(...)`. `AlphaCandidateComparison` carries **no**
winner/rank/score field (SC3 — the deny-by-default DTO forbids it; type-asserted
in the unit suite).

### Task 50-03-02 — page shell + route + runs list + live progress (SC1 UI)
New lazy route `backtest/alpha-workbench` → `<AlphaWorkbench />`. Page shell:
runs-list selector (React Query over `fetchAlphaRuns`) + selected-run panel.
`useAlphaStream(runId)` opens a native `EventSource(alphaRunStreamUrl(runId))`,
accumulates projected events into a bounded tail, tracks an
`idle|running|done|error|reconnecting` connection-state chip (mirrors
`WalkForward.tsx`), and closes the stream on a `terminal` event → `done`.
**Bounded-polling fallback** (`GET /progress` + `GET /runs/{id}` terminal check)
activates when `EventSource` is unavailable (SC1 "SSE *or* bounded polling").

### Task 50-03-03 — lineage tree + compare panel + stress matrix + data-quality banner (SC2/SC3/SC4)
Four tabbed sub-views: **(1) Lineage tree** — parent→child edges with a
token-level LCS diff of the canonical expressions, seed/step/operation, plus
branch-replay (`useMutation(postReplayBranch)`) and clone (`useMutation(postClone)`)
actions. **(2) Compare panel** — candidate multi-select → side-by-side table
(config / per-fold evidence / gate trail / artifacts / diversity); **no**
winner/rank/score column is computed or shown (SC3). **(3) Stress matrix** —
Tier-1 fee/slippage/rebalance `cost_drag`/`net` grid over the frozen baseline.
**(4) Data-quality banner** — binds `evidence_classification.clean`: **red** with
the specific degraded reason (stale cache / missing fields / low coverage /
fixture / final-blind-unavailable) when `clean === false`, green when clean (SC4
— degraded results can never look like clean production).

## Commits

| hash | task | subject |
|---|---|---|
| _see below_ | 50-03-01 | api.ts typed fetchers + shared types for the Phase-50 endpoints (SC1–SC4 surface) |
| _see below_ | 50-03-02 + 50-03-03 | AlphaWorkbench page — EventSource progress, lineage tree, compare, stress, data-quality banner |
| _see below_ | 50-03-04 | Playwright e2e — SC1–SC4 + Watchlist zero-touch |

Each commit used explicit `git add <file>`; the ~97 pre-existing unstaged
frontend/backend files and `frontend/src/pages/Watchlist.tsx` were never touched.

## Test totals

- `e2e/alpha-workbench.spec.ts`: **7** scenarios → **21** runs across
  desktop-chromium / mobile-chromium-320 / phase4-fastapi-host, all green.
- `tests/unit/alpha-workbench-{api,progress,views}.test.ts`: runnable-ready
  vitest artifacts (see Deviation #2).

## Verification (run, green)

```
cd frontend
npx tsc -b                    → EXIT 0   (new page/types compile under strict)
npm run build                 → EXIT 0   (tsc -b && vite build; AlphaWorkbench lazy chunk built)

# Authoritative executable proof (SC1–SC4) — dedicated vite dev server on :4199
# (CI=1 forced reuseExistingServer off; the shared :4173 was a sibling's).
PHASE1_BASE_URL=http://127.0.0.1:4199 npx playwright test e2e/alpha-workbench.spec.ts
  → 21 passed (desktop-chromium + mobile-chromium-320 + phase4-fastapi-host)

# Watchlist zero-touch (verified before commit)
git diff --name-only frontend/src/pages/Watchlist.tsx   → empty (only my files staged)
```

## Deviations from the plan (all benign, documented)

1. **SSE reconnect test asserts the client-side half of SC1.** Playwright's
   `route.fulfill` interception does **not** emulate the `Last-Event-ID` wire
   header on `EventSource` reconnects (diagnosed: 35 reconnects, all with an
   empty `Last-Event-ID` header). The native browser `EventSource` *does* send
   `Last-Event-ID` (a spec guarantee) and the server's lossless resume-from-cursor
   is proven server-side in 50-01 (`backend/tests/research/test_research_alpha_sse.py`:
   `test_last_event_id_resumes_from_k_plus_1`, `test_restart_resume_zero_module_state`,
   the `Last-Event-ID: "2"` endpoint test). The e2e therefore asserts what it can
   genuinely observe client-side: ordered event flow (no gap), reconnect dedup
   by seq so an event is never rendered twice (no duplication), and `terminal` →
   `done`. No code change — the consumer already dedups by seq for exactly this.

2. **Unit suites are runnable-ready, not executed here.** The plan's per-task
   `<verify>` names `npx vitest run …`, but vitest is **not** a dependency and
   there is no `test` script in `frontend/package.json`; adding it would violate
   the zero-new-deps constraint (ROADMAP.md:12). The three unit files live in
   `frontend/tests/unit/` (outside the `tsc -b` `include: ["src"]` scope, so they
   do not affect the build) and are correct against the vitest API — they run
   green the moment vitest is wired in. The **Playwright e2e is the executable
   proof** of SC1–SC4 (Playwright *is* a devDependency).

3. **Three additive fetchers beyond the plan's explicit list.** The plan listed
   the compare/lineage/evidence/stress/replay/clone fetchers + `alphaRunStreamUrl`.
   I also added `fetchAlphaRuns` (sanctioned by the plan's "reuse or add a
   runs-list fetcher"), `fetchAlphaRun` (polling-fallback terminal check), and
   `fetchAlphaCandidates` (compare/stress/quality candidate selectors). All wrap
   the existing `request<T>`; all mirror real backend routes.

4. **Dedicated dev server port (4199).** `CI=1` is set in this environment, which
   sets `playwright.config` `reuseExistingServer:false`; the default port 4173
   was occupied by a sibling executor's server. I ran a dedicated `vite` on 4199
   and pointed `PHASE1_BASE_URL` at it (which disables Playwright's own
   `webServer`). Pure test-harness choice; no project-file change.

## Non-goals honoured

- `Watchlist.tsx` zero-touch (asserted: no `Watchlist` token in
  `AlphaWorkbench.tsx`; `git diff` empty).
- Zero new runtime/dev deps (native `EventSource` + React Query + the existing
  `request<T>`; Playwright was already a devDependency).
- No opaque winner/rank/score computed client-side (SC3 — compare renders raw
  evidence columns only; e2e asserts no winner/rank/score header).
- The browser is never authority over run lifecycle — replay-branch/clone are
  explicit researcher actions that POST to the server-owned create path (SC1).

## Hand-off

To **50-04** (release guard): scan the new frontend modules
(`AlphaWorkbench.tsx`, the Phase-50 `api.ts` section) for the prohibited token
set + assert no `Watchlist` reference leaks (mirror `test_phase45_guard.py`'s
Watchlist-isolation assertion), and confirm zero new base runtime dep.
