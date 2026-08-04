---
phase: 11-portfolio-construction-optimization
plan: 11-06
subsystem: portfolio-optimization, risk-model
tags: [industry-cap, fail-closed, covariance-sha256, artifact-breadth, constraint-stack, risk-model-json, immutable-artifacts, pydantic]

# Dependency graph
requires:
  - phase: 11-portfolio-construction-optimization
    provides: 11-05 — run_optimization fail-closed wrapper (SnapshotBindingError/ValueError/RuntimeError/SolverError recorded as failed runs with failure_reason), catalog snapshot seam, list_optimization_runs breadth; 11-01 — PortfolioArtifactService.write_bundle (covariance.json support) + PSD provenance in risk_model_json; 11-04 — solver_path/w_prev/max-Sharpe breadth on the same constraint stack
provides:
  - portfolio/optimizer.py — industry-cap fail-closed gate wired through run_optimization (assert_industry_cap_unavailable at the top of the impl; requested cap → failed run with reason "industry mapping unavailable"), constraint_stack_json records industry_cap: null when unrequested (HRP / non-optimal / success paths), covariance_sha256 in _build_risk_model, covariance_artifact_relative_path recorded in risk_model_json (HRP + success paths)
  - portfolio/risk.py — covariance_sha256(cov): canonical 8-decimal JSON sha256 (byte-identical to write_bundle covariance.json serialization)
  - portfolio/artifacts.py — write_bundle rounds covariance to 8 decimals so artifact bytes hash to the recorded digest (Phase 12 checksum seam)
  - portfolio/schemas.py — OptimizationRequest.industry_cap: float | None
  - tests/portfolio/test_risk.py — covariance_sha256 determinism/discrimination + digest round-trip through read_artifact(covariance.json)
  - tests/portfolio/test_optimizer.py — industry-cap gate (failed run), industry_cap: null stack recording, covariance_sha256 + artifact path on successful runs, schema nullability
  - tests/portfolio/conftest.py — fixture_composite writes a real checksum-bound signals.json artifact (output_sha256 = sha256 of artifact bytes)
affects: [Phase 12 risk suite (covariance artifact seam), Phase 14 RebalancePlan, Phase 15 API, ship gate]

# Actuals (#2632)
actuals:
  tokens: 28000
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns: [industry-cap fail-closed gate wired through the orchestrator — assert_industry_cap_unavailable raises ValueError("industry mapping unavailable") caught by the 11-05 wrapper and recorded as a failed run (pitfall 8, T-11-06), covariance artifact breadth — covariance.json written under the run namespace with canonical 8-decimal rounding so covariance_sha256(cov) == artifact checksum, Phase 12 loads the matrix by checksum]

key-files:
  created: []
  modified:
    - backend/app/portfolio/optimizer.py
    - backend/app/portfolio/risk.py
    - backend/app/portfolio/artifacts.py
    - backend/app/portfolio/schemas.py
    - backend/tests/portfolio/test_risk.py
    - backend/tests/portfolio/test_optimizer.py
    - backend/tests/portfolio/conftest.py

key-decisions:
  - "The industry-cap fail-closed gate lives at the top of _run_optimization_impl: assert_industry_cap_unavailable(requested=req.industry_cap is not None) raises ValueError('industry mapping unavailable') before any solve/artifact write; the 11-05 wrapper records it as a failed run with failure_reason == 'industry mapping unavailable' — never silently ignored (pitfall 8, T-11-06)."
  - "constraint_stack_json records industry_cap: null (unrequested) on every path — HRP, non-optimal, and success — alongside the existing cap/min_cash/turnover_coef/reference fields and policy_version 'phase-11-policy-v1'. The failed-run stack (11-05 _record_failed_run) already carries the requested cap verbatim."
  - "Covariance identity is canonical 8-decimal: covariance_sha256(cov) hashes the matrix rounded to 8 decimals serialized as a list-of-lists with sort_keys + compact separators + ensure_ascii False — byte-identical to PortfolioArtifactService.write_bundle's covariance.json (which now also rounds to 8 decimals), so the artifact bytes hash to the recorded digest and Phase 12 can checksum-verify the load."
  - "risk_model_json carries the full recorded step: risk_model, window, dropna, psd_repair provenance, covariance_sha256, and (on artifact-writing paths) covariance_artifact_relative_path = research_artifacts/<run_id>/covariance.json — the Phase 12 risk-suite seam (PFOL-01)."
  - "fixture_composite now writes a real signals.json artifact and records output_sha256 = sha256(bytes), so the checksum-verified snapshot binding path (11-05/11-06) reads actual artifact bytes instead of a stub."

patterns-established:
  - "Industry-cap fail-closed through the orchestrator: INDUSTRY_CAP_ENABLED=False hard gate (constraints.py, from 11-01) + run_optimization wiring; requesting a cap always lands a failed run with the exact reason — the constraint is never silently dropped."
  - "Covariance artifact breadth: covariance.json written (O_EXCL + fsync + sha256) with canonical 8-decimal rounding; covariance_sha256 recorded in risk_model_json; read_artifact checksum-verifies against the digest (Phase 12 seam)."
  - "Grep-gate hygiene: no sector/industry JOIN in backend/app/portfolio/ (pitfall 8); np.clip on eigenvalues appears only inside repair_psd in risk.py (the only other np.clip is on correlation values in hrp.py, pre-existing, not eigenvalues)."

requirements-completed: [PFOL-01, PFOL-03]

coverage:
  - id: D1
    description: "Industry-cap fail-closed gate wired through run_optimization — a requested industry_cap records a failed run with failure_reason 'industry mapping unavailable'; unrequested runs record industry_cap: null in constraint_stack_json"
    requirement: PFOL-03
    verification:
      - kind: integration
        ref: "tests/portfolio/test_optimizer.py#test_industry_cap_requested_fails_closed_with_failed_run"
        status: pass
      - kind: integration
        ref: "tests/portfolio/test_optimizer.py#test_no_industry_cap_records_null_in_constraint_stack"
        status: pass
    human_judgment: false
  - id: D2
    description: "Covariance artifact + sha256 in risk_model_json — covariance_sha256 deterministic + discriminating (canonical 8-decimal identity); the repaired covariance's digest round-trips through read_artifact(covariance.json); a successful run's risk_model_json records covariance_sha256 (64 hex) + the artifact path and the artifact checksum-verifies"
    requirement: PFOL-01
    verification:
      - kind: unit
        ref: "tests/portfolio/test_risk.py#test_covariance_sha256_is_deterministic_and_discriminating"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_risk.py#test_covariance_sha256_digest_roundtrips_through_covariance_artifact"
        status: pass
      - kind: integration
        ref: "tests/portfolio/test_optimizer.py#test_successful_run_records_covariance_sha256_and_artifact"
        status: pass
    human_judgment: false

# Metrics
duration: 75min
completed: 2026-08-01
status: complete
---

# Phase 11 Plan 11-06: Constraint Hardening + Artifact Breadth Summary

**Industry-cap fail-closed gate wired through `run_optimization` — a requested cap lands a `failed` run with reason `"industry mapping unavailable"` (never silently ignored, PFOL-03/pitfall 8), and the covariance matrix becomes an immutable, checksum-verified artifact (`covariance.json` + `covariance_sha256` + artifact path in `risk_model_json`) that Phase 12 can load by digest (PFOL-01)**

## Performance

- **Duration:** 75 min
- **Started:** 2026-08-01T19:10:00Z
- **Completed:** 2026-08-01T20:25:00Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- **Industry-cap fail-closed gate through the orchestrator** — `OptimizationRequest` gains `industry_cap: float | None` (schemas.py). At the top of `_run_optimization_impl`, `assert_industry_cap_unavailable(requested=req.industry_cap is not None)` raises `ValueError("industry mapping unavailable")`; the 11-05 fail-closed wrapper catches it and records a `failed` run with `failure_reason == "industry mapping unavailable"` — the constraint is never silently dropped (pitfall 8, T-11-06). The failed-run constraint stack records the requested cap verbatim; unrequested runs record `industry_cap: null` on every path (HRP / non-optimal / success) with `policy_version: "phase-11-policy-v1"`.
- **Covariance artifact + sha256 breadth** — `risk.py` adds `covariance_sha256(cov)` over the canonical 8-decimal JSON of the matrix (sort_keys + compact separators + `ensure_ascii=False`, byte-identical to the artifact serializer). `artifacts.py` `write_bundle` now rounds the covariance to 8 decimals before writing `covariance.json`, so the artifact bytes hash to exactly the recorded digest. `_build_risk_model` records `covariance_sha256` in `risk_model_json`; the HRP and success paths record `covariance_artifact_relative_path` (`research_artifacts/<run_id>/covariance.json`) alongside `risk_model`, `window`, `dropna`, and `psd_repair` provenance — the full recorded step incl. the covariance identity (PFOL-01, Phase 12 seam).
- **Breadth locked by tests** — `test_risk.py`: `covariance_sha256` is deterministic and discriminating (identical matrices → identical 64-hex digests; a 1e-9 perturbation is below the 8-decimal resolution; a material change differs), and the repaired covariance's digest round-trips through `read_artifact("covariance.json")`. `test_optimizer.py`: `industry_cap=0.05` records a `failed` run with the exact reason; a no-cap run records `constraint_stack_json["industry_cap"] is None`; a successful run's `risk_model_json` carries `covariance_sha256` (64 hex) + the artifact path, and the artifact checksum-verifies under the run namespace; the schema field defaults to `None` and carries a requested cap verbatim.
- **Fixture hardening (shared infra)** — `fixture_composite` now writes a real `signals.json` artifact under the app-data root and records `output_sha256 = sha256(bytes)`, so the checksum-verified snapshot-binding path reads actual bytes rather than a stub — required for the covariance-artifact tests that resolve the same run namespace.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire the industry-cap fail-closed gate through `run_optimization`** - `38eb764` (feat)
2. **Task 2: Covariance artifact + sha256 in `risk_model_json`** - `696285c` (feat)
3. **Task 3: Extend `test_risk.py` + `test_optimizer.py` — covariance sha256 + industry-cap gate** - `c74ee55` (test)
4. **Fixture: `fixture_composite` writes a real checksum-bound composite artifact** - `9dae063` (test)

**Plan metadata:** complete (this summary)

## Files Created/Modified

- `backend/app/portfolio/optimizer.py` - `assert_industry_cap_unavailable` wired at the top of `_run_optimization_impl`; `industry_cap: req.industry_cap` in all three constraint stacks; `covariance_sha256` in `_build_risk_model`; `covariance_artifact_relative_path` recorded in HRP + success paths
- `backend/app/portfolio/risk.py` - `covariance_sha256(cov)` — canonical 8-decimal JSON sha256 identity
- `backend/app/portfolio/artifacts.py` - `write_bundle` rounds covariance to 8 decimals so artifact bytes hash to `covariance_sha256`
- `backend/app/portfolio/schemas.py` - `OptimizationRequest.industry_cap: float | None`
- `backend/tests/portfolio/test_risk.py` - 2 new tests: sha256 determinism/discrimination + artifact round-trip
- `backend/tests/portfolio/test_optimizer.py` - 4 new tests: industry-cap failed run, null stack recording, covariance artifact contract, schema nullability
- `backend/tests/portfolio/conftest.py` - `fixture_composite` writes a real checksum-bound `signals.json`

## Decisions Made

- **Gate placement** — the industry-cap assertion is the FIRST statement in `_run_optimization_impl`, before any solve or artifact write, so a requested cap can never partially execute or write artifacts for a run that must fail.
- **Canonical 8-decimal covariance identity** — `covariance_sha256` and `write_bundle` share the same rounding/serialization contract (`sort_keys`, compact separators, `ensure_ascii=False`, `allow_nan=False`), making `read_artifact("covariance.json", checksum_sha256=recorded_digest)` the Phase 12 load path.
- **Constraint-stack null recording** — `industry_cap: null` is recorded on every successful/non-optimal path so the audit trail is uniform regardless of whether the field was ever requested.
- **Failed-run stack carries the requested cap** — `_record_failed_run` (11-05) records `industry_cap` verbatim so the audit row shows exactly what was requested and why it failed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `covariance_sha256` must match the artifact bytes exactly**
- **Found during:** Task 2 (covariance artifact wiring)
- **Issue:** The plan specified a canonical JSON sha256 "matching `_json`", but `write_bundle` serialized the covariance as `[row.tolist() for row in covariance]` (full-precision floats) while the digest was computed over 8-decimal-rounded values — the digest and the artifact checksum would never match, breaking the Phase 12 checksum-verified load.
- **Fix:** Rounded the covariance to 8 decimals inside `write_bundle` before serialization, so the artifact bytes hash to exactly `covariance_sha256(cov)`. Verified: descriptor checksum == digest, and a read-back matrix re-hashes to the same digest.
- **Files modified:** backend/app/portfolio/artifacts.py
- **Verification:** `pytest tests/portfolio/test_risk.py -q --tb=short` → 8 passed (incl. the round-trip case).
- **Committed in:** `696285c` (Task 2 commit)

**2. [Rule 2 - Missing Critical] `fixture_composite` needed a real artifact for the checksum-bound path**
- **Found during:** Task 3 (covariance-artifact test needs the run namespace to resolve)
- **Issue:** `fixture_composite` recorded `output_sha256="f"*64` with no artifact bytes on disk; the run's snapshot binding would fail on checksum verification whenever a test exercised the real artifact path.
- **Fix:** `fixture_composite` now writes a real `signals.json` under `artifact_root/research_artifacts/<id>/` and records `output_sha256 = sha256(bytes)`, keeping the run-row audit root `input_snapshot_sha256 == "f"*64` contract intact.
- **Files modified:** backend/tests/portfolio/conftest.py
- **Verification:** full `tests/portfolio` suite → 63 passed.
- **Committed in:** `9dae063`

---

**Total deviations:** 2 auto-fixed (missing critical, both required for the plan's own success criteria — the checksum-verified covariance seam and the fixture's real artifact bytes)
**Impact on plan:** None beyond the plan's stated success criteria. No scope creep.

## Issues Encountered

- **Parallel-agent coordination (with Exec1105, 11-05)** — 11-06 started while 11-05 was mid-flight. Coordinated over IRC: Exec1105 committed its 11-05 work first (optimizer.py fail-closed wrapper), and I re-applied my `industry_cap` + covariance wiring onto the post-11-05 tree so each plan's commits stayed clean. A half-finished `conftest.py` edit briefly broke `test_pipeline.py` (NameError `output_sha256`); it was completed (real artifact write) and verified green before either agent's gate. Final: 11-05 (7 commits) then 11-06 (4 commits) on the same tree, both gates green.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Phase 12 risk suite** — `risk_model_json` now carries `covariance_sha256` + `covariance_artifact_relative_path`; `read_artifact(run_id/covariance.json, checksum_sha256=covariance_sha256)` is the checksum-verified load path for the covariance matrix (immutable artifact seam).
- **Phase 14 RebalancePlan / Phase 15 API** — unchanged seams; constraint_stack_json now uniformly includes `industry_cap` so downstream audit/UI can render the fail-closed policy.
- **Industry cap** — remains deferred (fail-closed) until a governed industry mapping exists; the gate is wired through the orchestrator so enabling it later is a `constraints.py` change plus the mapping implementation.
- **Blockers/concerns:** none. Per-plan gate `pytest tests/portfolio -q --tb=short` → 63 passed. Grep gates: no sector/industry JOIN in `backend/app/portfolio/`; `np.clip` on eigenvalues appears only inside `repair_psd` in `risk.py` (the only other `np.clip` is on correlation values in `hrp.py`, pre-existing, not eigenvalues). Full-suite pytest deliberately NOT run (phase gate after all plans, per batch constraints).

## Self-Check: PASSED

All 7 files present on disk; all 4 plan commits present in git history (`38eb764`, `696285c`, `c74ee55`, `9dae063`). Per-plan gate re-run after the final commit: `pytest tests/portfolio -q --tb=short` → 63 passed; cross-module `test_snapshot_binding.py + test_repository.py + test_models.py` → 24 passed. Grep gates clean as documented above.

## Self-Check: PASSED (post-write re-verification)

Re-verified after writing this summary: `38eb764`, `696285c`, `c74ee55`, `9dae063` all present in git history; all 7 modified files + this summary on disk; per-plan gate green (63 passed); cross-module green (24 passed).
