---
phase: 01-core-merger
plan: 11
subsystem: testing
tags: [docker-compose, fixtures, playwright, sqlite, sse, upstream-sync]
requires:
  - phase: 01-core-merger
    provides: Phase 1 portfolio, monitoring, delivery, decision, governed-data, and frontend workflows
provides:
  - Pinned local app, receiver, and verifier images plus a no-build/no-pull fixture Compose acceptance command
  - Internal-only Feishu and Telegram receiver verification, endpoint allowlisting, SQLite API checks, SSE alerts, and desktop/mobile browser coverage
  - Upstream source-to-host adoption and regression map
  - Accessible monitor regions and holding cards for deterministic browser verification
affects: [phase-01-validation, compose-acceptance, upstream-adoption]
tech-stack:
  added: [Docker Compose fixture verifier, Playwright Chromium verifier]
  patterns: [prepare images before offline acceptance, internal receiver-only notification delivery, fixture-owned startup synchronization]
key-files:
  created:
    - compose/phase1.test.yml
    - compose/phase1/Dockerfile.verifier
    - compose/phase1/receiver.py
    - compose/phase1/verifier.py
    - compose/phase1/prepare-images.sh
    - compose/phase1/run.sh
    - compose/phase1/fixtures/instruments.json
    - compose/phase1/fixtures/market-data.json
    - docs/UPSTREAM-SYNC.md
  modified:
    - backend/app/main.py
    - frontend/e2e/phase1.spec.ts
    - frontend/src/components/portfolio/HoldingCard.tsx
    - frontend/src/pages/Monitor.tsx
key-decisions:
  - "Fixture mode marks onboarding complete after fixture synchronization so browser acceptance starts at the investor workflow instead of first-run onboarding."
  - "Browser acceptance verifies portfolio creation, delivery inspection, and mobile navigation; API acceptance verifies decision review/replay deterministically."
  - "Notification targets are receiver-only internal Compose endpoints and verifier endpoint allowlisting rejects all other destinations."
patterns-established:
  - "Image preparation: build and inspect all pinned local images, then smoke the verifier with networking disabled before running Compose."
  - "Acceptance isolation: run Compose with --no-build --pull never and fixture-only volumes, then always tear down the project."
requirements-completed: [CORE-06, CORE-07]
---

# Phase 01 Plan 11 Summary

Implemented a hermetic fixture-only Compose acceptance controller for the Phase 1 integrated investor workflow.

## Delivered

- Added the three-service Compose topology: application, internal delivery receiver, and verifier on an internal test network.
- Added deterministic instrument and governed market-data fixtures; the app initializes fixture data and onboarding state without external market calls.
- Added image preparation that builds and inspects pinned local images and runs verifier smoke checks with `--network none`.
- Added no-build/no-pull acceptance runner with exit-code preservation and cleanup.
- Added verifier coverage for health, fixture synchronization, SQLite-backed portfolio and monitoring APIs, SSE emitted alerts, receiver-only Feishu/Telegram deliveries, decision review/replay APIs, endpoint allowlisting, and Playwright desktop/mobile workflows.
- Added the upstream synchronization adoption map covering Tickflow, PanWatch, HermesAlpha, and daily_stock_data seams, ownership, boundaries, and regressions.
- Added accessible names for mobile holding cards and monitor regions so operational browser checks target behavior deterministically.

## Verification

- `bash compose/phase1/prepare-images.sh` — passed: prepared all local images and completed the network-disabled verifier smoke check.
- `bash compose/phase1/run.sh` — passed: fixture synchronization, API/SSE/delivery/decision checks, and 2 desktop/mobile Playwright workflows passed (2 project-inapplicable tests skipped).

## Deviations

- Added small, plan-required testability/accessibility adjustments to existing frontend surfaces (`HoldingCard`, `Monitor`) and fixture-mode onboarding setup in `main.py`. No external runtime, endpoint, database, queue, market data, or notification credential was introduced.

## Commits

- `9063824` — `test(01-11): add hermetic fixture compose acceptance`

## Next Phase Readiness

- The Phase 1 integration is reproducible from local images and immutable fixtures using `bash compose/phase1/prepare-images.sh` followed by `bash compose/phase1/run.sh`.
