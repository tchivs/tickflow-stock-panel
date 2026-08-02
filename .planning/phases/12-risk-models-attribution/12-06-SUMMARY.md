---
phase: 12-risk-models-attribution
plan: 12-06
subsystem: portfolio-risk-attribution
tags: [rsk-03, drawdown-breadth, per-segment-attribution, segment-identity, underwater-curve]
requires: [12-01, 12-04]
provides: [drawdown_attribution, full-run_drawdown-report, drawdown-evidence-breadth]
affects: [drawdown.py, analyzer.py, test_drawdown.py]
tech-stack:
  added: [drawdown_attribution per-instrument x per-segment decomposition, segment reconciliation identity, run_drawdown full report payload]
  patterns: [segment-level hard identity symmetric with RSK-01 variance reconciliation, module-threshold constants recorded in evidence, arithmetic (non-compounded) contribution design]
key-files:
  created: []
  modified:
    - backend/app/portfolio/drawdown.py
    - backend/app/portfolio/analyzer.py
    - backend/tests/portfolio/test_drawdown.py
decisions:
  - "drawdown_attribution decomposes each identified drawdown period per-instrument x per-segment: c_i = sum_{t in [start,end]} w_i * r_{i,t}, segment_return computed INDEPENDENTLY as (w @ segment.T).sum() so the HARD assertion sum(c_i) == segment_return (rtol 1e-10, atol 1e-15) is a genuine identity check, never a tautology"
  - "contributions are arithmetic (non-compounded) by design — the identity sum(c_i) == segment return holds exactly in arithmetic; compounding would make it approximate"
  - "empty periods produce the vacuous summary {periods: [], max_depth: 0.0, longest_period: 0, segment_reconciliation_max_abs_error: 0.0}"
  - "The depth/min-obs thresholds (DRAWDOWN_DEPTH_THRESHOLD=0.02, DRAWDOWN_MIN_OBS=2) are module constants recorded in the evidence reconciliation_json — no magic literals in analyzer.py"
  - "run_drawdown evidence reconciliation_json = {period_count, max_depth, longest_period, segment_max_abs_error, depth_threshold, min_obs}; the drawdown.json artifact carries the full report (symbols, underwater, periods with contributions, max_depth, longest_period, segment error, threshold constants)"
  - "non-finite returns raise ValueError before any evidence write (fail closed, no evidence row)"
metrics:
  duration: "~40 min"
  completed: 2026-08-02
status: complete
---

# Phase 12 Plan 06: Drawdown Attribution Breadth — Per-Instrument × Per-Segment Decomposition Summary

One-liner: The RSK-03 drawdown surface hardened from the tracer's identity path to the full contract — per-instrument × per-time-segment decomposition (`drawdown_attribution`) with the hard segment identity Σ c_i == segment return (rtol 1e-10), the module threshold constants (depth 2% / min 2 obs) recorded in evidence, a full `run_drawdown` report + append-only evidence row, and green tests locking the constructed-segment detection, the exact segment identity, thresholds, and end-to-end evidence.

## Objective Achieved

Plan 12-06 turned the 12-02 RED scaffold green and added the RSK-03 breadth: (1) per-instrument × per-segment drawdown attribution — each identified drawdown period carries the per-instrument contribution table `c_i = Σ_{t in [start,end]} w_i · r_{i,t}` with the segment reconciliation identity `Σ_i c_i == segment return` asserted exactly (rtol 1e-10 — linear decomposition, exact in arithmetic); (2) the full `run_drawdown` report — underwater series, periods with per-symbol contributions, max_depth, longest_period, segment reconciliation max abs error, and the documented module thresholds — plus the append-only evidence row recording `period_count / max_depth / longest_period / segment_max_abs_error / depth_threshold / min_obs`; (3) green tests locking the constructed obs 8-11 segment, the exact segment identity, the sub-threshold-dip negative case, and the end-to-end evidence contract.

## Tasks Completed

1. **drawdown.py — `drawdown_attribution` (per-instrument × per-segment)** — for each identified period, computes per-instrument contributions `c_i = w_i * Σ_t r_{i,t}` and an INDEPENDENTLY computed segment return `(w @ segment.T).sum()`, then hard-asserts `Σ c_i == segment return` (rtol 1e-10, atol 1e-15). Returns `{periods: [{start_idx, end_idx, depth, segment_return, contributions: {symbol → float}}], max_depth, longest_period, segment_reconciliation_max_abs_error}`. Empty periods → zero summary (identity vacuous). Out-of-bounds period indices / misaligned panels fail closed with `ValueError`. Contributions are arithmetic (non-compounded) by design — the identity holds exactly in arithmetic. Commit `2ddd822`.
2. **analyzer.py — `run_drawdown` full report + evidence** — computes portfolio returns `weights @ returns.T`, `underwater_curve` + `drawdown_periods` + `drawdown_attribution` BEFORE any write; the `attribution/drawdown.json` artifact now carries the full report (symbols, underwater series, periods with per-symbol contributions, max_depth, longest_period, segment reconciliation max abs error, `depth_threshold`/`min_obs` module constants); the evidence `reconciliation_json` records `period_count / max_depth / longest_period / segment_max_abs_error / depth_threshold / min_obs`. Non-finite returns or a missing run raise `ValueError` with no evidence row. Commit `9c3c6d1`.
3. **test_drawdown.py — the RSK-03 breadth locked green** — the 12-02 scaffold cases stay green (underwater cumprod reference, flat/short → no periods, constructed segment detection, min-obs threshold); new cases: the constructed obs 8-11 segment found with exact boundaries (start 8, end 11) and depth ≥ 2%, the hard segment identity (`sum(contributions) == segment_return` to rtol 1e-10), the sub-2%-depth dip NOT flagged, the vacuous empty-periods summary, misaligned-input fail-closed, the end-to-end `run_drawdown` on a fixture run (tiled 12-column returns aligned to the run's SYM universe) with checksum-verified artifact read-back + evidence reconciliation payload, append-only second evidence row, and non-finite returns failing closed with no evidence row. Commit `e7c8009`.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_drawdown.py -q --tb=short
```

**Result: 12 passed.**

Related files still green (no regression from the analyzer payload change — the existing drawdown identity path in the pipeline tracer; re-run after Exec1205's df5f617 landed on the shared analyzer.py):
```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_drawdown.py tests/portfolio/test_pipeline.py -q --tb=short
```

**Result: 19 passed.**

Grep gates (per plan):
- `simulate_portfolio` appears nowhere in `portfolio/` — the engine is reference-only. ✔
- The depth/min-obs thresholds are the module constants (no magic `0.02`/`2` literals in `analyzer.py`). ✔
- `np.cov(` appears nowhere in `drawdown.py` / `analyzer.py`. ✔

Ruff: `ruff check` clean on all 3 touched files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Segment identity was a tautology in the first draft**
- **Found during:** smoke test before commit 1
- **Issue:** The initial `drawdown_attribution` computed `segment_return = contributions.sum()` — the same quantity as `sum(c_i)`, making the hard assertion vacuous (always passes, even if contributions were wrong).
- **Fix:** `segment_return` is now computed independently as `(w @ segment.T).sum()` (the arithmetic sum of portfolio returns over the segment), so `np.testing.assert_allclose(sum(c_i), segment_return, rtol=1e-10, atol=1e-15)` is a genuine identity check. Verified: 12/12 tests pass and the fixture's `segment_reconciliation_max_abs_error == 0.0`.
- **Files modified:** `backend/app/portfolio/drawdown.py`
- **Commit:** `2ddd822` (folded into the decomposition task)

**2. [Rule 1 - Bug] Depth-threshold test dipped below the 2% threshold by compounding**
- **Found during:** test run (1 failure)
- **Issue:** The scaffold-style `-1% × 3 obs` series compounds to a −2.97% underwater depth — which the 2% threshold SHOULD flag — so the "sub-threshold is NOT flagged" test failed with a real period detected.
- **Fix:** Changed the fixture to `[-0.01, -0.005, ...]`, whose cumulative underwater stays above −2% (−1.5% max), and added an explicit `curve.min() > -DRAWDOWN_DEPTH_THRESHOLD` guard; the negative case now asserts `[]`.
- **Files modified:** `backend/tests/portfolio/test_drawdown.py`
- **Commit:** `e7c8009` (folded into the test task)

**3. [Rule 1 - Bug] RUF002 ambiguous `×` in docstrings**
- **Found during:** ruff check
- **Issue:** The `×` multiplication sign in Chinese docstrings triggered ruff RUF002 (ambiguous unicode).
- **Fix:** Replaced `×` with `x` in the module/function docstrings (`drawdown.py`, and the `analyzer.py` shared module docstring line 7, which Exec1205's 12-05 commit df5f617 carried).
- **Files modified:** `backend/app/portfolio/drawdown.py`, `backend/app/portfolio/analyzer.py`
- **Commit:** analyzer.py fix rides in Exec1205's `df5f617` (shared file, coordinated); drawdown.py fix in `e7c8009`

## Deviations from Plan (scope adjustments)

- **None** — plan executed exactly as written within the 3 tasks. The 12-column returns panel for the end-to-end test tiles `fixture_returns_long` 3× to align with the fixture run's 12-SYM universe (the run row's `output_weights` require column alignment), preserving the constructed obs 8-11 segment.

## Known Stubs

None. `run_drawdown` computes the full per-segment report from the run's weights + caller-supplied returns; no placeholder data paths.

## Threat Flags

None — no security-relevant surface beyond the planned read/analyze layer. The segment identity (T-12-05) is now locked by a hard assertion in `drawdown_attribution` (rtol 1e-10, asserted before any evidence write) with dedicated green tests.

## Self-Check: PASSED

- All 3 modified files exist and lint clean.
- 3 commits recorded (2ddd822, 9c3c6d1, e7c8009), each verified via `git log`.
- Per-plan verification command: 12 passed.
- Related-file regression check: 19 passed (drawdown + pipeline) — re-run after Exec1205's df5f617 landed on the shared analyzer.py.
