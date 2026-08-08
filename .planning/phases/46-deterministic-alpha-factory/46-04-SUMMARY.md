# Plan 46-04 Summary: Budget Enforcement + Structural Diversity + Worker Integration

**Phase:** 46-deterministic-alpha-factory
**Plan:** 04 (Wave 3, final)
**Status:** COMPLETE
**Requirements:** AF-REQ-19, AF-REQ-23 (SC4)

## What was delivered

### Task 46-04-01: Additive `generated` candidate status
- **`migrations.py`**: Appended one additive Phase 46 migration that rebuilds
  `research_alpha_candidate_attempts` with `'generated'` in the status CHECK.
  Uses the Phase 7 FK-off rebuild pattern (CREATE `_v2` → INSERT → DROP → RENAME).
  The cross-table `research_alpha_lineage_same_run` trigger references this table
  in its WHEN clause, so it is dropped before and recreated after the rebuild
  (SQLite eagerly recompiles dependent triggers on schema change). The two
  append-only triggers and the same-run artifact guard are recreated on the
  rebuilt table. Data-preserving: all existing rows survive unchanged.
- **`run_contract.py`**: Added `"generated"` to `CANDIDATE_STATUSES` (ordered
  after `low_coverage`, matching the rebuilt CHECK).
- **`test_operational_migrations.py`**: 2 new tests — data-preservation rebuild
  (existing rows/ordinals/digests/statuses survive; CHECK accepts `generated`,
  rejects unknown; UNIQUE/FK/triggers preserved) and idempotent re-run.

### Task 46-04-02: Structural diversity without silent merging
- **`alpha_factory.py`**: Added `diversity_summary(candidate_features,
  population_features)` reusing `factor_registry._jaccard` for field and
  operator/function overlap, plus exact-structural-match and shape-match flags
  and a `most_similar_step` aggregate reference. Added `classify_candidate(
  validation, diversity)` → `invalid`/`duplicate`/`generated`. Defined
  `ALPHA_GENERATION_STATUSES`. Widened the import guard to permit
  `factor_registry` alongside `factor_dsl` and `run_contract`.
- **`test_alpha_factory.py`**: 15 new tests covering Jaccard metrics (hand-computed
  values), exact-duplicate classification, generated classification, empty
  population, shape-match-without-exact, no IC correlation, JSON serializability,
  and factory population diversity.

### Task 46-04-03: Server-side budget guard + token-fenced driver loop
- **`alpha_factory.py`**: Added `BudgetLimits` (frozen dataclass with
  `from_manifest` classmethod parsing `budgets.max_candidates`/`max_expressions`/
  `max_wallclock_seconds` + `grammar.max_depth`/`max_nodes`). Added `BudgetGuard`
  checking candidate-count, wall-clock (`time.monotonic`), and expression-count
  budgets at the TOP of each step (research Pitfall 4). Added
  `drive_alpha_generation` — the deterministic driver loop that runs one
  candidate per step through `validate_candidate` + `diversity_summary`,
  classifies, persists via the token-fenced adapter (candidate + lineage +
  bounded progress), and transitions to `completed` on budget exhaustion with a
  `terminal_reason` naming the exhausted budget. Tracks live `transition_version`
  across `update_progress` increments. Globally unique candidate/lineage IDs
  (`acand_{run_id}_{digest}`) for parallel-invariance.
- **`run_service.py`**: Added `append_candidate_lineage` principal-scoped wrapper.
- **`run_worker.py`**: Added token-fenced `append_candidate` and
  `append_candidate_lineage` callbacks (validate token via
  `_validate_attempt_token` before delegating to the service; fail closed on
  stale/invalid token).
- **`test_alpha_factory.py`**: 34 new tests covering BudgetLimits parsing,
  BudgetGuard exhaustion logic (candidate/wallclock/expression/candidate-first
  precedence/terminal-reason), end-to-end driver loop (candidate budget, ordinal
  order, progress counters, lineage edges), wallclock exhaustion (budget marker
  candidate + completed terminal), expression budget, worker token fencing
  (stale/missing token → no side effect), parallel invariance (two runs same seed
  → identical streams), and replay in ordinal order.

## Verification results

| Selection | Result |
|-----------|--------|
| `tests/test_operational_migrations.py -k 'atomic or restart or phase46'` | **6 passed** |
| `tests/research/test_alpha_factory.py -k 'diversity or duplicate or overlap'` | **13 passed** |
| `tests/research/test_alpha_factory.py -k 'budget or worker or ... guard'` | **34 passed** |
| `tests/research/test_alpha_factory.py` (full) | **152 passed** |
| `tests/research/test_alpha_factory.py tests/research/test_run_contract.py` | **269 passed** |

## Commits

| Hash | Message |
|------|---------|
| `5b46598` | feat(phase-46): 46-04-01 add generated candidate status via additive migration |
| `da13300` | feat(phase-46): 46-04-02 structural diversity accounting without silent merging |
| `4794859` | feat(phase-46): 46-04-03 budget guard + token-fenced generation driver loop |
| `2f7a5ad` | fix(phase-46): remove pre-existing Phase 45 WIP contamination from 46-04-03 |
| `b81ab3a` | fix(phase-46): remove Phase 45 WIP from service/worker, align test to HEAD contract |

## Deviations

- The 46-04-03 commit initially captured pre-existing Phase 45 WIP changes to
  `run_service.py` and `run_worker.py` (token-fenced service-level parameters
  that assume repository-level fencing not in the committed code). Two follow-up
  fix commits reverted the WIP contamination. A sibling executor concurrently
  landed the Phase 45 fencing work (commits `5b48547`, `411aedb`, `55c1249`).
  Final state: all 269 integration tests pass after clearing stale `.pyc` cache.
- The `research_alpha_lineage_same_run` trigger (cross-table reference to
  `research_alpha_candidate_attempts`) required drop/recreate around the table
  rebuild — a deviation from the plan's literal "two append-only triggers"
  wording, necessary because SQLite eagerly recompiles dependent triggers.

## Phase 46 status

Phase 46 is complete: a deterministic, replay-stable candidate population with
versioned vocabulary, validated expressions, budget enforcement, and structural
diversity. Hand off to Phase 47 (governed scoring/admission) which resolves
`generated` candidates into `admitted`/`rejected`/`failed` and adds IC-series
correlation.
