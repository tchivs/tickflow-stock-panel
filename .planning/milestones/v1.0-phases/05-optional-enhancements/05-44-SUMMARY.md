---
phase: 05-optional-enhancements
plan: 44
subsystem: final-gate
tags: [provenance, machine-reports, atomic-update, github-attestation, complete]

requires:
  - phase: 05-optional-enhancements
    provides: 05-43 runtime-boundary fixes and committed summary provenance
provides:
  - Four same-tree, repository-external machine reports with adjacent provenance sidecars
  - Fifteen unique report-qualified findings across native Windows, Linux, fixture-browser, and real-host evidence
  - Atomic R43/Wave 15 scoped validation approval
  - GitHub Ubuntu exact-tree Linux evidence workflow and fail-closed consumer
affects: [phase-05-closeout, linux-runner, r43-wave15-sign-off]

tech-stack:
  added: []
  patterns:
    - expectedHead and expectedTree frozen before producers
    - exact relevant-pathspec cleanliness excluding repository-root codebase memory
    - adjacent same-run provenance sidecars
    - remote GitHub run attestation bound to local orchestration
    - in-memory semantic allowlist followed by fsync and os.replace

key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-44-SUMMARY.md
    - .github/workflows/phase5-linux-evidence.yml
  modified:
    - backend/scripts/verify_phase5_final_gate.py
    - backend/tests/test_phase5_final_gate.py
    - frontend/e2e/phase5-optional-enhancements.spec.ts
    - frontend/playwright.config.ts
    - frontend/playwright.phase5-real-host.config.ts
    - .planning/phases/05-optional-enhancements/05-VALIDATION.md
    - .planning/STATE.md
    - .planning/ROADMAP.md
    - .planning/WINDOWS.md

key-decisions:
  - "The successful closeout is bound to local run 7d7ce3ad-c09b-4bb8-8b4b-31d28f7aadef at HEAD 2c313c1c59f1d43699f034624bee1751f114f06d and tree c79e902d29f0de40125d9d43542c4d2973ed8cb9."
  - "GitHub Actions run 30221237357 supplies the exact-tree native Linux report; its attestation and live run identity are consumed fail closed rather than substituting Windows evidence."
  - "Only the R43/Wave 15 scope is approved; global validation status, historical rows, 05-28, 05-40, and component-only 05-GC-44-1 remain unchanged."

metrics:
  duration: 1h34m47s
  completed: 2026-07-27
  tasks: 2 complete
  files: 11

status: complete
---

# Phase 05 Plan 44: Final Machine Closeout Summary

**One provenance-bound closeout approved only the R43/Wave 15 scope after 613/613 checks passed against one frozen Git tree, including attested native Linux evidence from GitHub Actions.**

## Performance

- **Duration:** 1h34m47s across initial fail-closed execution, authorized recovery, and successful closeout
- **Initial start:** 2026-07-26T20:04:06Z
- **Successful run start:** 2026-07-26T21:34:07.293999Z
- **Successful atomic closeout:** 2026-07-26T21:38:53Z
- **Tasks:** 2 complete
- **Successful final orchestration invocations on the final tree:** exactly 1

## Accomplishments

- Implemented and contract-tested producer specifications, frozen HEAD/tree and exact-pathspec checks, four-sidecar provenance validation, a fifteen-finding parser, and an allowlisted atomic validation updater.
- Added an attested GitHub Ubuntu evidence route that verifies workflow identity, repository, run, requested HEAD/tree, native Linux commands, freshness, JUnit hash, and the live GitHub Actions API result.
- Produced four machine reports and four adjacent provenance sidecars beneath one repository-external local run root.
- Passed all 613 discovered checks: 152 native-Windows pytest, 429 native-Linux pytest, 31 fixture Playwright, and 1 real-host Playwright.
- Matched all 15 required report-qualified findings exactly once, with no prohibited status, action, external-request, interception, or repository-bypass evidence.
- Atomically transitioned only `r43_wave15_status`, 05-GC-43-1..3, 05-GC-44-2, five R43 evidence rows, four current report rows, and the R43/Wave 15 scoped approval.

## Task Commits

1. **Task 1 RED: final orchestration contracts** — `c758b39`
2. **Task 1 GREEN: one-shot final-gate components** — `6b9bb28`
3. **Rule 1: preserve native WSL diagnostics** — `adb7a09`
4. **Blocked checkpoint record** — `f0b6903`
5. **Authorized recovery: GitHub-attested Linux evidence path** — `645076b`
6. **Rule 3: trigger attested evidence on the milestone commit** — `6b5653c`
7. **Rule 1: isolate Linux pytest module imports** — `1efa8e6`
8. **Rule 3: install locked Shadow evidence dependencies** — `7244b84`
9. **Rule 1: scope Windows evidence to native contracts** — `0f427c9`
10. **Rule 3: resolve the pnpm producer on Windows** — `c84db57`
11. **Rule 1: run locked Playwright producers cross-platform** — `7cc65a9`
12. **Rule 1: preserve the canonical real-host report path** — `839b403`
13. **Rule 1: preserve the canonical fixture report path** — `2c313c1`

## Final Evidence

- **Local run ID:** `7d7ce3ad-c09b-4bb8-8b4b-31d28f7aadef`
- **GitHub Linux run:** `30221237357`
- **Expected HEAD:** `2c313c1c59f1d43699f034624bee1751f114f06d`
- **Expected tree:** `c79e902d29f0de40125d9d43542c4d2973ed8cb9`
- **Report root:** `D:\AI-Data\temp\Admin\athena-phase5-44-7d7ce3ad-c09b-4bb8-8b4b-31d28f7aadef`
- **Windows JUnit:** `pytest-windows.xml` — 152/152 passed
- **Linux JUnit:** `pytest-linux.xml` — 429/429 passed
- **Fixture Playwright:** `playwright-fixture.json` — 31/31 passed
- **Real-host Playwright:** `playwright-real-host.json` — 1/1 passed
- **Parser verdict:** `parser-verdict.json` — all 15 required findings unique

The report root also contains one adjacent provenance JSON sidecar per report. The Linux sidecar binds the local run to the accepted GitHub run and its verified attestation. The orchestration returned successfully only after preflight, all producers, provenance checks, the strict parser, static/postflight checks, and the final atomic replacement.

## Validation Scope

The resulting `05-VALIDATION.md` diff is limited to:

- `r43_wave15_status: pending` → `passed`
- 05-GC-43-1, 05-GC-43-2, 05-GC-43-3, and 05-GC-44-2 → passed
- R43-CR-01..04 and R43-WR-01 → passed
- Four current report rows → passed with the local run ID and canonical paths
- Seven scoped sign-off checkboxes → checked
- The R43/Wave 15 scoped approval → passed with exact run, HEAD, tree, timestamp, and root

Global `status: pending`, all historical/global rows, 05-28 rejected/blocked, 05-40 pending/blocked, and component-contract-only 05-GC-44-1 remain unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Decode native WSL diagnostics without crashing**

- **Found during:** the initial Task 2 invocation
- **Issue:** `wsl.exe` emitted UTF-16LE installation help while the host decoder expected GBK, causing the fallback reader to lose both streams.
- **Fix:** Decode WSL output explicitly and handle absent streams defensively.
- **Commit:** `adb7a09`

**2. [Rule 3 - Blocking] Admit independently attested native Linux evidence**

- **Found during:** checkpoint resolution after the host was proven to have no installed WSL distribution
- **Issue:** The required native Linux suite could not run on the local host.
- **Fix:** Add a minimal-permission GitHub Ubuntu producer and a fail-closed consumer that verifies the artifact and live run API against the exact local HEAD/tree.
- **Commit:** `645076b`
- **Evidence:** GitHub Actions run `30221237357`

**3. [Rules 1 and 3] Repair final-tree producer portability**

- **Found during:** authorized recovery and final orchestration preparation
- **Issues:** milestone-trigger identity, Linux import isolation, locked optional dependencies, native Windows marker scope, pnpm resolution, cross-platform Playwright startup, and canonical JSON output paths prevented a complete four-report bundle.
- **Fix:** Apply the smallest contract-covered corrections in commits `6b5653c`, `1efa8e6`, `7244b84`, `0f427c9`, `c84db57`, `7cc65a9`, `839b403`, and `2c313c1`.
- **Verification:** The single final orchestration passed 613/613 and produced all four canonical reports plus sidecars.

## Authentication Gates

None. The GitHub run and artifact were already available to the authorized recovery flow; the executor did not push or dispatch a workflow.

## Known Stubs

None.

## Deferred Issues

None for the R43/Wave 15 scope. Global validation and historical supply-review states intentionally remain open because Plan 05-44 is prohibited from changing them.

## Threat Flags

None beyond the plan's declared Git-tree, report-envelope, parser, GitHub-attestation, and atomic-update trust boundaries.

## Self-Check: PASSED

- All four reports, four adjacent provenance sidecars, and `parser-verdict.json` exist in the canonical external run root.
- Expected HEAD `2c313c1c59f1d43699f034624bee1751f114f06d` and tree `c79e902d29f0de40125d9d43542c4d2973ed8cb9` match the successful run record.
- All Task 1, recovery, and producer-fix commits listed above exist in repository history.
- The inspected validation diff changes only the allowlisted R43/Wave 15 scope.
- No orchestration, producer, parser, test suite, or post-replace git gate was rerun during summary/state closeout.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-27*
