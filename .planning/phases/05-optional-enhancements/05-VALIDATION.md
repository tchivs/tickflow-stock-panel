---
phase: 05
slug: optional-enhancements
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-15
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0, pytest-asyncio >=0.23, FastAPI TestClient; Playwright 1.61.1 |
| **Config file** | `backend/pyproject.toml`, `frontend/playwright.config.ts` |
| **Quick run command** | `cd backend && uv run pytest tests/shadow tests/theses tests/forecast -x` |
| **Full suite command** | `cd backend && uv run pytest tests/shadow tests/theses tests/forecast tests/test_phase5_optional_host.py -x && cd ../frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium` |
| **Estimated runtime** | Target <30 seconds per focused backend task; phase gate bounded by focused backend plus one Playwright spec |

The optional real-model smoke is `cd backend && uv run --extra forecast pytest tests/forecast/test_kronos_regression.py -m kronos_model -x`. It runs only with a human-reviewed pinned local Kronos-mini/tokenizer pair and MUST NOT download a checkpoint during the test.

---

## Sampling Rate

- **After every task commit:** Run the task's single-domain `pytest ... -x` command; UI tasks run the Phase 05 Playwright spec.
- **After every plan wave:** Run all three focused backend domain suites; waves containing UI changes also run the desktop Playwright spec.
- **Before `/gsd:verify-work`:** Run default/no-extra, Shadow-only, Forecast-only, and Shadow+Forecast host availability contracts, then the complete Phase 05 focused backend and Playwright acceptance commands.
- **Max feedback latency:** 30 seconds for focused task checks; real-model smoke is isolated from the routine feedback loop.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-W0-01 | TBD | 0 | SHDW-01 | T-05-01 | Immutable bounded import; invalid files create no evidence set | unit/integration | `cd backend && uv run pytest tests/shadow/test_imports.py tests/shadow/test_evidence_sets.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-02 | TBD | 0 | SHDW-01 | T-05-02 | Candidate contains allowlisted explainable rules only; retention cannot activate execution | unit/integration | `cd backend && uv run pytest tests/shadow/test_distillation.py tests/shadow/test_evaluation_retention.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-03 | TBD | 0 | THES-01 | T-05-03 | Versions and checks append; condition AST rejects injected fields/operators | unit/integration | `cd backend && uv run pytest tests/theses/test_contracts.py tests/theses/test_versions.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-04 | TBD | 0 | THES-01 | Due checks are idempotent; only a server-authorized confirmation changes official state | integration/API | `cd backend && uv run pytest tests/theses/test_scheduler.py tests/theses/test_lifecycle.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-05 | TBD | 0 | FORE-01 | Catalog rejects moving refs, tokenizer mismatch, digest mismatch, and unsafe model loading | unit/host | `cd backend && uv run pytest tests/forecast/test_catalog.py tests/test_phase5_optional_host.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-06 | TBD | 0 | FORE-01 | Only governed daily stock OHLCV and 5/20/60 governed sessions enter the frozen input | unit/integration | `cd backend && uv run pytest tests/forecast/test_input.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-07 | TBD | 0 | FORE-01 | P10/P50/P90 are computed across 32 retained paths, not from an averaged path | unit/fixture | `cd backend && uv run pytest tests/forecast/test_kronos_adapter.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-08 | TBD | 0 | FORE-01 | Timeout/resource/shape failures create no forecast record; successful artifacts stay immutable | integration | `cd backend && uv run pytest tests/forecast/test_runner.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-09 | TBD | 0 | FORE-01 | Mature outcomes append calibration facts and retries never rewrite the original forecast | integration | `cd backend && uv run pytest tests/forecast/test_calibration.py -x` | ❌ W0 | ⬜ pending |
| 05-W0-10 | TBD | 0 | SHDW-01, THES-01, FORE-01 | Optional modules degrade independently; browser cannot forge evidence/checkpoints or trigger live action | host/browser | `cd backend && uv run pytest tests/test_phase5_optional_host.py -x && cd ../frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/shadow/test_imports.py`, `test_evidence_sets.py`, `test_distillation.py`, `test_evaluation_retention.py`
- [ ] `backend/tests/theses/test_contracts.py`, `test_versions.py`, `test_scheduler.py`, `test_lifecycle.py`
- [ ] `backend/tests/forecast/test_catalog.py`, `test_input.py`, `test_kronos_adapter.py`, `test_runner.py`, `test_calibration.py`
- [ ] `backend/tests/test_phase5_optional_host.py` — optional-module combinations, completed-v1 non-regression, and no-live-execution contract
- [ ] `frontend/e2e/phase5-optional-enhancements.spec.ts` — desktop/narrow viewport, immutable history, pending confirmation, quantiles/paths, unavailable modules, and SSE reconnection
- [ ] Deterministic fixtures for broker CSV/XLSX imports, duplicate/partial fills, governed OHLCV/calendar Parquet, a fixed sampled tensor, and maturity outcomes
- [ ] Human-approved offline Kronos source/checkpoint policy; routine tests must never download models

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pinned Kronos-mini/tokenizer can load and produce the expected regression output on the target CPU runtime | FORE-01 | The optional checkpoint is large, deployment-provisioned, and intentionally absent from routine CI | Install the approved local source and checkpoint catalog without network access, run `uv run --extra forecast pytest tests/forecast/test_kronos_regression.py -m kronos_model -x`, confirm exact checkpoint revisions/digests and bounded runtime output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s for focused checks
- [ ] Routine suites make no external model/network requests
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
