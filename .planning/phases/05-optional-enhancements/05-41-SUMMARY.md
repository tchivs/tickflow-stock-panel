---
phase: 05-optional-enhancements
plan: "41"
subsystem: shadow-real-host-e2e
tags: [playwright, fastapi, shadow, cr-01, real-host, optional-modules]
requires:
  - phase: 05-optional-enhancements
    plan: "33"
    provides: server-resolved all_authorized_batch_trades membership and production Shadow browser contract
provides:
  - test-only production optional-host launcher with deterministic governed market data and zero-authority telemetry
  - dedicated phase5-shadow-real-host Playwright project with loopback FastAPI + Vite webServers
  - exact CR-01 real-browser primary node for non-empty import → evidence → distillation → chronological IS/OOS
affects: [05-29, SHDW-01, shadow-production]
tech-stack:
  added: []
  patterns:
    - real-host Playwright without page.route for /api/shadow/**
    - harness-prepended telemetry routes before SPA catch-all
    - live-action spies and repository-ID bypass counters at teardown
key-files:
  created:
    - backend/tests/phase5_real_host_harness.py
    - frontend/playwright.phase5-real-host.config.ts
    - frontend/e2e/phase5-shadow-real-host.spec.ts
    - .planning/phases/05-optional-enhancements/05-41-SUMMARY.md
  modified: []
key-decisions:
  - "Harness launches production app.main lifespan via uvicorn factory; only market fixture size, AUTH_PASSWORD, DATA_DIR, action spies, and forecast probe unavailability are test-owned."
  - "Telemetry lives under /api/__phase5_real_host__/** and is prepended onto the router so SPA catch-all cannot shadow it."
  - "Browser CR-01 never reads repository trade/evidence IDs; membership_mode is strictly all_authorized_batch_trades."
patterns-established:
  - "Phase 05 real-host: Python harness + dedicated Playwright config + one exact primary title for machine report selection."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "Real browser uploads non-empty local CSV and completes import, server-resolved evidence, distillation, and chronological IS/OOS on the production optional host."
    requirement: SHDW-01
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/phase5-shadow-real-host.spec.ts#CR-01 real host non-empty Shadow import to evidence distillation and IS-OOS"
        status: pass
    human_judgment: false
  - id: D2
    description: "No Shadow route interception, no repository-ID handoff, and zero live-action/external bypass counters at teardown."
    requirement: SHDW-01
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/phase5-shadow-real-host.spec.ts telemetry + request assertions"
        status: pass
    human_judgment: false
duration: 45m
completed: 2026-07-22
status: complete
---

# Phase 05 Plan 41: CR-01 Real-Host Shadow Primary Node Summary

**One real Chromium browser now drives non-empty Shadow import through server-resolved evidence, candidate distillation, and chronological IS/OOS against the production optional host with zero Shadow interception and zero live-action authority.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-22T17:49:30Z
- **Completed:** 2026-07-22T18:15:00Z
- **Tasks:** 1/1
- **Files modified:** 3 implementation files plus this summary

## Accomplishments

- Added `backend/tests/phase5_real_host_harness.py`: test-only launcher around production lifespan with temporary storage, deterministic multi-year governed daily bars for `600001.SH`, authenticated principal, live-action spies, network guard, and zero-authority telemetry endpoint.
- Added `frontend/playwright.phase5-real-host.config.ts` with one `phase5-shadow-real-host` Chromium project and two loopback webServers (uvicorn harness on 3018, Vite on 4175).
- Added `frontend/e2e/phase5-shadow-real-host.spec.ts` with the exact CR-01 title once: upload 22-row CSV → completed import → evidence (`membership_mode=all_authorized_batch_trades`, positive member count `1 / 22`) → distill → chronological 样本内/样本外 visible; teardown asserts repository-ID bypass, live-action, and unexpected external counters are zero.
- Verified API-level path first (import/evidence/distill/eval 201), then the exact Playwright primary node passed once in 11.4s wall time for the suite (test ~4.9s).

## Task Commits

| Gate | Task | Result |
|---|---|---|
| GREEN | Task 1: Prove CR-01 in a real browser against the strict 05-33 production Shadow host | Exact CR-01 node passed; harness + config + spec committed atomically |

**Plan metadata:** committed separately after self-check.

## Files Created/Modified

- `backend/tests/phase5_real_host_harness.py` — production optional-host launcher, fixture market data, spies, telemetry.
- `frontend/playwright.phase5-real-host.config.ts` — isolated real-host Playwright project + webServers.
- `frontend/e2e/phase5-shadow-real-host.spec.ts` — exact CR-01 primary report node.

## Decisions Made

- Used a full-year+ weekday daily fixture with session-valid `quote_ts` so fixture-contract validation and distillation feature panels both succeed.
- Forced forecast probe unavailable in the harness so Kronos/torch is not required for Shadow CR-01.
- Allowed only static font CDN hosts (index.html) as non-authority browser traffic; data-plane external connects remain blocked/counted by the harness guard.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Telemetry routes must win over SPA catch-all**
- **Found during:** Task 1 host smoke
- **Issue:** Routes registered after import were shadowed by `/{full_path:path}` SPA fallback and returned `index.html`.
- **Fix:** Prepend telemetry routes onto `app.router.routes` before serving.
- **Files modified:** `backend/tests/phase5_real_host_harness.py`
- **Verification:** `GET /api/__phase5_real_host__/telemetry` returns JSON counters.

**2. [Rule 1 - Bug] Fixture `quote_ts` failed market-session contract**
- **Found during:** Task 1 fixture sync smoke
- **Issue:** Synthetic timestamps were outside 09:00–15:30 Asia/Shanghai session windows.
- **Fix:** Emit 15:00 Asia/Shanghai epoch milliseconds per trade date.
- **Files modified:** `backend/tests/phase5_real_host_harness.py`
- **Verification:** `run_phase1_fixture_sync` completes; `get_daily` returns 262 rows for 2024.

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug)
**Impact on plan:** Required for host readiness and telemetry; no scope creep.

## Issues Encountered

- Default UI distill button label is `开始候选蒸馏` (not the fixture-spec wording); e2e matches the production UI string.
- Static font CDN requests from production `index.html` appear in browser request logs; excluded from authority external-hit assertions while harness `ATHENA_ALLOW_NETWORK=0` still guards Python data-plane sockets.

## Verification

```text
export PATH="/home/orca/source/AthenaQuant/backend/.venv/bin:/root/.local/bin:$PATH"
cd frontend && ATHENA_ALLOW_NETWORK=0 playwright test --config=playwright.phase5-real-host.config.ts e2e/phase5-shadow-real-host.spec.ts --project=phase5-shadow-real-host --grep "CR-01 real host non-empty Shadow import to evidence distillation and IS-OOS$"
Result: PASS — 1 passed (11.4s)
```

## Acceptance Criteria

- **PASS — exact CR-01 title once:** primary node selected by the anchored grep and passed.
- **PASS — unmocked Shadow path:** preview/confirm/evidence/candidates/evaluations hit production `/api/shadow/**` with no route interception.
- **PASS — positive membership:** UI shows frozen evidence and `1 / 22` member count.
- **PASS — IS and OOS:** chronological 样本内 and 样本外 rows visible after evaluation.
- **PASS — zero authority:** repository-ID bypass, all live-action spies, and unexpected external counters are zero.

## Threat Mitigation Evidence

- **T-05-41-01:** authenticated session principal; browser cannot name membership trade IDs.
- **T-05-41-02:** ordinary production requests; immutable evidence append; no repository-ID handoff.
- **T-05-41-03:** live-action spy map remains all zeros at teardown.
- **T-05-41-04:** harness network guard + browser external-hit filter for non-static hosts.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 05-29 machine-report verifier can select the exact CR-01 primary title from the real-host Playwright JSON reporter output.
- Shared `.planning/STATE.md` / `ROADMAP.md` remain for the orchestrator when writable.

## Self-Check: PASSED

- Files exist: harness, Playwright config, e2e spec, this summary.
- Exact verify command passed with 1/1 green.
- No Shadow route interception; no repository-ID construction in the browser flow.
