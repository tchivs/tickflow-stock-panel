# Phase 50-02 Summary — Compare + Tier-1 Stress Matrix + Replay-Branch + Clone

**Phase:** 50-replay-workbench
**Plan:** 02 (wave 2, depends_on 50-01)
**Requirements:** AF-REQ-20, AF-REQ-22 (also closes the AF-REQ-18 SC2 replay/clone half)
**Status:** COMPLETE — all four tasks test-first, all verification green

## What landed

The wave-2 evidence/action surfaces of the Replay Workbench, layered on
50-01's read APIs as pure read-mostly projections over durable facts. No
opaque winner, no admission rewrite, no second generation path, no parent
mutation.

### Task 50-02-01 — side-by-side compare (SC3, AF-REQ-22)
`service.compare_candidates` + `projections.compare` + `GET /runs/{id}/compare`.
Exposes every requested candidate's **configuration** (canonical_expression,
seed/step/operation/digest), **per-fold evidence** (`fold_evidence` projection —
IC/RankIC/ICIR/coverage/monthly robustness + cost diagnostics),
**admission verdict + gate_trail_digest**, **artifact refs**, and the
**diversity** structural signatures — all values exposed equally. There is
**never** an opaque aggregate/winner/rank/score key (asserted). An unknown
candidate among the set is skipped (graceful partial); cross-principal /
unknown runs return the same `None` → 404 boundary (no 403 leak).

### Task 50-02-02 — Tier-1 stress matrix (AF-REQ-20, SC3)
`service.stress_matrix` + `projections.stress_matrix` + `GET /runs/{id}/stress-matrix`.
Pure-arithmetic re-projection of the frozen `cost_diagnostics` over STORED
turnover under declared **fee_bps / slippage_bps / rebalance** values. The
baseline row equals the frozen `cost_diagnostics` verbatim (zero recomputation
at the declared config). The cost-rate helper mirrors
`evaluation._cost_rate` **exactly** (plan-check W2):
`commission_pct*2 + stamp_tax_pct + slippage_bps*2/1e4` — **not** the
shorthand `(fee+slippage)/1e4`. Recomputes **no** factor values, re-scores
nothing through the chain (raising fakes for evaluation/signal_chain/admission
asserted never called), writes nothing to admission. Tier-2 axes
(calendar_regime/coverage/symbol_subset) raise `NotImplementedError` → bounded
422 `not_implemented` (explicit deferral, never a fake result).

### Task 50-02-03 — branch replay (SC2)
`service.replay_branch` + `POST /runs/{id}/replay-branch`. Reconstructs
`AlphaFactory(seed)` from the frozen manifest, calls `replay_to(parent_step+1)`,
**asserts** the re-derived prefix digests equal the parent's first
`parent_step+1` candidates (determinism — raises on mismatch), then continues
generation into a NEW child run via the **existing** `create()` path (no second
generation path, risk #2). The child shares the parent's frozen
snapshot/manifest digests; the parent is byte-identical before/after.
Idempotent on the idempotency key (exactly-once child).

### Task 50-02-04 — clone (SC2)
`service.clone_run` + `projections.clone_diff` + `POST /runs/{id}/clone`.
Deep-merges **only** declared `scoring`/`costs`/`budgets` overrides over the
parent's frozen manifest; `seed`/`universe` are rejected (`CloneOverrideForbidden`
→ 422 — digest-change guarantee). A **no-op** clone (no dimension actually
changed) returns the parent run id verbatim with an empty diff
(unchanged-inputs-keep-their-hashes); a changed digested dimension delegates to
the existing `create()` and produces a new run id with a field-level diff
(risk #5). Parent never mutated.

## Commits

| hash | task | subject |
|---|---|---|
| `f9d84c2` | 50-02-01 + 50-02-02 | compare + Tier-1 stress matrix — side-by-side projection, no opaque winner (SC3, AF-REQ-20/22) |
| `c33b398` | 50-02-03 | replay-branch — seed re-derivation into a new child run (SC2) |
| `faeadba` | 50-02-04 | clone — overridable manifest dimensions into immutable create + field-level diff (SC2) |

Each commit used explicit `git add <file>` (3–5 files each); the ~68 pre-existing
unstaged frontend files and the unrelated unmerged `kline.py`/`screener.py` were
never touched. `frontend/src/pages/Watchlist.tsx` was zero-touch (verified).

## Test totals

- `test_alpha_compare.py`: **18** tests (compare + stress).
- `test_alpha_replay_clone.py`: **24** tests (replay-branch + clone).
- **42 new tests**, all green.

## Verification (run, green)

```
# Per-task focused selections
T1 compare : 18 passed
T2 stress  : 9 passed
T3 replay  : 11 passed
T4 clone   : 24 passed

# Plan verification block
pytest tests/research/test_alpha_compare.py tests/research/test_alpha_replay_clone.py \
      tests/research/test_run_contract.py -q   → 179 passed

# Boundary guards (scanned modules: run_service/projections/run_schemas/research_alpha)
pytest tests/test_phase45_guard.py tests/test_phase49_guard.py -q   → 62 passed
```

The new compare/stress/replay/clone surfaces are additive; the immutable create
contract is reused (not duplicated); the frozen snapshot/digest invariants hold;
the Phase 45/49 AST/import boundary guards stay green (the lazy
`alpha_factory` import carries no prohibited token; the stress path imports no
evaluation/admission collaborator).

## Deviations from the plan (all benign, documented)

1. **Commit grouping (compare + stress in one commit).** Tasks 50-02-01 and
   50-02-02 share the same test file (`test_alpha_compare.py`) and the same
   implementation surfaces (projections / DTOs / service / route), so they
   landed in a single atomic commit (`f9d84c2`) rather than two. replay-branch
   and clone each got their own commit. Every commit is atomic and test-first.

2. **No-op clone mechanism.** The plan stated `create()` returns the parent id
   for an identical manifest, but `create()` dedupes by `idempotency_key`, not
   manifest hash. `clone_run` therefore short-circuits a no-op
   (`changed == []`) and returns the parent run id directly **without** calling
   `create()`. Same observable behaviour (no-op → parent id verbatim, empty
   diff); the mechanism is the correct one for this idempotency model.

3. **rebalance Tier-1 axis.** True rebalance re-scoring needs the per-date
   weight series (Tier-2 territory), so the rebalance axis is a documented
   **turnover-frequency projection**: declared cadence → annual rebalance
   frequency (`daily=252 / weekly=52 / monthly=12`), `alt_turnover =
   total_turnover * freq(alt)/freq(declared)`, `cost_drag` at the frozen rate.
   Pure arithmetic over stored turnover, hand-computable; the `_REBALANCE_FREQUENCY`
   constant is the single source of truth (imported by both service and test).

4. **fee_bps axis semantics.** `fee_bps` is the round-trip fee+tax in basis
   points, replacing `(commission_pct*2 + stamp_tax_pct)` in `_cost_rate`:
   `cost_rate = fee_bps/1e4 + slippage_bps*2/1e4`. At the baseline
   `fee_bps = (commission_pct*2 + stamp_tax_pct)*1e4` this reproduces the
   frozen cost_rate **exactly** (plan-check W2), so the baseline row equals the
   frozen `cost_diagnostics` verbatim.

## Non-goals honoured

- No opaque winner/rank/score (SC3 — asserted in projections + tests).
- No admission write / factor re-score in the stress path (raising-fake proof).
- Tier-2 stress (calendar-regime/coverage/symbol-subset + a
  `research_alpha_stress_trials` table) remains the documented follow-up.
- No second generation path (replay-branch reuses `create()`).
- Parent runs never mutated (byte-identical snapshot/manifest/candidate ledger).
- Zero new runtime deps. `Watchlist.tsx` zero-touch.

## Hand-off

To **50-03** (frontend workbench): render the compare panel (no winner column),
the Tier-1 stress matrix, replay-branch / clone actions, and bind the
data-quality banner to `evidence_classification.clean` (from 50-01).
To **50-04** (release guard): scan the new compare/stress/replay/clone handlers
in `run_service.py` / `research_alpha.py` / `projections.py` for the prohibited
token set + broker/execution AST walk; assert the stress path imports no
admission-write collaborator.
