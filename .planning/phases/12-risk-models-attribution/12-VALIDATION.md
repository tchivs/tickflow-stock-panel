---
phase: 12
slug: risk-models-attribution
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-01
---

# Phase 12 — Validation Strategy

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
| 12-02-xx | 02 | 0 | RSK-01/02/03 | T-12-01 | evidence table append-only + triggers | unit | `pytest tests/test_operational_migrations.py tests/portfolio/test_attribution.py tests/portfolio/test_drawdown.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 12-01-xx | 01 | 1 | RSK-01/03 | T-12-02 | sum(MC)==variance rtol 1e-12; checksum-bound covariance | unit | `pytest tests/portfolio/test_attribution.py tests/portfolio/test_pipeline.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 12-03-xx | 03 | 2 | RSK-02 | T-12-03 | semi/EWMA/Ledoit-Wolf PSD provenance; sklearn lazy-import | unit | `pytest tests/portfolio/test_risk.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 12-04-xx | 04 | 2 | RSK-01 | T-12-04 | signed variance components; tamper fail-closed | unit | `pytest tests/portfolio/test_attribution.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 12-05-xx | 05 | 3 | RSK-01/02 | T-12-05 | all-4-models reconciliation; list filter | unit | `pytest tests/portfolio/test_attribution.py tests/portfolio/test_risk.py -q --tb=short` | ❌ W0 | ⬜ pending |
| 12-06-xx | 06 | 4 | RSK-03 | T-12-06 | segment identity sum(c_i)==return rtol 1e-10 | unit | `pytest tests/portfolio/test_drawdown.py -q --tb=short` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/portfolio/test_attribution.py` — stubs for RSK-01 (new)
- [ ] `tests/portfolio/test_drawdown.py` — stubs for RSK-03 (new)
- [ ] Extend `tests/portfolio/test_risk.py` — RSK-02 3-model cases (semi/EWMA/Ledoit-Wolf + PSD provenance)
- [ ] `tests/portfolio/conftest.py` — `fixture_returns_long`, `fixture_attribution_run` fixtures (new)
- [ ] Extend `tests/test_operational_migrations.py` — portfolio_risk_attribution_evidence table + triggers
- [ ] Wave 0 gate: sklearn lazy-import audit (subprocess asserting `"sklearn" not in sys.modules` after importing app.portfolio.*)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| sklearn lazy-import boundary | RSK-02 | Requires subprocess module-top import audit | Run `python -X importtime -c "import app.portfolio.risk"` and assert no `sklearn`/`scikit_learn` import |

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
