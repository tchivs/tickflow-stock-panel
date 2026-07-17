---
phase: 05-optional-enhancements
plan: "25"
subsystem: operational-host-integrity
status: complete
tags: [sqlite, fastapi, cors, local-principal, readiness, fault-isolation]
requires:
  - phase: 05-optional-enhancements
    plan: "19"
    provides: restart-safe Shadow identities and complete production service
  - phase: 05-optional-enhancements
    plan: "22"
    provides: complete Forecast factory, recovery, scanner, and approved local workflow
  - phase: 05-optional-enhancements
    plan: "32"
    provides: complete Thesis readers, scanner readiness, and scheduler registration
provides:
  - atomic per-version SQLite migration and user_version commit or rollback
  - exact loopback Host/Origin initialization boundary with one stable server-owned principal
  - configured-mode session principal enforcement without wildcard CORS
  - final optional capability publication only after factory, recovery, and scanner readiness
  - complete module-local failure cleanup while preserving one runtime and zero live actions
affects: [SHDW-01, THES-01, FORE-01, optional-host, operational-migrations]
tech-stack:
  added: []
  patterns:
    - explicit BEGIN/script/user_version/COMMIT with exception-driven ROLLBACK
    - deployment-owned loopback authority and origin allowlists
    - final readiness publication after all module-specific lifecycle gates
key-files:
  created:
    - backend/tests/test_operational_migrations.py
    - .planning/phases/05-optional-enhancements/05-25-SUMMARY.md
  modified:
    - backend/app/operational/migrations.py
    - backend/app/main.py
    - backend/app/optional_modules.py
    - backend/tests/test_phase5_optional_host.py
key-decisions:
  - "Migration scripts are split with SQLite complete-statement parsing; foreign-key directives run outside the explicit transaction, while every schema statement and exact user_version update commit together."
  - "Unconfigured API access requires a direct loopback peer plus an exact deployment-owned Host and, when present, Origin; accepted requests receive the stable server-owned local_owner_v1 principal."
  - "Configured deployments continue to require the persisted session-derived opaque reviewer principal, and CORS echoes only exact trusted local origins with credentials enabled."
  - "Optional module statuses publish once after creation, Forecast recovery, and required Thesis/Forecast scanner registration; failure clears only that module's complete runtime state."
patterns-established:
  - "Atomic forward migration: strip transaction-incompatible foreign-key directives, execute an explicit transaction script, roll back on any BaseException, and restore foreign_keys=ON in finally."
  - "Truthful optional readiness: no capability status reaches app state before every module-specific lifecycle gate has reached its final result."
requirements-completed: [SHDW-01, THES-01, FORE-01]
coverage:
  - id: D1
    description: "Every migration version and its user_version update commit or roll back as one unit, and immediate restart succeeds after injected mid-script failure."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "backend/tests/test_operational_migrations.py -k 'atomic_version_and_user_version or restart_after_mid_script_failure'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Unconfigured APIs admit only exact trusted loopback Host/Origin requests under one stable server principal; hostile Origin, wrong Host, and LAN peers fail closed."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/test_phase5_optional_host.py -k 'trusted_loopback_origin_host_principal or hostile_origin_denied'"
        status: pass
    human_judgment: false
  - id: D3
    description: "All eight module combinations remain independent and every factory, recovery, or scanner failure clears only the affected capability after complete readiness evaluation."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/test_phase5_optional_host.py -k 'complete_operational_readiness or eight_module_combinations'"
        status: pass
    human_judgment: false
duration: 25m36s
completed: 2026-07-17
---

# Phase 05 Plan 25: Atomic Migration and Truthful Local Host Summary

**Operational migrations now commit schema and version atomically, while the single FastAPI host exposes unconfigured data only through an exact loopback trust boundary and advertises each optional module only after complete independent readiness.**

## Performance

- **Duration:** 25m 36s
- **Started:** 2026-07-17T12:12:58Z
- **Completed:** 2026-07-17T12:38:34Z
- **Tasks:** 2/2
- **Files modified:** 5 implementation/test files plus this summary

## Accomplishments

- Replaced bare migration execution with SQLite-aware statement parsing and an explicit transaction containing every version's schema statements and exact `PRAGMA user_version` update; any failure rolls back the whole version and restores foreign-key enforcement.
- Replaced wildcard CORS and private-LAN trust with exact deployment-owned local origins/authorities, direct loopback peer validation, one stable server-owned initialization principal, and unchanged configured-session principal authority.
- Delayed capability publication until complete factory creation, Forecast recovery, and required Thesis/Forecast scanner registration, with full runtime-state cleanup for the failed module only.
- Preserved the sole operational SQLite database, governed lake, scheduler, FastAPI process/container, completed-v1 routes, and explicit zero-live-action collaborator boundary.

## Task Commits

TDD gates were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Atomic migration and user_version boundary | `e3bdd67` | Mid-script failure left `atomic_probe` behind under the old bare `executescript` runner |
| GREEN | Task 1: Atomic migration and user_version boundary | `854185b` | Full rollback, clean retry, exact version advance, and historical migration regressions pass |
| RED | Task 2: Safe local initialization and complete readiness | `afc096d` | Trusted local responses still exposed wildcard CORS before implementation |
| GREEN | Task 2: Safe local initialization and complete readiness | `c848996` | Loopback trust, session auth, all readiness failures, and eight combinations pass |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/operational/migrations.py` — SQLite complete-statement parsing, deliberate foreign-key directive handling, explicit atomic transaction script, rollback, and policy restoration.
- `backend/tests/test_operational_migrations.py` — deterministic mid-script failure, complete schema/version rollback, clean restart, idempotent final version, and foreign-key restoration contracts.
- `backend/app/main.py` — exact trusted local authorities/origins, credentialed non-wildcard CORS, direct loopback initialization gate, stable local principal, and fail-closed session principal resolution.
- `backend/app/optional_modules.py` — final-only status publication plus complete Forecast transport-state cleanup after recovery/scanner failure.
- `backend/tests/test_phase5_optional_host.py` — real-ASGI local trust scenarios, configured-session proof, seven lifecycle failure cases, eight combinations, one-runtime assertions, and zero-action evidence.

## Decisions Made

- Used `sqlite3.complete_statement` instead of semicolon splitting so compound trigger bodies retain their historical SQL semantics. Only explicit `PRAGMA foreign_keys` directives are removed from the transaction script and applied deliberately outside it.
- Kept CORS and authentication decisions aligned: only exact local origins receive `Access-Control-Allow-Origin`, while the authorization middleware independently requires direct loopback peer and exact Host/Origin trust before assigning `local_owner_v1`.
- Allowed absent Origin only for the exact loopback Host CLI/same-origin path; a present Origin must be allowlisted exactly. Private-address peers, forwarded/client-supplied identity, hostile origins, empty Host, and foreign Host values grant no initialization authority.
- Published module status only after the startup lifecycle has reached a final result. Shadow requires complete creation; Thesis additionally requires ready scanner registration; Forecast additionally requires recovery and scanner registration.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repaired the isolated pytest launcher**
- **Found during:** Task 1 GREEN verification.
- **Issue:** The ignored `backend/.venv/bin/pytest` shebang referenced `/root/source/AthenaQuant`, so `uv run pytest` loaded the primary checkout's old migration code instead of this isolated executor's implementation.
- **Fix:** Repointed only the ignored local launcher to this isolated interpreter and reran the literal plan commands.
- **Files modified:** `backend/.venv/bin/pytest` (ignored environment file; not committed)
- **Verification:** Runtime code paths resolved under `/root/.omp/wt/t77a303290/m`, after which the atomic tests exercised the new BEGIN/ROLLBACK trace and passed.
- **Committed in:** Not applicable — ignored local execution environment only.

---

**Total deviations:** 1 auto-fixed blocking environment issue.
**Impact on plan:** No production scope changed; the repair ensured verification used the actual isolated implementation.

## Issues Encountered

- Two multi-hunk edit-tool operations applied shifted ranges incorrectly in test files. Both anomalies were reported through `xd://report_issue`, immediately re-read, and repaired before verification or commit.
- The initial authorizer-based fault injection was replaced with a deterministic invalid third SQL statement because the stale primary-checkout pytest launcher obscured the new transaction trace. The final contract still injects a true mid-version failure and proves complete rollback plus immediate corrected retry.
- Optional-host tests emit pre-existing Polars deprecation/sortedness warnings from the shared Phase 1 fixture pipeline; all requested assertions pass.

## Verification

```text
cd backend && uv run pytest tests/test_operational_migrations.py -x
Result: PASS — 2 passed.

cd backend && uv run pytest tests/test_phase5_optional_host.py -k "trusted_loopback_origin_host_principal or hostile_origin_denied or complete_operational_readiness or eight_module_combinations" -x
Result: PASS — 11 passed, 6 deselected, 49 pre-existing fixture warnings.

cd backend && uv run pytest tests/test_phase5_foundation.py -k migration -x
Result: PASS — 5 passed, 9 deselected.

cd backend && uv run pytest tests/test_phase5_optional_host.py -x
Result: PASS — 17 passed, 69 pre-existing fixture warnings.

cd backend && uv run ruff check app/operational/migrations.py tests/test_operational_migrations.py
Result: PASS.

cd backend && uv run ruff check --select I app/main.py app/optional_modules.py tests/test_phase5_optional_host.py
Result: PASS.
```

## Acceptance Criteria

- **PASS — atomic migration:** No table/index/trigger or `user_version` from a failed version survives; corrected restart applies both test versions cleanly and repeat migration remains at version 2.
- **PASS — safe usable local path:** Trusted loopback requests receive exact-origin CORS and the stable server principal across preview/confirm identity binding; hostile Origin, wrong/empty Host, and private-LAN peer requests return 403.
- **PASS — configured authority:** Configured mode returns 401 without a valid session and succeeds only after login resolves a persisted opaque reviewer principal.
- **PASS — truthful independent readiness:** Seven probe/init/recovery/scanner failure cases clear every affected module runtime attribute while peers and completed-v1 behavior remain usable; all eight availability combinations pass.
- **PASS — single runtime/no action:** Optional modules retain one operational database, governed lake, scheduler, runtime identity, and zero strategy/monitor/plan/position/ledger/broker/provider/market-action calls.

## Threat Mitigation Evidence

- **T-05-25-01:** Every version executes as `BEGIN; schema statements; PRAGMA user_version; COMMIT;`; exception handling issues `ROLLBACK` and `finally` restores `foreign_keys=ON`.
- **T-05-25-02:** The local principal is a server constant assigned only after numeric direct-peer loopback validation plus exact Host and optional Origin allowlisting; no client identity field is consumed.
- **T-05-25-03:** CORS has no wildcard origin, uses exact deployment-owned local origins, and hostile-origin authorization responses contain no readable CORS grant.
- **T-05-25-04:** Capability state is published only after complete per-module lifecycle gates; recovery/scanner failure removes both service state and Forecast progress transport state.
- **T-05-25-05:** Existing no-action spies remain at zero across success, failure, and terminal paths; no new endpoint, database, queue, container, scheduler authority, provider, broker, or market-action collaborator was introduced.

## TDD Gate Compliance

- Task 1 RED `e3bdd67` failed on observable residual schema under the old runner; GREEN `854185b` made rollback/restart and historical migrations pass.
- Task 2 RED `afc096d` failed because trusted local responses still carried wildcard CORS; GREEN `c848996` made exact local trust, configured auth, complete cleanup, and independent readiness pass.
- No refactor-only commit was necessary after scoped formatting, exact plan verification, and focused regressions.

## Known Stubs

None. Empty optional dependency maps are the explicit deployment-unavailable and zero-live-action seams. Forecast's transient `runner=None` constructor argument is attached to the complete bounded runner before `assert_ready()` and before any status publication. Existing `None` runtime values in `main.py` represent typed disabled/failed services and cannot satisfy the new readiness contracts.

## User Setup Required

None. Local browser access uses the deployment's loopback host and supported app/dev ports; external deployments should continue configuring `AUTH_PASSWORD` and using session authentication.

## Next Phase Readiness

- SHDW-01, THES-01, and FORE-01 can be re-verified against one atomic operational store and a safe, principal-scoped, independently truthful host.
- Later optional work can rely on final capability status as operational truth rather than dependency-probe optimism.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched as required by the Wave 13 executor contract.

## Self-Check: PASSED

- All five scoped implementation/test artifacts and this summary exist in the isolated checkout.
- RED/GREEN commits `e3bdd67`, `854185b`, `afc096d`, and `c848996` resolve as commits.
- Exact plan verification passed 2 migration tests and 11 host tests; focused regressions passed 5 historical migrations and all 17 optional-host scenarios.
- Stub and threat-surface scans found no goal-blocking placeholder or unplanned security surface.
- No task commit deleted a tracked file; `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
