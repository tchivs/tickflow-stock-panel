---
phase: 01-core-merger
plan: 07
subsystem: testing
tags: [playwright, chromium, browser-testing, desktop, mobile, compose]

requires:
  - phase: 01-core-merger
    provides: "Explicit human approval for only @playwright/test@1.61.1 before installation"
provides:
  - "Pinned @playwright/test@1.61.1 dependency and project Chromium runtime"
  - "Deterministic desktop Chromium and 320px mobile Chromium Playwright projects"
  - "Fixture-only Phase 1 Portfolio, Monitor, delivery, SSE, and decision replay browser contracts"
affects: [01-11, CORE-06, compose-acceptance, frontend]

tech-stack:
  added: ["@playwright/test@1.61.1"]
  patterns:
    - "Use PHASE1_BASE_URL exclusively for fixture-controlled browser acceptance targets."
    - "Use semantic Chinese roles and labels plus web-first assertions for desktop and mobile investor workflows."

key-files:
  created:
    - frontend/playwright.config.ts
    - frontend/e2e/phase1.spec.ts
    - .planning/phases/01-core-merger/01-07-SUMMARY.md
  modified:
    - frontend/package.json
    - frontend/pnpm-lock.yaml

key-decisions:
  - "Installed only the exact human-approved @playwright/test@1.61.1 release."
  - "Kept browser contracts fixture-only and intentionally RED until the isolated Compose topology and Phase 1 UI exist."

patterns-established:
  - "Browser acceptance declares separate desktop and 320px touch Chromium projects without a local webServer command."
  - "Acceptance tests exercise accessible UI semantics and never use real Feishu, Telegram, Tickflow, PanWatch, Hermes, or market endpoints."

requirements-completed: [CORE-06]

coverage:
  - id: D1
    description: "The approved Playwright dependency is pinned to 1.61.1 in the frontend manifest and lockfile."
    requirement: CORE-06
    verification:
      - kind: other
        ref: "pnpm --dir frontend list @playwright/test --depth 0; frontend/pnpm-lock.yaml"
        status: pass
    human_judgment: false
  - id: D2
    description: "Desktop and 320px mobile fixture-only browser workflow contracts cover Portfolio, Monitor, delivery status, decision replay, and responsive states."
    requirement: CORE-06
    verification:
      - kind: automated_ui
        ref: "pnpm --dir frontend exec playwright test --list"
        status: pass
    human_judgment: true
    rationale: "The specifications are intentionally RED until the planned Phase 1 UI and isolated Compose fixture topology are delivered; Plan 11 runs the workflows end to end."

duration: 5min
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 07: Browser Acceptance Tooling Summary

**Pinned Playwright browser tooling and fixture-only desktop/mobile investor workflow contracts establish the isolated Compose acceptance seam.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-11T02:13:00Z
- **Completed:** 2026-07-11T02:17:42Z
- **Tasks:** 2 completed
- **Files modified:** 5

## Accomplishments

- Installed only the Plan 06-approved `@playwright/test@1.61.1` development dependency, updated the frontend lockfile, and installed its pinned Chromium runtime.
- Added a no-webServer Playwright configuration whose desktop and 320px touch Chromium projects receive their target only through `PHASE1_BASE_URL`.
- Added deterministic, semantic browser contracts for Portfolio account/holding mutation and freshness, position-rule alert/delivery review, dashboard baseline/final/replay inspection, shared mobile navigation, 44px touch controls, and no-overflow Monitor layout.

## Task Commits

Each task was committed atomically:

1. **Task 1: Install the human-approved Playwright package and Chromium** - `9a9478a` (chore)
2. **Task 2: Create deterministic desktop and mobile browser workflow contracts** - `a00620c` (test)

## Files Created/Modified

- `frontend/package.json` - Adds the exact approved `@playwright/test` development dependency.
- `frontend/pnpm-lock.yaml` - Locks `@playwright/test` and its Playwright runtime at `1.61.1`.
- `frontend/playwright.config.ts` - Configures fixture-controlled desktop and 320px mobile Chromium projects with failure-only screenshots/videos.
- `frontend/e2e/phase1.spec.ts` - Defines fixture-only desktop and mobile investor workflow acceptance contracts.
- `.planning/phases/01-core-merger/01-07-SUMMARY.md` - Records the approved tooling and workflow-contract delivery.

## Decisions Made

- Used only `@playwright/test@1.61.1`, exactly as approved in Plan 06; no substitute package, version range, or browser framework was introduced.
- Did not configure a `webServer` or a default external URL. The suite receives its target from `PHASE1_BASE_URL` when Plan 11 runs the isolated Compose verifier.
- Kept the workflows intentionally RED against the current application because the planned Portfolio, responsive drawer, delivery-detail, and decision inspector surfaces are not yet all present.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The plan's literal version-check grep (`@playwright/test@1\.61\.1`) does not match pnpm 9's displayed format (`@playwright/test 1.61.1`). The exact pin was instead verified by the successful plain `pnpm --dir frontend list @playwright/test --depth 0` output and the lockfile's `specifier` and resolved `version`, both `1.61.1`.

## Verification

- **PASS — approved dependency resolution:** `pnpm --dir frontend list @playwright/test --depth 0` reports `@playwright/test 1.61.1` under frontend dev dependencies.
- **PASS — exact manifest/lock pin:** `frontend/package.json` and `frontend/pnpm-lock.yaml` declare and resolve `@playwright/test` as `1.61.1`.
- **PASS — browser discovery:** `pnpm --dir frontend exec playwright test --list` discovers four project/test entries: the desktop workflow and mobile workflow in both configured projects.
- **NOT RUN by design:** Browser workflows require the planned isolated fixture Compose application. They were not pointed at any non-fixture deployment.

## User Setup Required

None - Plan 11 supplies the isolated Compose `PHASE1_BASE_URL` and local receiver environment for end-to-end execution.

## Next Phase Readiness

- Plan 11 can run the declared browser contracts inside its verifier-controlled Compose topology.
- The configuration and tests are ready for the planned Portfolio, Monitor, delivery, SSE, dashboard inspector, and responsive-shell implementations to turn the intentionally RED workflows green.

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Plan: 07*
*Completed: 2026-07-11*
