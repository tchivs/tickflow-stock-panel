---
phase: 1
slug: core-merger
status: draft
nyquist_compliant: true
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
| 01-13-01 | 01-13 | 1 | CORE-03, CORE-04 | T-01-13 | Account/holding and holding-aware Monitor test contracts require archive safety, quote/close freshness, scoped rules, cooldown, and durable event context. | contract | `uv run --directory backend pytest tests/test_portfolio_api.py tests/test_position_monitor.py -q; test $? -ne 0` | No - Wave 1 | pending |
| 01-13-02 | 01-13 | 1 | CORE-04, CORE-05 | T-01-13 | Delivery/SSE test contracts require persisted-streamed events before bounded outcomes and independent subscriber fan-out. | contract | `uv run --directory backend pytest tests/test_notification_delivery.py tests/test_portfolio_sse.py -q; test $? -ne 0` | No - Wave 1 | pending |
| 01-14-01 | 01-14 | 1 | PLAN-01, PLAN-02 | T-01-14 | Decision test contracts require deterministic baseline persistence and bounded allowed-field audit outcomes. | contract | `uv run --directory backend pytest tests/test_decision_playbook.py tests/test_decision_adjustments.py -q; test $? -ne 0` | No - Wave 1 | pending |
| 01-14-02 | 01-14 | 1 | PLAN-02 | T-01-14 | Provider/replay test contracts require provenance and fallback plus historical AI-free replay. | contract | `uv run --directory backend pytest tests/test_decision_ai_review.py tests/test_decision_replay.py -q; test $? -ne 0` | No - Wave 1 | pending |
| 01-02-01 | 01-02 | 2 | CORE-01 | T-01-02 | Fixture synchronization writes only governed Parquet data and refreshes normal views/enrichment. | integration | `uv run --directory backend pytest tests/test_phase1_fixture_sync.py -q` | No - Wave 0 | pending |
| 01-02-02 | 01-02 | 2 | CORE-02 | T-01-02 | Duplicate keys, invalid time semantics, repair-window violations, and schema drift fail deterministically. | unit/integration | `uv run --directory backend pytest tests/test_data_contracts.py -q` | No - Wave 0 | pending |
| 01-03-01 | 01-03 | 2 | CORE-03 | T-01-03 | Portfolio CRUD enforces archive/delete rules and derives P&L from shared quote or governed close. | integration | `uv run --directory backend pytest tests/test_portfolio_api.py -q` | No - Wave 0 | pending |
| 01-05-01 | 01-05 | 4 | CORE-04 | T-01-05 | Position-rule processing preserves cooldown non-events and persists accepted event identity with valuation context. | unit/integration | `uv run --directory backend pytest tests/test_position_monitor.py -q` | No - Wave 0 | pending |
| 01-12-01 | 01-12 | 5 | CORE-04 | T-01-12 | Persisted events stream before bounded Feishu or Telegram delivery; quiet-period suppression persists a skipped outcome. | unit/integration | `uv run --directory backend pytest tests/test_notification_delivery.py -q` | No - Wave 0 | pending |
| 01-12-02 | 01-12 | 5 | CORE-05 | T-01-12 | Two independent SSE subscribers receive alert and portfolio updates; frontend refreshes Portfolio data. | unit/browser | `uv run --directory backend pytest tests/test_portfolio_sse.py -q` | No - Wave 0 | pending |
| 01-04-01 | 01-04 | 3 | PLAN-01 | T-01-04 | Fixed governed data produces and stores deterministic entry, stop, target, and sizing values before any provider proposal. | unit/integration | `uv run --directory backend pytest tests/test_decision_playbook.py -q` | No - Wave 0 | pending |
| 01-15-01 | 01-15 | 4 | PLAN-02 | T-01-15 | Configured OpenAI-compatible review persists typed proposal/provenance, fake and unavailable paths keep the baseline, and fields remain bounded. | unit/integration | `uv run --directory backend pytest tests/test_decision_adjustments.py tests/test_decision_ai_review.py -q` | No - Wave 0 | pending |
| 01-15-02 | 01-15 | 4 | PLAN-02 | T-01-15 | Replay reads only historical data and cannot invoke a review gateway. | unit/integration | `uv run --directory backend pytest tests/test_decision_replay.py -q` | No - Wave 0 | pending |
| 01-11-01 | 01-11 | 8 | CORE-06 | T-01-11 | Isolated Compose fixture flow verifies health, sync, CRUD, rule trigger, receiver payloads, SSE, AI-review-disabled baseline, and desktop/mobile workflows without external services. | Compose/E2E | `bash compose/phase1/run.sh` | No - Wave 0 | pending |
| 01-11-02 | 01-11 | 8 | CORE-07 | T-01-11 | The adoption map identifies upstream source, local owner, preserved boundary, and regression coverage for each integration. | documentation check | `test -f docs/UPSTREAM-SYNC.md` | No - Wave 0 | pending |

---

## Wave 1 Contract Requirements

- [ ] `backend/tests/test_phase1_fixture_sync.py` and `backend/tests/test_data_contracts.py` - two governed-data contracts owned by Plan 01.
- [ ] `backend/tests/test_portfolio_api.py`, `test_position_monitor.py`, `test_notification_delivery.py`, and `test_portfolio_sse.py` - four operational-loop contracts owned by Plan 13.
- [ ] `backend/tests/test_decision_playbook.py`, `test_decision_adjustments.py`, `test_decision_ai_review.py`, and `test_decision_replay.py` - four deterministic decision-safety contracts owned by Plan 14.
- [ ] Human verification of the official `@playwright/test` package and release before installation, then `frontend/playwright.config.ts` and Phase 1 desktop/mobile specs.
- [ ] `compose/phase1.test.yml`, typed fixture data, local receiver/verifier scripts, verifier image, and cleanup-safe runner for the isolated acceptance topology.

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
- [ ] Wave 1 contract plans cover all missing test references.
- [ ] No watch-mode flags are used in verification commands.
- [ ] Focused feedback latency is under 120 seconds.
- [ ] `nyquist_compliant: true` is set in frontmatter after plans map all tasks.

**Approval:** pending
