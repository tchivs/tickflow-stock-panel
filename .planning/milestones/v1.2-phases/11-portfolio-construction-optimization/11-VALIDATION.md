---
phase: 11
slug: portfolio-construction-optimization
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-01
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8+ (`--import-mode=importlib`, asyncio auto) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && .venv/bin/python -m pytest tests/portfolio -x` |
| **Full suite command** | `cd backend && .venv/bin/python -m pytest -x` |
| **Estimated runtime** | ~120 seconds (full suite ~8 min) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && .venv/bin/python -m pytest tests/portfolio -x` (or the touched test file)
- **After every plan wave:** Run `cd backend && .venv/bin/python -m pytest tests/portfolio tests/test_operational_migrations.py -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-02-xx | 02 | 0 | PFOL-04 | T-11-01 | cvxpy 1.9.2 pinned; append-only runs table + triggers + CHECKs | unit | `pytest tests/portfolio/test_portfolio_repository.py tests/test_operational_migrations.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 11-01-xx | 01 | 1 | PFOL-01..04 | T-11-01..05 | PSD gate before quad_form; immutable run; no silent repair | unit | `pytest tests/portfolio -q --tb=short` | ❌ W0 | ⬜ pending |
| 11-03-xx | 03 | 2 | PFOL-02 | T-11-03 | HRP baseline deterministic + rendered alongside | unit | `pytest tests/portfolio/test_optimizer.py tests/portfolio/test_pipeline.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 11-04-xx | 04 | 2 | PFOL-02/03 | T-11-04 | max-Sharpe requires baselines; solver fallback | unit | `pytest tests/portfolio/test_optimizer.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 11-05-xx | 05 | 3 | PFOL-04 | T-11-05 | snapshot binding fail-closed; run record breadth | unit | `pytest tests/portfolio/test_pipeline.py tests/research/test_models.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 11-06-xx | 06 | 4 | PFOL-01/03 | T-11-06 | industry cap fail-closed; covariance artifact | unit | `pytest tests/portfolio -q --tb=short` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/portfolio/test_optimizer.py` — stubs for PFOL-01/02/03 (new)
- [ ] `tests/portfolio/test_risk.py` — stubs for PFOL-01 (new)
- [ ] `tests/portfolio/test_portfolio_repository.py` — stubs for PFOL-04 (new)
- [ ] `tests/portfolio/test_schemas.py` — stubs for DTO validation (new)
- [ ] `tests/portfolio/test_pipeline.py` — end-to-end tracer stubs (new)
- [ ] `tests/portfolio/conftest.py` — shared fixtures (new)
- [ ] Extend `tests/test_operational_migrations.py` — portfolio_optimization_runs table + triggers
- [ ] Wave 0 gate: empty-`.venv` `uv sync` + cvxpy 1.9.2 version assert + installed_solvers + module-top import audit + smoke QP

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Empty-`.venv` cvxpy resolution | cvxpy dep | Requires a real clean-venv install | Run `cd backend && uv venv --clear && uv sync && python -c "import cvxpy; assert cvxpy.__version__=='1.9.2'"` |

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
