---
phase: 13
slug: walk-forward-validation-parameter-search
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-01
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8+ (`--import-mode=importlib`, asyncio auto) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && .venv/bin/python -m pytest tests/backtest -x` |
| **Full suite command** | `cd backend && .venv/bin/python -m pytest -x` |
| **Estimated runtime** | ~120 seconds (full suite ~8 min) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && .venv/bin/python -m pytest tests/backtest -x` (or the touched test file)
- **After every plan wave:** Run `cd backend && .venv/bin/python -m pytest tests/backtest tests/test_operational_migrations.py -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-02-xx | 02 | 0 | WFWD-01/02/03 | T-13-01 | wf_* tables append-only + UNIQUE OOS | unit | `pytest tests/test_operational_migrations.py tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 13-01-xx | 01 | 1 | WFWD-01 | T-13-02 | rolling folds + reserved OOS exactly-once | unit | `pytest tests/backtest/test_walkforward.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 13-03-xx | 03 | 2 | WFWD-01/02 | T-13-03 | OOS-scored search; trial/search-space/distribution recorded | unit | `pytest tests/backtest/test_optimizer_run.py tests/backtest/test_walkforward.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 13-04-xx | 04 | 3 | WFWD-03 | T-13-04 | rank-average ensemble validated-only gate | unit | `pytest tests/backtest/test_ensemble.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 13-05-xx | 05 | 4 | WFWD-01/02/03 | T-13-05 | geometry robustness + reporting breadth | unit | `pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/backtest/test_walkforward.py` — stubs for WFWD-01 (new)
- [ ] `tests/backtest/test_ensemble.py` — stubs for WFWD-03 (new)
- [ ] Extend `tests/backtest/test_optimizer_run.py` — WFWD-02 OOS cases (new)
- [ ] `tests/backtest/conftest.py` — shared fold/panel fixtures (new)
- [ ] Extend `tests/test_operational_migrations.py` — wf_* tables (wf_plans/wf_folds/wf_search_runs/wf_validated_strategies/wf_ensembles)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Trading calendar from governed panel | WFWD-01 | Requires real governed-panel date probe | Run the fold-planner over the actual enriched panel and assert Feb-2026 CNY month yields 14 trading days |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** {pending / approved YYYY-MM-DD}
