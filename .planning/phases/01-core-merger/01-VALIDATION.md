---
phase: 1
slug: core-merger
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-10
---

# Phase 1 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest with pytest-asyncio; Playwright Test after human package-legitimacy approval |
| **Config file** | `backend/pyproject.toml`; `frontend/playwright.config.ts` is Wave 0 work |
| **Quick run command** | `uv run --directory backend pytest tests/test_operational_portfolio.py tests/test_position_monitor.py -q` |
| **Full suite command** | `uv run --directory backend pytest -q && pnpm --dir frontend build` |
| **Estimated runtime** | ~120 seconds before Compose acceptance |

---

## Sampling Rate

- **After every task commit:** Run the focused pytest files for the changed module, plus `pnpm --dir frontend build` after UI or API type changes.
- **After every plan wave:** Run `uv run --directory backend pytest -q && pnpm --dir frontend build`.
- **Before `/gsd-verify-work`:** Run the full suite and the isolated Compose acceptance command.
- **Max feedback latency:** 120 seconds for focused tests; 10 minutes for the Compose acceptance flow.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | TBD | 1 | CORE-01 | T-01-01 | Fixture synchronization writes only governed Parquet data and refreshes normal views/enrichment. | integration | `uv run --directory backend pytest tests/test_phase1_fixture_sync.py -q` | No - Wave 0 | pending |
| 01-01-02 | TBD | 1 | CORE-02 | T-01-02 | Duplicate keys, invalid time semantics, repair-window violations, and schema drift fail deterministically. | unit/integration | `uv run --directory backend pytest tests/test_data_contracts.py -q` | No - Wave 0 | pending |
| 01-02-01 | TBD | 1 | CORE-03 | T-01-03 | Portfolio CRUD enforces archive/delete rules and derives P&L from shared quote or governed close. | integration | `uv run --directory backend pytest tests/test_portfolio_api.py -q` | No - Wave 0 | pending |
| 01-02-02 | TBD | 2 | CORE-04 | T-01-04 | Rule processing persists events and emits SSE before bounded Feishu or Telegram delivery records outcomes. | unit/integration | `uv run --directory backend pytest tests/test_position_monitor.py tests/test_notification_delivery.py -q` | No - Wave 0 | pending |
| 01-03-01 | TBD | 2 | CORE-05 | T-01-05 | Two independent SSE subscribers receive alert and portfolio updates; frontend refreshes Portfolio data. | unit/browser | `uv run --directory backend pytest tests/test_portfolio_sse.py -q` | No - Wave 0 | pending |
| 01-04-01 | TBD | 2 | PLAN-01 | T-01-06 | Fixed governed data produces and stores deterministic entry, stop, target, and sizing values. | unit/integration | `uv run --directory backend pytest tests/test_decision_playbook.py -q` | No - Wave 0 | pending |
| 01-04-02 | TBD | 2 | PLAN-02 | T-01-07 | Adjustment fields are allowlisted and bounded; replay reads only historical data and cannot invoke AI. | unit/integration | `uv run --directory backend pytest tests/test_decision_adjustments.py tests/test_decision_replay.py -q` | No - Wave 0 | pending |
| 01-05-01 | TBD | 3 | CORE-06 | T-01-08 | Isolated Compose fixture flow verifies health, sync, CRUD, rule trigger, receiver payloads, SSE, and desktop/mobile workflows without external services. | Compose/E2E | `docker compose -p athenaquant-phase1-test -f docker-compose.yml -f compose/phase1.test.yml up --build --abort-on-container-exit --exit-code-from verifier` | No - Wave 0 | pending |
| 01-05-02 | TBD | 3 | CORE-07 | T-01-09 | The adoption map identifies upstream source, local owner, preserved boundary, and regression coverage for each integration. | documentation check | `test -f docs/UPSTREAM-SYNC.md` | No - Wave 0 | pending |

---

## Wave 0 Requirements

- [ ] `backend/tests/test_phase1_fixture_sync.py` and `backend/tests/test_data_contracts.py` - fixture synchronization and data contract coverage.
- [ ] `backend/tests/test_portfolio_api.py`, `test_position_monitor.py`, `test_notification_delivery.py`, and `test_portfolio_sse.py` - operational state and shared event-loop behavior.
- [ ] `backend/tests/test_decision_playbook.py`, `test_decision_adjustments.py`, and `test_decision_replay.py` - deterministic decision safety.
- [ ] Human verification of the official `@playwright/test` package and release before installation, then `frontend/playwright.config.ts` and Phase 1 desktop/mobile specs.
- [ ] `compose/phase1.test.yml`, fixture data, and local receiver/verifier scripts or images for the isolated acceptance topology.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Playwright dependency admission | CORE-06 | Research flagged the current package release as requiring a human legitimacy checkpoint. | Verify the requested package version, official Microsoft repository ownership, provenance, and release notes before adding it to `frontend` dev dependencies. |
| Upstream source revision selection | CORE-07 | The architecture does not prescribe a Git remote, patch-series, or manifest mechanism. | Confirm the source revisions and local owners recorded in `docs/UPSTREAM-SYNC.md` match the intended upstream adoption workflow. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verification or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing test references.
- [ ] No watch-mode flags are used in verification commands.
- [ ] Focused feedback latency is under 120 seconds.
- [ ] `nyquist_compliant: true` is set in frontmatter after plans map all tasks.

**Approval:** pending
