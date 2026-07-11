---
phase: 01-core-merger
plan: 13
subsystem: testing
tags: [pytest, sqlite, portfolio, monitor, notifications, sse]
requires: []
provides:
  - Deterministic contract tests for archive-safe multi-account portfolio persistence and quote-projected valuation.
  - Holding-aware MonitorRuleEngine contracts for scope validation, cooldown, active time, and durable alert context.
  - Nonblocking Feishu/Telegram delivery ordering and shared QuoteService fan-out contracts.
affects: [01-03, 01-05, 01-12]
tech-stack:
  added: []
  patterns:
    - Future operational features use temporary SQLite repositories and in-memory collaborators in their contract tests.
    - Shared stream contracts assert independent subscriber queues rather than a second event source.
key-files:
  created:
    - backend/tests/test_portfolio_api.py
    - backend/tests/test_position_monitor.py
    - backend/tests/test_notification_delivery.py
    - backend/tests/test_portfolio_sse.py
  modified: []
key-decisions:
  - "Portfolio contracts require source and as_of freshness metadata, preferring fresh shared quotes and falling back to governed closes."
  - "Position-scoped rules preserve generic per-symbol deduplication while persisting immutable account and valuation context."
  - "Delivery contracts require persistence and strategy-alert fan-out before bounded channel work, with portfolio updates on the existing subscriber pipeline."
patterns-established:
  - "Operational contracts: build temporary SQLite state and deterministic fake market or delivery collaborators."
  - "RED handoff: Wave 1 tests specify future public boundaries without invoking live providers or notification credentials."
requirements-completed: [CORE-03, CORE-04, CORE-05]
coverage:
  - id: D1
    description: Multi-account, archive-safe portfolio persistence and freshness-labeled valuation contract.
    requirement: CORE-03
    verification:
      - kind: other
        ref: "uv run --directory backend pytest tests/test_portfolio_api.py tests/test_position_monitor.py -q; test $? -ne 0"
        status: pass
    human_judgment: false
  - id: D2
    description: Holding-aware MonitorRuleEngine scope, cooldown, active-time, and immutable event-context contract.
    requirement: CORE-04
    verification:
      - kind: other
        ref: "uv run --directory backend pytest tests/test_portfolio_api.py tests/test_position_monitor.py -q; test $? -ne 0"
        status: pass
    human_judgment: false
  - id: D3
    description: Persisted-before-streamed bounded Feishu and Telegram delivery-outcome contract.
    requirement: CORE-04
    verification:
      - kind: other
        ref: "uv run --directory backend pytest tests/test_notification_delivery.py tests/test_portfolio_sse.py -q; test $? -ne 0"
        status: pass
    human_judgment: false
  - id: D4
    description: Independent QuoteService subscribers receive alert and portfolio update fan-out through the existing stream.
    requirement: CORE-05
    verification:
      - kind: other
        ref: "uv run --directory backend pytest tests/test_notification_delivery.py tests/test_portfolio_sse.py -q; test $? -ne 0"
        status: pass
    human_judgment: false
duration: 2min
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 13: Operational-loop Wave 1 Contracts Summary

**Four deterministic RED pytest contracts define archive-safe portfolio state, holding-aware monitoring, bounded notification outcomes, and shared SSE fan-out.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-11T01:46:32Z
- **Completed:** 2026-07-11T01:48:05Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added temporary-SQLite portfolio contracts for account-specific funds, aggregate P&L, quote freshness, governed-close fallback, validation, archival, and deletion guards.
- Added holding-aware MonitorRuleEngine contracts covering selected-position scope, generic-rule deduplication, cooldown, active time, and immutable event context.
- Added nonblocking delivery and shared-stream contracts requiring persist → strategy_alert → bounded delivery ordering and independent alert/portfolio fan-out.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define SQLite portfolio and holding-aware Monitor contracts** - `4b5e9a4` (test)
2. **Task 2: Define nonblocking delivery and shared-SSE contracts** - `2721601` (test)

**Plan metadata:** Pending this commit.

## Files Created/Modified

- `backend/tests/test_portfolio_api.py` - SQLite account, position, valuation, archival, and deletion contracts.
- `backend/tests/test_position_monitor.py` - Position-rule scope, cooldown, schedule, deduplication, and event-persistence contracts.
- `backend/tests/test_notification_delivery.py` - Ordered, bounded Feishu/Telegram delivery-outcome contracts.
- `backend/tests/test_portfolio_sse.py` - Independent alert and portfolio-update subscriber fan-out contracts.

## Decisions Made

- Deterministic contracts use temporary SQLite and in-memory quote or delivery collaborators, never live providers or credentials.
- Portfolio valuation must return source and as_of metadata; stale quotes fall back to the governed close.
- Position rules remain in the existing Monitor domain, and portfolio updates remain in the existing QuoteService/SSE pipeline.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The focused `uv run` commands reached the configured package mirror but could not download existing locked dependencies (`apscheduler==3.11.2` and `fastapi==0.136.1`) because it returned HTTP 403. The required RED wrappers still completed successfully because the commands intentionally assert a nonzero pytest invocation. `python3 -m pytest` was also unavailable because the system interpreter has no pytest installation. No dependency, production code, or configuration was changed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03 can implement the SQLite operational repository, PortfolioService, and Portfolio API against `test_portfolio_api.py`.
- Plan 05 can extend the existing MonitorRuleEngine and operational repository against `test_position_monitor.py`.
- Plan 12 can implement bounded delivery and portfolio SSE fan-out against the two remaining contract modules.

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
