# Plan 56-01: 后端 SCT 渠道全链路 — Summary

**Status:** Complete
**Requirements:** SCT-01, SCT-02, SCT-03, SCT-04
**Tasks:** 3/3 complete

## What Was Built

### Task 1: SctChannel + preferences + settings API (TDD)
- `SctChannel` class in `backend/app/notifications/delivery.py` — implements `NotificationChannel` Protocol, POST to `sctapi.ftqq.com/{sendkey}.send` with `title` + `desp` form-data, `code != 0` failure detection
- `get_sct_sendkey()` / `set_sct_sendkey()` in `preferences.py` — symmetric with `get_feishu_webhook_url()`
- `RULE_DELIVERY_CHANNELS` and `REVIEW_PUSH_CHANNELS` whitelists updated to include `"sct"`
- `PUT /preferences/sct-sendkey` endpoint with `secrets_store.mask()` redaction
- `POST /sct-test` endpoint for push testing
- 11 tests GREEN (test_sct_channel.py + test_sct_settings.py)

### Task 2: Pipeline integration + audit + dedup + daily limit
- `SctChannel.deliver()` records `ToolCallEnvelope(tool="sct", category="notification")` on every push (success + failure) via `get_audit_repo().append()`
- `NotificationDeliveryService._channel_for()` registers sct branch → returns `SctChannel`
- Dedup: 5-minute TTL dict keyed by `rule_id:symbol:event_type`, skipped outcomes marked `"dedup"`
- Daily limit: `SCT_DAILY_LIMIT=200`, over-limit pushes marked `"daily_limit_exceeded"`
- `quote_service._maybe_send_webhook()` — sct branch in both fixture and non-fixture modes
- `daily_pipeline._maybe_push_review()` — sct branch using `SctChannel.deliver()`
- `monitor_rules.DELIVERY_CHANNELS` + validate error message updated for sct
- `OperationalRepository.create_delivery_outcome()` channel guard + migration CHECK constraint include `'sct'`
- 15 tests GREEN (test_notification_delivery.py SCT section)

### Task 3: Integration regression
- All SCT + feishu/telegram tests pass (1 pre-existing failure unrelated to SCT — streaming regression from Phase 55 WS migration)

## Commits
- `cf3ff531` test(56-01): add failing tests for SctChannel + settings API (RED)
- `f5b12b23` feat(56-01): implement SctChannel + preferences + settings API (GREEN)
- `6356b70e` test(56-01): add failing tests for SCT audit/dedup/daily-limit/pipeline (RED)
- `a0235278` feat(56-01): SCT dedup + daily limit + pipeline integration + audit (GREEN)

## Key Files Modified
- `backend/app/notifications/delivery.py` — SctChannel + dedup + daily limit + _channel_for registration
- `backend/app/services/preferences.py` — get/set_sct_sendkey + whitelist updates
- `backend/app/api/settings.py` — PUT /preferences/sct-sendkey + POST /sct-test
- `backend/app/operational/repository.py` — channel guard includes sct
- `backend/app/operational/migrations.py` — CHECK constraint includes sct
- `backend/app/strategy/monitor_rules.py` — DELIVERY_CHANNELS includes sct
- `backend/app/services/quote_service.py` — _maybe_send_webhook sct branch
- `backend/app/jobs/daily_pipeline.py` — _maybe_push_review sct branch

## Deviations
- Pre-existing test failure `test_event_persists_and_streams_before_slow_delivery_completes` is a Phase 55 WS migration regression, not related to SCT work
