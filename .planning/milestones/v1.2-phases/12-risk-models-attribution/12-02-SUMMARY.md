---
phase: 12-risk-models-attribution
plan: 12-02
subsystem: database
tags: [sqlite, migrations, append-only, risk-models, evidence, pytest]

# Dependency graph
requires:
  - phase: 11-portfolio-optimization
    provides: portfolio_optimization_runs append-only table + triggers, portfolio/risk.py sample covariance + PSD provenance, tests/portfolio/conftest.py fixtures
provides:
  - portfolio_risk_attribution_evidence append-only table (attribution_type/risk_model enums, sha256 + reconciliation CHECKs, run_id FK, immutability triggers)
  - portfolio_optimization_runs risk_model CHECK widened to the 4-model enum (option-a table rebuild)
  - Wave 0 test scaffolding: test_attribution.py + test_drawdown.py (new), test_risk.py new-model RED cases, conftest fixture_returns_long + fixture_attribution_run, migration test coverage
affects: 12-01 (tracer), 12-03 (risk-model breadth), 12-04 (attribution breadth), 12-06 (drawdown breadth), 12-05 (cross-model)

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 143
  tasks: 3
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One-way-door schema migration: table rebuild via ALTER RENAME TO _legacy + recreate + copy + drop, wrapped in PRAGMA foreign_keys OFF/ON, for a CHECK widening SQLite cannot ALTER"
    - "Append-only evidence table: CHECK enums + length/sha256 + reconciliation invariant CHECK + no_update/no_delete triggers (Phase 10/11 pattern)"
    - "RED scaffold: new test files import modules created by later plans so the suite is provably failing until the tracer/breadth plans land"

key-files:
  created:
    - backend/tests/portfolio/test_attribution.py
    - backend/tests/portfolio/test_drawdown.py
  modified:
    - backend/app/operational/migrations.py
    - backend/tests/test_operational_migrations.py
    - backend/tests/portfolio/conftest.py
    - backend/tests/portfolio/test_risk.py

key-decisions:
  - "Approved one-way-door option-a: widen portfolio_optimization_runs.risk_model CHECK to the 4-model enum via a table rebuild (Phase 7 pattern) in the SAME migration script as the evidence table — run-level risk-model selection supported for Phase 13; Phase 11 rows survive (proven by test)"
  - "The runs-table rebuild runs BEFORE the evidence CREATE in the script so the evidence run_id FK binds to the final runs table (renaming runs after the FK exists would re-point the FK to the _legacy table)"
  - "Evidence schema follows the plan verbatim: reconciliation_json NOT NULL for every evidence row (the plan's CHECK is (attribution_type = 'exposure_contribution') = (reconciliation_json IS NOT NULL), which with NOT NULL reconciliation makes both types carry reconciliation — drawdown carries period_count/max_depth/longest_period/segment_max_abs_error per 12-01/12-06)"

patterns-established:
  - "Append-only evidence tables follow the Phase 10/11 template: enums + 64-hex sha256 + invariant CHECK + run_id FK ON DELETE RESTRICT + no_update/no_delete triggers"
  - "One-way-door CHECK widening follows the Phase 7 rebuild pattern (rename legacy → recreate → INSERT SELECT → drop legacy) wrapped in PRAGMA foreign_keys OFF/ON"
  - "Test scaffolding is provably RED: missing modules/functions fail collection/import so the exact later-plan tests turn green"

requirements-completed: [RSK-01, RSK-02, RSK-03]

# Coverage metadata (#1602) — one entry per shipped deliverable.
coverage:
  - id: D1
    description: "portfolio_risk_attribution_evidence append-only table migrates with attribution_type/risk_model enums, 64-hex output_sha256 CHECK, reconciliation invariant CHECK, run_id FK ON DELETE RESTRICT, and no_update/no_delete triggers"
    requirement: RSK-01
    verification:
      - kind: unit
        ref: "backend/tests/test_operational_migrations.py#test_phase12_attribution_evidence_migrate_with_constraints_and_idempotence"
        status: pass
    human_judgment: false
  - id: D2
    description: "portfolio_optimization_runs risk_model CHECK widened to the 4-model enum via table rebuild; Phase 11 rows survive column-for-column and the evidence FK binds to the rebuilt table"
    requirement: RSK-02
    verification:
      - kind: unit
        ref: "backend/tests/test_operational_migrations.py#test_phase12_risk_model_enum_widened"
        status: pass
      - kind: unit
        ref: "backend/tests/test_operational_migrations.py#test_phase12_rebuild_preserves_phase11_run_rows"
        status: pass
    human_judgment: false
  - id: D3
    description: "Wave 0 test scaffolding: test_attribution.py (RSK-01), test_drawdown.py (RSK-03), test_risk.py new-model RED cases (RSK-02), conftest fixture_returns_long + fixture_attribution_run — all provably RED until 12-01/12-03 land"
    requirement: RSK-03
    verification:
      - kind: unit
        ref: "backend/tests/portfolio/test_attribution.py (collection error until 12-01 creates app.portfolio.attribution)"
        status: unknown
    human_judgment: true
    rationale: "The scaffolds are intentionally RED by design (missing modules created by later plans). The verifier must confirm the scaffolds fail for the missing-module reason, not a defect, and that 12-01/12-03 turn them green."

# Metrics
duration: 35min
completed: 2026-08-02
status: complete
---

# Phase 12 Plan 12-02: Wave 0 Foundations Summary

**Append-only attribution-evidence migration (portfolio_risk_attribution_evidence) plus the 4-model risk_model enum widening via the Phase 7 table-rebuild pattern, and the Wave 0 RED test scaffolding (test_attribution / test_drawdown / test_risk new-model cases / conftest fixtures) every later plan builds on**

## Performance

- **Duration:** 35 min
- **Started:** 2026-08-02T00:00:00Z
- **Completed:** 2026-08-02T00:35:00Z
- **Tasks:** 3 (1 checkpoint:decision auto-approved as instructed — the one-way door was ALREADY approved by the user; 2 executed)
- **Files modified:** 6

## Accomplishments

- `portfolio_risk_attribution_evidence` lands as ONE new atomic migration script: attribution_type/risk_model CHECK enums, 64-hex `output_sha256`, the reconciliation invariant CHECK, `run_id` FK → `portfolio_optimization_runs` ON DELETE RESTRICT, `idx_attribution_evidence_run(run_id, attribution_type)`, and `no_update`/`no_delete` immutability triggers (T-12-04 mitigation).
- `portfolio_optimization_runs.risk_model` CHECK widened from `sample_covariance_v1` to the 4-model enum (`sample_covariance_v1 | semi_covariance_v1 | ewma_covariance_v1 | ledoit_wolf_v1`) via the approved option-a table rebuild — same columns/constraints/triggers, rows copied column-for-column (proven by a dedicated rebuild-preservation test).
- The runs rebuild executes BEFORE the evidence CREATE so the evidence FK binds to the FINAL runs table; `PRAGMA foreign_keys = OFF/ON` wraps the rebuild (Phase 7 pattern), and the full script advances `PRAGMA user_version` to 28.
- Wave 0 RED scaffolding: `test_attribution.py` (RSK-01: variance reference, sum(MC)==variance rtol 1e-12, signed exposure, perturbed-MC rejection), `test_drawdown.py` (RSK-03: underwater-curve reference, empty-period identities, constructed-segment detection, min_obs threshold), `test_risk.py` (RSK-02: semi/EWMA/Ledoit-Wolf references, `make_risk_model_family` dispatch, sklearn lazy-import subprocess gate), and conftest `fixture_returns_long` (engineered obs 8-11 dip) + `fixture_attribution_run` (records an optimal min-vol run via `run_optimization`).

## Task Commits

Each task was committed atomically:

1. **Task 1: checkpoint:decision — evidence table + risk-model enum (one-way door)** — `c2af05f` (feat(12-02): the migration script implementing the already-approved option-a; no re-prompt per the batch constraint)
2. **Task 2: build — append the evidence migration + runs-table CHECK widening + migration tests** — `c2af05f` (same atomic commit: schema + tests landed together, matching the plan's "build" task scope)
3. **Task 3: test — scaffold the new test files + extend fixtures** — `e9b85c6` (test(12-02): Wave 0 RED scaffolding)

## Files Created/Modified

- `backend/app/operational/migrations.py` - Appended migration #28: rebuild `portfolio_optimization_runs` with the 4-model `risk_model` CHECK (Phase 7 pattern, rows copied) then CREATE `portfolio_risk_attribution_evidence` with enums/sha256/reconciliation CHECKs + triggers
- `backend/tests/test_operational_migrations.py` - New `test_phase12_risk_model_enum_widened`, `test_phase12_attribution_evidence_migrate_with_constraints_and_idempotence` (forward-only, CHECK/trigger/FK cases), and `test_phase12_rebuild_preserves_phase11_run_rows`
- `backend/tests/portfolio/conftest.py` - `fixture_returns_long` (24×4 seeded matrix with engineered obs 8-11 drawdown, recovered by obs 13) and `fixture_attribution_run` (optimal min-vol run on the fixture composite)
- `backend/tests/portfolio/test_attribution.py` - (new) RSK-01 RED scaffold: variance/MC/exposure references + hard reconciliation rejection
- `backend/tests/portfolio/test_drawdown.py` - (new) RSK-03 RED scaffold: underwater curve, empty-period identities, constructed segment, min_obs
- `backend/tests/portfolio/test_risk.py` - RSK-02 RED cases: semi/EWMA/Ledoit-Wolf references, family dispatch, lazy-import subprocess gate

## Decisions Made

- **One-way-door option-a approved (user pre-approved; no re-prompt per batch constraint):** widen the runs-table `risk_model` CHECK to the 4-model enum via table rebuild in the SAME migration as the evidence table. Run-level risk-model selection is fully supported (Phase 13 seam); Phase 11 rows survive (test-proven).
- **Rebuild-before-evidence ordering:** the runs rebuild runs first so the evidence table's `run_id` FK binds to the final runs table — renaming runs after the FK exists would re-point the FK to the `_legacy` table and break on drop.
- **`reconciliation_json TEXT NOT NULL` for every evidence row:** the plan's invariant CHECK `(attribution_type = 'exposure_contribution') = (reconciliation_json IS NOT NULL)` combined with NOT NULL makes both types carry reconciliation — exposure rows carry `{"portfolio_variance", "sum_contributions", "max_abs_error"}` (12-04), drawdown rows carry `{"period_count", "max_depth", "longest_period", "segment_max_abs_error"}` (12-06), per the plan's evidence-shape spec.

## Deviations from Plan

None - plan executed exactly as written. The checkpoint:decision task was auto-approved because the one-way door was already approved by the user (batch constraint explicitly directed skipping the re-prompt and implementing directly, option-a).

## Issues Encountered

- One ruff F541 error on line 490 of `tests/test_operational_migrations.py` is pre-existing (present in the HEAD version, confirmed via `git show HEAD:` + ruff) — a cosmetic f-string without placeholders in the Phase 11 `_run_row` helper. Left untouched per the scope boundary (out of task scope; not caused by this plan's changes). Two other pre-existing RUF005 findings at lines 131/245 are also untouched.

## Known Stubs

None — the RED scaffolds are intentional by design (they fail on missing modules/functions created by 12-01/12-03) and are tracked as coverage D3 for the verifier; no delivered implementation contains a stub.

## Next Phase Readiness

- Wave 1 (12-01 tracer) can start immediately: `portfolio_risk_attribution_evidence` exists with its invariants, `fixture_attribution_run` records an optimal run for the attribution spine, and the RED `test_attribution.py`/`test_drawdown.py` define exactly the contracts 12-01 turns green.
- Wave 2 (12-03) consumes the widened enum + the RED `test_risk.py` new-model cases + the sklearn lazy-import subprocess gate (sklearn 1.8.0 shadow extra verified importable).
- Phase 13/14 build on the widened `portfolio_optimization_runs.risk_model` and the append-only evidence contract.

---
*Phase: 12-risk-models-attribution*
*Completed: 2026-08-02*

## Self-Check: PASSED

All created files exist and both commits (c2af05f, e9b85c6) are present in git log.
