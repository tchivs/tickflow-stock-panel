---
phase: 01-core-merger
plan: 12
subsystem: notifications
tags: [sqlite, sse, feishu, telegram, httpx]
requires:
  - phase: 01-05
    provides: Durable position-aware monitor alert events and shared QuoteService handoff
provides:
  - Bounded Feishu and Telegram delivery with independent durable outcomes
  - Credential-safe failed and skipped delivery records retained with alert events
  - Coalesced portfolio updates on the existing intraday SSE stream
affects: [monitor-frontend, portfolio-frontend, compose-acceptance]
tech-stack:
  added: []
  patterns:
    - Persist and broadcast accepted alerts before bounded external delivery begins.
    - Coalesce affected portfolio account IDs per independent SSE subscriber.
key-files:
  created:
    - backend/app/notifications/delivery.py
  modified:
    - backend/app/operational/migrations.py
    - backend/app/operational/repository.py
    - backend/app/services/quote_service.py
    - backend/app/api/intraday.py
    - backend/app/api/portfolio.py
    - backend/app/main.py
key-decisions:
  - "Only Feishu and Telegram are accepted by the durable delivery adapter; Telegram requests always use the fixed Bot API origin."
  - "Quiet-period delivery suppression is a skipped delivery outcome, while monitor cooldown remains a non-event gate."
patterns-established:
  - "Use NotificationDeliveryService only after QuoteService has persisted and broadcast an accepted alert."
  - "Use QuoteService.notify_portfolio_updated(account_ids) for portfolio mutation refreshes; do not add another EventSource route."
requirements-completed: [CORE-04, CORE-05]
coverage:
  - id: D1
    description: "Accepted alerts remain durable and stream-visible before each configured Feishu or Telegram delivery outcome is independently recorded."
    requirement: CORE-04
    verification:
      - kind: integration
        ref: backend/tests/test_notification_delivery.py
        status: pass
    human_judgment: false
  - id: D2
    description: "Independent subscribers receive coalesced portfolio updates and alert events through the existing intraday stream."
    requirement: CORE-05
    verification:
      - kind: integration
        ref: backend/tests/test_portfolio_sse.py
        status: pass
    human_judgment: false
duration: 15min
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 12: Bounded Notification Delivery and Shared Portfolio SSE Summary

**Immutable monitor alerts now reach every shared-stream subscriber before bounded Feishu or Telegram work records a separate credential-safe outcome, while portfolio mutations fan out through that same stream.**

## Performance

- **Duration:** 15 min
- **Completed:** 2026-07-11T02:47:14Z
- **Tasks:** 2/2
- **Files modified:** 9

## Accomplishments

- Added a bounded delivery service that creates one SQLite outcome per configured Feishu or Telegram channel, enforces approved endpoint construction, applies short `httpx` timeouts, and keeps failures out of monitor evaluation.
- Added a versioned `notification_deliveries` table and repository operations for pending, sent, failed, and quiet-period-skipped outcomes without changing immutable alert event history.
- Extended the existing QuoteService subscribers and `/api/intraday/stream` with coalesced `portfolio_updated` events containing affected account IDs; account and position mutations now use that fan-out.

## Task Commits

Each task was committed atomically:

1. **Task 1: Deliver bounded Feishu and Telegram outcomes after persistence and stream fan-out** - `3b497c7` (feat)
2. **Task 2: Add portfolio updates to the existing SSE subscriber fan-out** - `ebaaba1` (feat)

**Plan metadata:** Pending this commit.

## Files Created/Modified

- `backend/app/notifications/__init__.py` - Exposes the narrow notification delivery boundary.
- `backend/app/notifications/delivery.py` - Performs bounded Feishu and Telegram delivery and safely persists outcomes.
- `backend/app/services/webhook_adapter.py` - Shares the established Feishu text payload and HMAC signing behavior with the delivery adapter.
- `backend/app/operational/migrations.py` - Adds the versioned delivery-outcome schema.
- `backend/app/operational/repository.py` - Stores and queries independent delivery rows.
- `backend/app/services/quote_service.py` - Preserves persistence/SSE/delivery ordering and fans out coalesced portfolio changes.
- `backend/app/api/intraday.py` - Emits named `portfolio_updated` events from the existing stream endpoint.
- `backend/app/api/portfolio.py` - Notifies the shared QuoteService with affected account IDs after successful mutations.
- `backend/app/main.py` - Attaches one delivery service to the existing application state.

## Decisions Made

- Feishu delivery retains the project’s approved hook-prefix validation and HMAC payload behavior; Telegram builds only from the fixed Bot API origin plus configured token and chat ID.
- Delivery rows are created after accepted events are persisted and streamed, so slow or failed external work cannot hide user-visible history.
- Quiet-period suppression persists `skipped` outcomes. Cooldown remains owned by `MonitorRuleEngine`, where suppressed evaluations create no event or delivery row.

## TDD Gate Compliance

- **RED:** Existing Wave 5 contract tests from `2721601 test(01-13): define delivery and shared SSE contracts` failed before this implementation because `app.notifications` did not exist.
- **GREEN:** `3b497c7` and `ebaaba1` make the delivery and shared-SSE contracts pass.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Monitor and Portfolio clients can consume persisted delivery outcomes and `portfolio_updated` from the sole intraday EventSource.
- Compose acceptance can route configured Feishu and Telegram fixtures through its local receiver without adding a second application service.

## Verification

- `uv run --directory backend pytest tests/test_notification_delivery.py tests/test_portfolio_sse.py tests/test_portfolio_api.py -q` — **passed** (12 passed).

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
