# Phase 58 — Deferred Items

## Pre-existing test failure (out of scope)

| Category | Item | Status |
|----------|------|--------|
| Pre-existing | `tests/test_notification_delivery.py::test_event_persists_and_streams_before_slow_delivery_completes` — AssertionError on alert event persistence. Confirmed pre-existing via `git stash` test (fails without Plan 01 changes). Not related to WeCom audit or push_stats. | Out of scope — do not fix in this plan |
