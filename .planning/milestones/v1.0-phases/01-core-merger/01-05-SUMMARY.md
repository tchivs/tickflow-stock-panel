---
phase: 01-core-merger
plan: "05"
subsystem: monitoring
tags: [sqlite, monitor-rules, portfolio, alerts]
requires:
  - phase: 01-03
    provides: SQLite operational repository and quote-projected position valuations
  - phase: 01-04
    provides: Current versioned operational database migration boundary
provides:
  - Position-scoped Monitor rules with schedule, cooldown, quiet-bypass, and delivery-channel validation
  - Durable immutable alert-event records with valuation and position context
  - Position projections evaluated after deduplicated generic monitor rules
affects: [01-12, monitor-frontend, compose-acceptance]
tech-stack:
  added: []
  patterns:
    - Generic rules evaluate the deduplicated quote frame before position rules evaluate explicit holding valuations.
    - Persisted alert events are immutable operational snapshots created before SSE or delivery work.
key-files:
  created: []
  modified:
    - backend/app/strategy/monitor_rules.py
    - backend/app/strategy/monitor.py
    - backend/app/api/monitor_rules.py
    - backend/app/services/quote_service.py
    - backend/app/operational/migrations.py
    - backend/app/operational/repository.py
key-decisions:
  - "Position rules use an explicit selected position scope and per-holding cooldown keys so two held accounts for one symbol both retain their own alert context."
  - "The existing MonitorRuleEngine remains the sole rule engine: generic rules stay symbol-deduplicated and position rules run only after their valuation projection is available."
  - "Operational SQLite persists a JSON-safe immutable alert snapshot before SSE broadcast or later delivery handoff."
patterns-established:
  - "Use OperationalRepository.record_alert_event for accepted monitor events before user-visible downstream actions."
  - "Keep active-time evaluation at the Monitor engine boundary; quiet-period delivery behavior remains owned by the later delivery plan."
requirements-completed: [CORE-04]
coverage:
  - id: D1
    description: "Position rules validate explicit holding scope, active-time range, quiet-period bypass, and approved delivery channels."
    requirement: CORE-04
    verification:
      - kind: unit
        ref: backend/tests/test_position_monitor.py#test_position_rule_requires_explicit_position_scope_schedule_and_approved_channels
        status: pass
    human_judgment: false
  - id: D2
    description: "Generic price rules retain one event per instrument while selected holdings receive separate position context and cooldown handling."
    requirement: CORE-04
    verification:
      - kind: integration
        ref: backend/tests/test_position_monitor.py#test_position_rules_preserve_generic_symbol_deduplication_and_scope_each_holding
        status: pass
      - kind: integration
        ref: backend/tests/test_position_monitor.py#test_position_rule_cooldown_and_active_time_suppress_only_the_matching_position_events
        status: pass
    human_judgment: false
  - id: D3
    description: "Accepted position events retain stable identity, immutable conditions, and valuation source/as-of context in operational SQLite."
    requirement: CORE-04
    verification:
      - kind: integration
        ref: backend/tests/test_position_monitor.py#test_accepted_position_event_persists_immutable_condition_and_valuation_context
        status: pass
    human_judgment: false
duration: 5 min
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 05: Holding-Aware Monitor and Durable Event Summary

**The existing Monitor center now evaluates explicit holdings after generic rules and persists immutable position-aware event snapshots before downstream handoff.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-11T02:27:00Z
- **Completed:** 2026-07-11T02:32:37Z
- **Tasks:** 1/1
- **Files modified:** 6

## Accomplishments

- Extended the established Monitor-rule model and API with `position` scope, selected holding IDs, active-time controls, quiet-period bypass, and Feishu/Telegram-compatible channels.
- Kept generic price/market rule evaluation on the deduplicated quote frame, then evaluated selected holdings through the shared portfolio valuation projection with account, position, source, and as-of context.
- Added versioned operational SQLite storage for compatible rule state and immutable alert events, and made QuoteService persist each event before it can reach SSE or later delivery work.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add validated position rules and durable alert-event persistence** - `d21fd49` (feat)

**Plan metadata:** Pending this commit.

## Files Created/Modified

- `backend/app/strategy/monitor_rules.py` - Validates and normalizes position scope, active times, quiet bypass, and approved channels.
- `backend/app/strategy/monitor.py` - Evaluates explicit position projections after generic rules and adds durable event identity/context.
- `backend/app/api/monitor_rules.py` - Exposes position-rule fields and mirrors validated rule state into operational storage.
- `backend/app/services/quote_service.py` - Builds the holding valuation projection and persists events before SSE or delivery processing.
- `backend/app/operational/migrations.py` - Adds versioned monitor-rule and alert-event tables.
- `backend/app/operational/repository.py` - Provides parameterized rule and immutable alert-event persistence methods.

## Decisions Made

- Used the existing `MonitorRuleEngine` and `QuoteService` seams; no scheduler, alert model, or holding fan-out was introduced.
- Retained a per-position cooldown key for position rules so independently held accounts sharing a symbol each preserve their own accepted event context; generic rules retain their existing `(rule_id, symbol)` behavior.
- Preserved the existing JSON rule store for startup/backward compatibility while mirroring validated rule state into the operational SQLite boundary.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 12 can attach bounded Feishu/Telegram delivery outcomes to immutable `alert_events` without changing rule evaluation order.
- Monitor history and the existing shared SSE path receive stable event identity plus position/valuation context for their later UI and stream work.

## Verification

- `uv run --directory backend pytest tests/test_position_monitor.py -q` — **passed** (4 passed).
- `uv run --directory backend pytest tests/test_position_monitor.py tests/test_monitor_etf.py -q` — **passed** (11 passed).

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
