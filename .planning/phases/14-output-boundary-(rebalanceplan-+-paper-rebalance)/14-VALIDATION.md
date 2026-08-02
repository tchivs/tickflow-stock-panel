---
phase: 14
slug: output-boundary-(rebalanceplan-+-paper-rebalance)
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-01
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8+ (`--import-mode=importlib`, asyncio auto) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -x` |
| **Full suite command** | `cd backend && .venv/bin/python -m pytest -x` |
| **Estimated runtime** | ~120 seconds (full suite ~8 min) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -x` (or the touched test file)
- **After every plan wave:** Run `cd backend && .venv/bin/python -m pytest tests/portfolio tests/test_operational_migrations.py -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-02-xx | 02 | 0 | RBAL-01/02 | T-14-03 | rebalance_plans + paper_rebalance_transitions append-only + UNIQUE (plan_id, transition) | unit | `pytest tests/test_operational_migrations.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 14-01-xx | 01 | 1 | RBAL-01/02 | T-14-01/02 | tracer — run weights → lot adapter → plan artifact → suggestion → approve → fill, no-execution gate | unit/integration | `pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 14-03-xx | 03 | 2 | RBAL-01 | T-14-04/07 | odd-lot sell, cash residue, turnover cost, blocked, expiry, RMSE simple/weighted | unit | `pytest tests/portfolio/test_rebalance.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 14-04-xx | 04 | 2 | RBAL-02 | T-14-02/05/06 | reject path, expired fail-closed, no-execution regression gate | unit | `pytest tests/portfolio/test_paper.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 14-05-xx | 05 | 3 | RBAL-01/02 | T-14-01/08 | read/list reporting, run fail-closed, checksum-verified read | unit | `pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/portfolio/test_rebalance.py` — stubs for RBAL-01 (new)
- [ ] `tests/portfolio/test_paper.py` — stubs for RBAL-02 (new)
- [ ] Extend `tests/portfolio/conftest.py` — `fixture_rebalance_run` / `fixture_prices` / `fixture_plan_inputs` (new)
- [ ] Extend `tests/test_operational_migrations.py` — rebalance_plans + paper_rebalance_transitions tables

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| No execution route anywhere | RBAL-01/02 (hard acceptance) | Boundary invariant — verified by automated grep gate + `test_no_execution_route` regression test in every plan's Verification block | `grep -vE '^\s*(#|""")' app/portfolio/rebalance.py app/portfolio/paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; `grep -c "INSERT INTO positions" app/portfolio/paper.py` == 0; `grep -c "INSERT INTO" app/portfolio/paper.py` == 0 |

*The no-execution-route gate is automated (14-01 tracer, 14-04 regression test, consolidated Phase Verification) — the manual-only column is informational for the auditor.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** {pending / approved YYYY-MM-DD}
