---
phase: 10
slug: factor-library-multi-factor-model
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-01
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8+ (`--import-mode=importlib`, asyncio auto) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && .venv/bin/python -m pytest tests/research -x` |
| **Full suite command** | `cd backend && .venv/bin/python -m pytest -x` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && .venv/bin/python -m pytest tests/research -x` (or the touched test file)
- **After every plan wave:** Run `cd backend && .venv/bin/python -m pytest tests/research tests/test_operational_migrations.py -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-02-xx | 02 | 0 | FACT-01/02/03/05/06 | T-10-05 | Append-only rows; UNIQUE guards; scipy 1.17.1 pinned | unit | `pytest tests/research/test_universe_resolution.py tests/research/test_signal_chain.py tests/research/test_admission.py tests/research/test_models.py -x` | ❌ W0 | ⬜ pending |
| 10-03-xx | 03 | 0 | FACT-04 | T-10-01 | DSL partition contract; denied labels; leakage gate | unit | `pytest tests/research/test_factor_dsl.py -x` | ✅ extend | ⬜ pending |
| 10-01-xx | 01 | 1 | FACT-01..06 | T-10-01..06 | Shared chain; immutable verdicts; no second impl | unit | `pytest tests/research -x` | ❌ W0 | ⬜ pending |
| 10-04-xx | 04 | 2 | FACT-02/06 | T-10-02 | Per-date universe resolution; manifest fingerprint | unit | `pytest tests/research/test_universe_resolution.py tests/research/test_signal_chain.py -x` | ❌ W0 | ⬜ pending |
| 10-05-xx | 05 | 3 | FACT-01/02/05 | T-10-03 | ICIR/robustness/coverage; candidate trail; rejections | unit | `pytest tests/research/test_admission.py tests/research/test_factor_evaluation.py tests/research/test_experiment_catalog.py -x` | ❌ W0 | ⬜ pending |
| 10-06-xx | 06 | 4 | FACT-03/05 | T-10-04 | Deterministic composite; snapshot-immutable output | unit | `pytest tests/research/test_models.py tests/research/test_experiment_catalog.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/research/test_admission.py` — stubs for FACT-01 (new)
- [ ] `tests/research/test_models.py` — stubs for FACT-03 (new)
- [ ] `tests/research/test_signal_chain.py` — stubs for FACT-06 (new)
- [ ] `tests/research/test_universe_resolution.py` — PIT contract (new)
- [ ] Extend `tests/research/test_factor_dsl.py` — FACT-04 partition + leakage matrix
- [ ] Extend `tests/research/test_factor_evaluation.py` — FACT-02 evidence
- [ ] Extend `tests/research/test_experiment_catalog.py` — FACT-05 metrics
- [ ] Extend `tests/test_operational_migrations.py` — four new tables
- [ ] Wave 0 gate: empty-`.venv` `uv sync --extra shadow` + scipy version assert + lazy-import audit

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Empty-`.venv` dependency resolution | scipy promotion | Requires a real clean-venv install, not unit-testable | Run `cd backend && uv venv --clear && uv sync --extra shadow && python -c "import scipy; assert scipy.__version__ == '1.17.1'"` |

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
