---
status: clean
phase: 10-factor-library-multi-factor-model
reviewed: 2026-08-01T00:00:00Z
depth: standard
files_reviewed: 22
findings:
  critical: 2
  warning: 8
  info: 9
  total: 19
---

# Phase 10: Code Review Report

**Reviewed:** 2026-08-01
**Depth:** standard
**Files Reviewed:** 22
**Status:** findings

## Summary

Reviewed the executed Phase 10 factor-library source: the shared signal chain (`signal_chain.py`), the 5-gate admission pipeline (`admission.py`), the deterministic composite model (`models.py`), the PIT universe resolver (`universe.py`), the evaluation/catalog/registry/repository extensions, the DSL partition-context contract (`factor_dsl.py`), the 4-table append-only migration, and the new test suite. The architecture is sound and the FACT-01..06 spine is exercised end-to-end by tests (73+37 pass). The single-compile-path contract (FACT-06) holds: `parse_factor`/`compile_factor` are consumed by `signal_chain` for compute and by registry/hypotheses/api for validation only.

Two BLOCKER defects were found and verified numerically:

1. **Equal-weight composite output is scaled by 1/n** — the code pre-multiplies each revision's z-score by its weight (1/n for equal weight) and then takes a *mean* of the already-weighted columns, applying the 1/n factor twice. The documented formula is `composite = mean_r z_r`; the implementation computes `mean(z_r)/n`. Verified: observed `-0.581` vs true `-1.162` (bias factor 0.5 with n=2).

2. **IC-correlation dedup is computed on date-misaligned series** — `_ic_correlation_duplicate` truncates both arrays to `min(len)` *positionally* instead of intersecting dates. When the admitted factor's per-date IC series is sparse (dates dropped for null IC), the two arrays are paired at mismatched dates and the gate emits a spurious correlation (verified: an anti-correlated sparse series returns 1.0). This can both falsely admit a near-duplicate and falsely reject a distinct factor.

Also notable: the PIT universe resolver — the phase's flagship survivorship-bias fix — is implemented and tested but **never wired into the running application** (`main.py` constructs `FactorEvaluationService` without a resolver; `seed_membership`/`UniverseResolver` have no runtime caller). In production every manifest reports `universe_resolution.method: "config-symbols"` with an empty membership fingerprint, so the PIT contract is dormant in the host.

## Findings

| # | Severity | File | Line/Function | Issue | Recommendation |
|---|----------|------|---------------|-------|----------------|
| CR-01 | BLOCKER | `backend/app/research/models.py` | `build_composite` L283, L292-294 | Equal-weight composite double-applies the 1/n weight (multiply then mean_horizontal) → composite = mean(z)/n | For equal weight, either `sum` the weighted z columns (matching the IC-weighted branch) or `mean_horizontal` the *unweighted* z columns |
| CR-02 | BLOCKER | `backend/app/research/admission.py` | `_ic_correlation_duplicate` L84-99 | Truncation to `min(len)` pairs mismatched dates when the admitted series is sparse → wrong dedup verdict | Intersect on dates first: `common = sorted(set(candidate_dates) & set(admitted_dates))` then correlate only those |
| WR-01 | WARNING | `backend/app/research/models.py` | `_collect_mean_ics` L129-155 | Picks the newest matching experiment without filtering `status == completed`; a diagnostic/summary record (no `ic_summary`) shadows a valid evaluation → IC-weighted composite fails closed | Filter `experiment["status"] == "completed"` and require `ic_summary.mean` before selecting |
| WR-02 | WARNING | `backend/app/research/admission.py` | `MIN_COVERAGE` L45 | Documented policy threshold (finite-share floor 0.50) is never enforced by any gate; a factor with negligible coverage can be admitted | Add a coverage gate to `run_admission` or remove the constant + docstring claim |
| WR-03 | WARNING | `backend/app/main.py` + `research/universe.py` | `main.py` L183-185 | `FactorEvaluationService` is constructed without a `universe_resolver`; `seed_membership`/`UniverseResolver` never wired → PIT membership table never seeded, production manifests always `config-symbols`, survivorship-bias fix inactive | Construct `UniverseResolver(research_repository)` and pass it into the service; invoke `seed_membership` in a startup/sync task |
| WR-04 | WARNING | `backend/app/research/models.py` | `_resolve_symbols` L159-166 | When `symbols` is omitted (default `None`), the fallback returns the revision's DSL *field names* (e.g. `("close","ma20")`) as a symbol list → production `load_panel` requests nonexistent symbols, empty/garbage composite; tests mask it because the stub engine ignores symbols | Require explicit symbols, or resolve symbols from the universe resolver/membership instead of `revision.fields` |
| WR-05 | WARNING | `backend/app/research/models.py` | `_write_composite_artifact` L195-199 | `result` metadata declares `composite_output: "composite.json"`, but `write_bundle` writes `signals.json`/`metric_series.json`/`result.json` only — Phase 11 consumers following the pointer find a missing file | Point `composite_output` at `signals.json` (which carries the composite rows) or add a real `composite.json` descriptor |
| WR-06 | WARNING | multiple | ruff: `admission.py:33`, `signal_chain.py:25`, `evaluation.py:12`, `repository.py:781` | F401 unused imports (`_FUNCTION_PARTITION`, `FactorDslError`, `timedelta`), F811 duplicate `list_comparison_candidates`, RUF100 unused noqa, plus UP035/UP037/UP017/B009/I001 across phase files (33 errors, 32 auto-fixable) | `ruff check --fix` on changed files; delete the second `list_comparison_candidates` at repository.py:781 |
| WR-07 | WARNING | `backend/app/research/catalog.py` + `admission.py` | `record_admitted_factor_summary` L355-411 | FACT-05's "admitted-factor catalog summary" method is never invoked by the admission pipeline (`run_admission` records only the evaluation reference); the summary storage exists but is dead in the main flow, reachable only via direct catalog calls in tests | Call `record_admitted_factor_summary` from `run_admission` (or the orchestrator) once a factor is admitted |
| WR-08 | WARNING | `backend/app/research/catalog.py` + `models.py` | `record_composite_model` L414-448 vs `build_composite` | Two divergent persistence paths for composite records: `build_composite` writes `factor_model_models`/`factor_model_composites` directly through the repository, while `catalog.record_composite_model`/`get_composite_model` are only exercised in tests — the catalog's first-class composite record is not wired to the real builder | Route `build_composite`'s persistence through `catalog.record_composite_model` (or delete the catalog path) so the snapshot record is always created |
| IN-01 | INFO | `backend/app/research/signal_chain.py` | `finite_counts` L141-158 | Coverage `pre_filter_counts` counts rows with null `_forward_return` (last horizon days) as finite, and counts all daily dates before rebalance → slight coverage overstatement vs the evaluated frame | Compute pre-filter counts on the rebalanced frame, or exclude rows whose forward return is null |
| IN-02 | INFO | `backend/app/research/admission.py` | `temporal_split`/`_per_date_ic` | 70/30 split is applied to *finite-IC dates only*, not the full trading window; dates with null IC shift the split boundary | Split on the full window's rebalance dates, then intersect with finite-IC dates |
| IN-03 | INFO | `backend/app/research/evaluation.py` | `_manifest` L420-425 | `resolved_symbols` records `resolved_config["symbols"]` (requested), not the membership-resolved union actually loaded | Record the union of loaded-panel symbols as `resolved_symbols` |
| IN-04 | INFO | `backend/app/research/repository.py` | `resolve_universe_memberships` L549-580 | `MAX(effective_date)` join returns both rows when a symbol has listed+delisted on the same effective_date (UNIQUE permits different states same date); `resolve_universe` then includes it as listed | Tie-break by `created_at`/state in the subquery, or disallow same-date dual events |
| IN-05 | INFO | `backend/app/research/universe.py` | `seed_membership` L155-166 | `except ValueError: continue` swallows *any* ValueError as "already exists" (incl. serialization/validation errors), not only the UNIQUE collision | Catch the UNIQUE-conflict specifically (or check existence first) |
| IN-06 | INFO | `backend/app/research/factor_dsl.py` | `shifted_label_ic` | Returns `inf` when no finite per-date correlation survives (e.g. short panels) → admission gate 2 rejects by design, but the DSL leakage test asserts `<= 0.02` on clean panels; degenerate inputs are indistinguishable from strong leakage | Document/assert the `inf` fail-closed path in the gate verdict detail |
| IN-07 | INFO | `backend/app/research/admission.py` | `run_admission` L158-175 | Every admission attempt (incl. gate-1 rejections) runs a full second evaluation and records catalog evidence + artifacts before gates run — by design per plan, but rejections duplicate catalog growth | Consider deferring evidence recording until after gate 1 passes |
| IN-08 | INFO | `backend/app/research/signal_chain.py` | `_empty_frame` L333-345 | Empty-panel path calls `_resolved_universe(config, None, {})`, discarding the resolved membership block (method reverts to `config-symbols`) | Pass the real membership/pre-filter counts through to `_empty_frame` |
| IN-09 | INFO | `backend/app/research/catalog.py` | `get_composite_model` L450-467 | "Latest" composite = last row by `created_at`/`id`, but `build_composite` generates a fresh `model_id` per build, so an identical-input rebuild creates a brand-new model row instead of a new composite under the same model; the docstring's "re-build appends a NEW composite row" claim is not what the code does | Decide whether rebuild should reuse model_id or document that each build is a distinct model |

## Critical Issues

### CR-01: Equal-weight composite is scaled by 1/n

**File:** `backend/app/research/models.py:283,292-294`
**Issue:** In `build_composite`, equal-weight weights are `1/n` per revision. Each revision's z-score is pre-multiplied by its weight (`_zscore * weight`) into `_z_{revision_id}`, and then `pl.mean_horizontal([_z_r1, _z_r2, ...])` is taken — which divides by n again. Result: `composite = mean_r (z_r * 1/n) = mean(z)/n`, not the documented `mean_r z_{r,t,i}`. Verified with the fixture panel (n=2): observed `-0.580948`, true `-1.161895` (bias factor 0.5). The IC-weighted branch uses `sum(w*z)` and is correct, so the two weightings are inconsistent.
**Fix:**
```python
if weighting == "equal":
    composite_expr = sum(
        pl.col(f"_z_{revision_id}") for revision_id in ordered
    ).alias("composite")   # sum of (z_r * 1/n) == mean(z_r)
```

### CR-02: IC-correlation dedup pairs mismatched dates

**File:** `backend/app/research/admission.py:84-99`
**Issue:** `_ic_correlation_duplicate` builds `candidate_values` and `admitted_values` by independently filtering `ordered_val` for dates present in each series, then computes `limit = min(len(candidate), len(admitted))` and `corrcoef(candidate[:limit], admitted[:limit])`. When the admitted series has dropped dates (null per-date IC), the two arrays are no longer aligned to the same dates — the correlation is computed on mispaired values. Verified: a candidate `[0.1..0.5]` vs an anti-correlated sparse admitted `[0.5,0.4,0.3,0.2]` (missing one date) returns **1.0** instead of ~-1.0. This is the FACT-01 similarity-dedup gate; a wrong correlation can admit a near-duplicate or reject a valid factor.
**Fix:**
```python
common_dates = sorted(set(per_date_ics) & set(series) & set(val_dates))
if len(common_dates) < 2:
    continue
candidate_values = np.array([per_date_ics[d] for d in common_dates], dtype=float)
admitted_values = np.array([series[d] for d in common_dates], dtype=float)
correlation = float(np.corrcoef(candidate_values, admitted_values)[0, 1])
```

## Warnings

### WR-01: `_collect_mean_ics` does not filter experiments by status

`models.py:129-155`. `repo.list_experiments()` returns every experiment (diagnostics, summaries, failed runs). `latest_by_revision` keeps the newest whose `resolved_config` matches — a `record_diagnostic`/summary snapshot can shadow a completed evaluation and cause `ic_summary.mean is None` → the IC-weighted composite fails closed with "no recorded evaluation evidence", even though valid evidence exists. Fix: skip experiments where `status != "completed"` and where `metrics.ic_summary.mean` is absent before committing them to `latest_by_revision`.

### WR-02: `MIN_COVERAGE` declared as fixed policy but never enforced

`admission.py:45` defines `MIN_COVERAGE = 0.50` with recorded provenance in the module docstring, yet `run_admission`'s five gates never check coverage. The plan lists "coverage gates" in the admission artifact; a factor covering 1% of the universe can be admitted if its IC clears the thresholds. Either implement a coverage gate (from `signal.resolved_universe["pre_filter_counts"]`) or remove the constant and its docstring.

### WR-03: PIT universe resolver not wired into the running application

`main.py:183-185` builds `FactorEvaluationService(engine, registry, artifact_service)` with no `universe_resolver`; no code path in `app/` calls `seed_membership`, `close_membership`, or `UniverseResolver`. Consequently `factor_universe_membership` is never seeded, the chain's per-date membership filter never runs, and every production evaluation/admission manifest records `universe_resolution.method: "config-symbols"` with an empty membership fingerprint. The phase's PIT contract (the survivorship-bias fix) is proven in tests but inert in the host. Wire `UniverseResolver(research_repository)` into the evaluation service and add a seeding step.

### WR-04: `_resolve_symbols` falls back to DSL field names as symbols

`models.py:159-166`. When `symbols=None` (the signature default), `_resolve_symbols` returns `tuple(sorted(revision.fields))` — the factor's governed *column names* (e.g. `("close","ma20")`), not tickers. The composite then builds a `SignalChainConfig` whose `symbols` are column names; a real `BacktestEngine.load_panel(symbols=["close",...])` returns an empty panel. Tests pass only because `StubBacktestEngine.load_panel` ignores the symbols argument. Fix: make `symbols` required, or resolve them from the universe resolver/membership.

### WR-05: Composite artifact metadata points to a nonexistent file

`models.py:195-199` writes `result={"composite_output": "composite.json", ...}` into `result.json`, but `EvaluationArtifactService.write_bundle` only ever writes `signals.json`, `metric_series.json`, and `result.json`. The composite rows actually live in `signals.json`. A Phase 11 consumer reading the snapshot's `result.json` would look for `composite.json` and fail. Align the pointer with the real file name.

### WR-06: Ruff/lint failures across phase files

`ruff check` on the changed files reports 33 errors (32 auto-fixable): F401 unused imports (`admission._FUNCTION_PARTITION`, `signal_chain.FactorDslError`, `evaluation.timedelta`), F811 duplicate method `list_comparison_candidates` (repository.py:781 shadows :485), RUF100 unused noqa (`signal_chain.py:279`), plus UP035/UP037/UP017/I001/B009 style items. The phase plan explicitly lists "ruff compliance (line 100, py311)" as a success criterion. Run `ruff check --fix` and remove the dead duplicate.

### WR-07: Admitted-factor catalog summary not wired into admission flow

`catalog.py:355-411` defines `record_admitted_factor_summary` (FACT-05's summary-storage entry point), but `run_admission` never calls it — an admitted factor's catalog entry is only the evaluation reference, and the summary is reachable solely through direct catalog calls in tests. The FACT-05 "admitted-factor catalog summary" is dead in the main flow.

### WR-08: Two divergent composite persistence paths

`build_composite` writes `factor_model_models`/`factor_model_composites` directly through the repository, while `catalog.record_composite_model`/`get_composite_model` — the first-class catalog snapshot record Phase 11 consumes — are exercised only in tests. The production builder never creates the catalog's composite record, so the snapshot the phase promises for Phase 11 may not exist for real models.

## Info

- **IN-01** `signal_chain.py:141-158` — coverage `pre_filter_counts` are computed before rebalance and before the forward-return finite filter, so the last `horizon` days' rows count as covered even though they are dropped from the evaluated frame; coverage slightly overstates usable cross-sections.
- **IN-02** `admission.py:49-58` — `temporal_split` splits on finite-IC dates only, not the full window's trading dates; null-IC dates shift the 70/30 boundary.
- **IN-03** `evaluation.py:420-425` — manifest `resolved_symbols` records the requested config symbols, not the membership-resolved union the chain actually loaded.
- **IN-04** `repository.py:549-580` — the `MAX(effective_date)` per-symbol join returns both rows if a symbol has listed and delisted events on the same effective_date (schema permits it); `resolve_universe` then treats it as listed.
- **IN-05** `universe.py:155-166` — `seed_membership` treats every `ValueError` as "already exists"; genuine validation/serialization errors are silently swallowed.
- **IN-06** `factor_dsl.py:shifted_label_ic` — returns `inf` for degenerate/short panels, so the admission leakage gate always rejects; fine as fail-closed, but the verdict detail does not distinguish "no data" from "strong leakage".
- **IN-07** `admission.py:158-175` — a full evaluation + catalog evidence is recorded before any gate runs, so rejected candidates also generate evidence/artifacts; matches the plan's "rejection recorded identically", but duplicates catalog growth on repeat submissions.
- **IN-08** `signal_chain.py:333-345` — the empty-panel path passes `membership=None` to `_resolved_universe`, dropping the real membership fingerprint when the governed panel is empty.
- **IN-09** `catalog.py:450-467` — `get_composite_model` treats the last `factor_model_composites` row as "latest", but `build_composite` mints a fresh `model_id` per build, so an identical-input rebuild creates a brand-new model rather than appending a composite row under the same model (docstring overstates the re-build behavior).

## Verdict Summary

The Phase 10 spine — shared chain, admission gates, composite, PIT resolver, append-only persistence, DSL partition contract, catalog evidence keys — is structurally well-designed and well-tested. The two BLOCKERs must be fixed before this ships: the equal-weight composite computes the wrong values (a factor of n), and the IC-correlation dedup can emit date-misaligned correlations that corrupt admission verdicts. The PIT resolver's absence from production wiring, the dead `MIN_COVERAGE` policy, the broken `symbols=None` fallback, and the composite artifact pointer mismatch are the highest-priority warnings. All tests currently pass, but none of them assert composite *values* against a reference or exercise sparse admitted IC series, which is why CR-01 and CR…

## Resolved

All 19 findings (2 BLOCKER, 8 WARNING, 9 INFO) were fixed on 2026-08-01. Each fix is an atomic commit; the fix report and test results are appended to `10-06-SUMMARY.md`.

| # | Finding | Fix commit |
|---|---------|-----------|
| CR-01 | Equal-weight composite double-applies 1/n | `bd78e46` |
| CR-02 | IC-corr dedup pairs misaligned dates | `a4aa43d` |
| WR-01 | `_collect_mean_ics` ignores experiment status | `2bd3e56` |
| WR-02 | `MIN_COVERAGE` never enforced | `7961e99` |
| WR-03 | PIT resolver not wired into app | `a5d3714` |
| WR-04 | `_resolve_symbols` falls back to DSL fields | `771dc00` |
| WR-05 | Composite artifact pointer → nonexistent file | `771dc00` |
| WR-06 | Ruff failures across phase files | `42687ed` |
| WR-07 | Admitted-factor summary dead in main flow | `3324234` |
| WR-08 | Divergent composite persistence paths | `01fbaab` |
| IN-01 | Coverage pre-filter overstates usable cross-section | `c1a4935` |
| IN-02 | Temporal split boundary shifts on null-IC dates | `b71b779` |
| IN-03 | Manifest records requested symbols, not loaded union | `4190080` |
| IN-04 | Same-date listed+delisted tie-break | `6772a0d` |
| IN-05 | seed_membership swallows all ValueErrors | `2996900` |
| IN-06 | `inf` fail-closed verdict undocumented | `57a13af` |
| IN-07 | Evidence recorded before any gate runs | `1c6a500` |
| IN-08 | Empty-panel path drops membership fingerprint | `26fe989` |
| IN-09 | Rebuild-model semantics docstring overstates | `57a13af` |

Full backend suite after fixes: **1030 passed, 3 skipped** (was 1027 passed, 3 skipped). `ruff check app/research tests/research` is clean.

---

_Reviewed: 2026-08-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
