---
phase: 01-core-merger
verified: 2026-07-11
status: gaps
verification_ref: 918b8a6
---

# Phase 01 Verification

## Status: gaps

Phase 01 is **not complete**. The committed backend contracts pass, and the Phase 11 topology correctly selects typed fixtures and internal notification receivers. However, the committed Compose acceptance flow cannot prepare its application image because the committed frontend does not type-check. Its effective Compose configuration also retains the base service's publicly published `3018` port, violating the required loopback-only fixture runtime. These are committed Phase 01 defects, confirmed in a detached worktree at `918b8a6`; they are not caused by the unrelated edits in the primary worktree.

## Scope and evidence basis

Reviewed all 15 Phase 01 plans and their 15 summaries, the validation strategy, roadmap, requirements, implementation commits, and the committed source in a detached worktree at `918b8a6`.

| Evidence | Result |
| --- | --- |
| `uv run --index-url https://pypi.org/simple --directory backend --extra dev pytest tests/test_phase1_fixture_sync.py tests/test_data_contracts.py tests/test_portfolio_api.py tests/test_position_monitor.py tests/test_notification_delivery.py tests/test_portfolio_sse.py tests/test_decision_playbook.py tests/test_decision_adjustments.py tests/test_decision_ai_review.py tests/test_decision_replay.py -q` | **37 passed** (three existing Polars warnings) |
| `docker compose -p athenaquant-phase1-test -f docker-compose.yml -f compose/phase1.test.yml config --format json` | Internal-only `phase1_test` network, fixture mode, read-only fixture mount, receiver-only Feishu/Telegram URLs, and AI review disabled are present; it also exposes an unexpected public `3018` port. |
| `bash compose/phase1/prepare-images.sh` | **Failed** during the committed image build: `frontend/src/pages/Monitor.tsx:81` calls `QK.alerts` with three arguments although its committed signature accepts at most one. Therefore the network-disabled smoke check and `run.sh` acceptance were not reached. |

The initially attempted backend command used the configured Tsinghua package mirror and was blocked by HTTP 403 for `h11`; retrying the same focused suite against public PyPI produced the result above. The direct detached-worktree frontend build was not a valid source result because dependencies are intentionally absent in a fresh worktree; the Docker build installed the locked dependencies and exposed the real committed TypeScript error.

## Requirement traceability

| Requirement | Plans | Status | Concrete committed evidence |
| --- | --- | --- | --- |
| CORE-01 | 01, 02, 11 | passed | `FixtureProvider`, `run_phase1_fixture_sync`, two-file fixture bundle, and `test_phase1_fixture_sync.py`; focused suite passes. |
| CORE-02 | 01, 02, 11 | passed | `app/contracts/validator.py` enforces primary-key, market-time, repair-window, and schema-drift checks; `test_data_contracts.py` passes. |
| CORE-03 | 03, 08, 09, 11, 13 | passed | SQLite operational repository, Portfolio API/service, typed client and `/portfolio`; `test_portfolio_api.py` passes. |
| CORE-04 | 05, 08, 10, 11, 12, 13 | passed | Existing Monitor rule domain persists events, stores sanitized delivery outcomes, and exposes alert reads; position/delivery tests pass. |
| CORE-05 | 08, 09, 11, 12, 13 | passed | Existing intraday SSE emits `strategy_alert` and `portfolio_updated`; independent-subscriber and frontend contract coverage passes. |
| CORE-06 | 06, 07, 11 | **gap** | Human Playwright approval and browser contracts exist, but the required one-command Compose proof cannot prepare because the committed frontend build fails. Effective Compose also retains public `3018`. |
| CORE-07 | 11 | passed | `docs/UPSTREAM-SYNC.md` maps Tickflow, PanWatch, HermesAlpha, and daily_stock_data source identity, owner, preserved boundary, named regressions, and review/update workflow. |
| PLAN-01 | 04, 08, 10, 14 | passed | Persisted deterministic governed-data playbook baseline and API; `test_decision_playbook.py` passes. |
| PLAN-02 | 08, 10, 14, 15 | passed | Configured proposal provenance, bounded field audit, unavailable fallback, and AI-free stable-hash replay; decision adjustment/review/replay tests pass. |

## Must-have assessment

### Proven

- The governed lake path uses exactly `instruments.json` and `market-data.json`, selected by `PHASE1_FIXTURE_MODE`; it does not add a SQLite market-series mirror.
- `compose/phase1.test.yml` mounts that fixture directory read-only at `/app/phase1-fixtures`, sets `PHASE1_FIXTURE_MODE=true`, clears real credentials, disables decision AI review, and configures both notification channels only as `http://receiver:8080/...`.
- The Compose services attach only to the named internal `phase1_test` network. `receiver.py` accepts only `/feishu` and `/telegram`, retains sanitized channel/status outcomes, and exposes them only through `/outcomes`.
- `verifier.py` requires fixture mode and rejects a Feishu or Telegram endpoint that is not its expected receiver URL before triggering a rule. It exercises sync, SQLite portfolio/rule mutations, named SSE events, receiver outcomes, baseline-only review, provider-free replay, and desktop/mobile Playwright workflows when acceptance can run.
- `prepare-images.sh` separates builds from acceptance, verifies all three static tags, and runs verifier smoke with `--network none`; `run.sh` uses one `up --no-build --pull never --abort-on-container-exit --exit-code-from verifier` and performs project-scoped cleanup.

### Gaps

1. **Committed frontend type error blocks CORE-06.** `frontend/src/pages/Monitor.tsx:79-83` calls `QK.alerts(filter, severity, delivery)`, while the committed `QK.alerts` API accepts only zero or one argument. The application image cannot build, so no prepared local app image, offline smoke result, or Compose end-to-end acceptance result exists for this revision.
2. **Effective Compose service publishes a non-loopback port.** Base `docker-compose.yml:11-12` contributes `${PORT:-3018}:3018`; `compose/phase1.test.yml` adds `127.0.0.1:13018:3018` rather than overriding the inherited list. Resolved configuration therefore contains both a public `3018` binding and the intended loopback binding. This violates the Plan 11/D-16 loopback-only acceptance runtime contract.

## Required next step

1. Repair the Phase 01 `QK.alerts` call/key contract so the committed frontend build succeeds; retain query-key distinctions for source, severity, and delivery status.
2. Change the Phase 11 override to replace—not append to—the base `ports` list, retaining only the loopback test binding.
3. In a clean committed worktree, rerun the focused backend suite, `bash compose/phase1/prepare-images.sh`, and `bash compose/phase1/run.sh`. Record passing smoke and end-to-end acceptance evidence before changing this status to `passed`.

## Human verification

No additional human approval blocks the repair: the Plan 06 record explicitly approves only `@playwright/test@1.61.1`. Future upstream-update reviews should follow the documented manifest workflow, but this is not a current Phase 01 completion gate.
