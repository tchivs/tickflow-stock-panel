---
phase: 12-risk-models-attribution
plan: 12-04
subsystem: portfolio-risk-attribution
tags: [rsk-01, attribution-breadth, signed-components, attribution-report, tamper-fail-closed]
requires: [12-01]
provides: [attribution_report, full-run_attribution-payload, evidence-invariants]
affects: [attribution.py, analyzer.py, test_attribution.py]
tech-stack:
  added: [attribution_report summary block, signed exposure/MC per symbol, negative-MC diversifier fixture]
  patterns: [signed variance decomposition, top-contributors/diversifiers summary, tamper fail-closed]
key-files:
  created: []
  modified:
    - backend/app/portfolio/attribution.py
    - backend/app/portfolio/analyzer.py
    - backend/tests/portfolio/test_attribution.py
decisions:
  - "attribution_report returns signed exposure + MC dicts per symbol, sum_contributions, reconciliation_error, and a summary block (instrument_count / top_contributors by |MC| desc / diversifiers MC<0 / policy_version phase-12-attribution-v1)"
  - "exposure and marginal contribution share the formula w_i*(Sigma*w)_i per CONTEXT; the labels are semantic (exposure = signed risk footprint, MC = variance decomposition) — both keep signs, never abs()ed"
  - "top_contributors sorts by |MC| for ranking but the vector itself is never abs()ed — the sum identity depends on raw signed components"
  - "The exposure_contribution artifact payload carries the FULL report (weights, exposure, MC, variance, reconciliation, summary); the evidence row stays compact (reconciliation_json = {portfolio_variance, sum_contributions, max_abs_error})"
metrics:
  duration: "~40 min"
  completed: 2026-08-02
status: complete
---

# Phase 12 Plan 04: Attribution Breadth — Signed Components, Full Report, Evidence Invariants Summary

One-liner: The RSK-01 attribution surface hardened from the tracer's single-path proof to the full contract — signed variance components (negative MC = diversifier, never abs()ed), the complete per-instrument contribution + summary report (`attribution_report`), a full `run_attribution` artifact payload with a compact evidence row, and green tests locking the exact reconciliation, the negative-MC diversifier identity, evidence invariants, and the tamper fail-closed path.

## Objective Achieved

Plan 12-04 turned the 12-02 RED scaffold green and added the RSK-01 breadth: (1) signed variance components — negative marginal contribution = diversifier, never abs()ed, so the sum identity survives edge cases; (2) the complete per-instrument contribution + summary report (`attribution_report`: portfolio variance, signed exposure, MC, sum_contributions, reconciliation_error, summary with top contributors / diversifiers / instrument count / policy version); (3) `run_attribution` now writes a full report payload while the evidence row stays compact; (4) green tests locking exact reconciliation on the run's own checksum-verified covariance bytes, the negative-MC identity, evidence invariants (reconciliation required, sha256 64-hex, run_id FK), and tamper fail-closed (modified covariance bytes raise `ArtifactReadError` and write NO evidence row).

## Tasks Completed

1. **attribution.py — `attribution_report`** — the full report: `portfolio_variance`, signed `exposure` (symbol → value), `marginal_contributions` (symbol → value), `sum_contributions`, `reconciliation_error`, and `summary` (`instrument_count`, `top_contributors` sorted by |MC| desc capped at 5, `diversifiers` with MC < 0, `policy_version: "phase-12-attribution-v1"`). Reuses `portfolio_variance` / `portfolio_exposure` / `marginal_contributions` / `reconcile_attribution`; module docstring documents the exposure-vs-MC semantic distinction (shared formula `w_i·(Σw)_i`). Commit `9457b63`.
2. **analyzer.py — full report payload + compact evidence** — the `exposure_contribution.json` artifact now carries weights, signed exposure per symbol, the MC dict, portfolio_variance, reconciliation, and the summary block; the evidence row stays compact (`reconciliation_json = {portfolio_variance, sum_contributions, max_abs_error}`). The checksum-bound covariance load, the hard reconciliation (aborts before any write on failure), and the no-evidence-row-on-failure contract are unchanged. Commit `3928d9a`.
3. **test_attribution.py — the RSK-01 breadth locked green** — the 12-02 scaffold cases stay green; new cases: full-report signed identity, summary-block presence, the negative-MC diversifier fixture (PSD matrix with eigvalsh > 0 where asset 3's MC < 0 and sum(MC) == variance still holds exactly), mismatched-symbols fail-closed, the analyzer payload carrying the full report, evidence invariants (reconciliation required, sha256 64-hex, run_id FK via `sqlite3.IntegrityError`, append-only across analyses), and tamper fail-closed with no evidence row. Commit `5f97ddb`.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py -q --tb=short
```

**Result: 12 passed.**

Related files still green (no regression from the analyzer payload change):
```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py tests/portfolio/test_repository.py tests/portfolio/test_drawdown.py -q --tb=short
```

**Result: 13 passed.**

Grep gate (per plan):
- `np.abs(` / `.abs()` never wraps the marginal-contribution or exposure vectors in `attribution.py` — the sum identity depends on signed components. ✔ (`grep -nE 'np\.abs\(|\.abs\(\)' app/portfolio/attribution.py` → no matches)

Ruff: `ruff check` clean on all 3 touched files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Analyzer passed the report's rounded MC dict as the reconciliation vector**
- **Found during:** smoke test before commit 1
- **Issue:** The initial refactor fed `reconcile_attribution` the report's float-dict MC values (already rounded to 8 decimals by `round()` on exposure and via `float()` coercion), while the variance came from the exact matrix product — a drift far above rtol 1e-12 could theoretically trip the hard assertion on adversarial fixtures.
- **Fix:** `run_attribution` now reconstructs the exact MC vector (`np.asarray(list(mc.values()))`) and passes it to `reconcile_attribution`; the artifact payload keeps the rounded display values. Verified: 12/12 tests pass.
- **Files modified:** `backend/app/portfolio/analyzer.py`
- **Commit:** `3928d9a` (folded into the payload task)

**2. [Rule 1 - Bug] Unused imports left in `analyzer.py` after the report refactor**
- **Found during:** ruff check
- **Issue:** `marginal_contributions` / `portfolio_exposure` / `portfolio_variance` became unused once `run_attribution` delegated to `attribution_report`.
- **Fix:** Trimmed the import list to `attribution_report` + `reconcile_attribution`; ruff clean.
- **Files modified:** `backend/app/portfolio/analyzer.py`
- **Commit:** folded into `3928d9a`

**3. [Rule 1 - Bug] B017 blind-`Exception` assertion in the FK test**
- **Found during:** ruff check
- **Issue:** `pytest.raises(Exception)` around the FK-violation case is a blind-exception anti-pattern (B017).
- **Fix:** Narrowed to `pytest.raises(sqlite3.IntegrityError)` and added the `sqlite3` import; the FK case now asserts the exact failure mode.
- **Files modified:** `backend/tests/portfolio/test_attribution.py`
- **Commit:** folded into `5f97ddb`

## Deviations from Plan (scope adjustments)

- **None** — plan executed exactly as written within the 3 tasks.

## Known Stubs

None. The cross-model reconciliation breadth (all four risk models, `reconcile_all_models`) is explicitly deferred to 12-05 per the wave structure; the `risk_model` recorded on the evidence row stays the run's own model until then.

## Threat Flags

None — no security-relevant surface beyond the planned read/analyze layer. The tamper fail-closed path (T-12-02) is now locked by a dedicated test: modified covariance artifact bytes raise `ArtifactReadError` and write NO evidence row.

## Self-Check: PASSED

- All 3 modified files exist and lint clean.
- 3 commits recorded (9457b63, 3928d9a, 5f97ddb), each verified via `git log`.
- Per-plan verification command: 12 passed.
- Related-file regression check: 13 passed (pipeline/repository/drawdown).
