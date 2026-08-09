# Plan 47-03 Summary: Admission Exposure + Candidate-Ledger Linkage + No-Edit Fingerprint

**Plan:** 47-03 (wave 2)
**Phase:** 47-governed-scoring-admission
**Status:** Complete
**Date:** 2026-08-08

## Objective

Expose admission verdicts against candidate identities and harden the no-edit guarantee
(AF-REQ-08 SC4). The gates already expose `observed`/`threshold`/`pass-fail`/`reason` per
gate and the thresholds are fixed module constants (`admission.py:40-48,243-320`), so the
work was (a) link each verdict to the candidate ledger via the exploratory revision id
(47-01), recording the terminal status + gate trail as an append-only fact, and (b) make
the no-edit guarantee explicit and fail-closed: an `ADMISSION_POLICY_FINGERPRINT` frozen
into the manifest and verified at scoring, plus a static guard that factory/Agent scoring
cannot edit thresholds, reorder gates, or convert rejection into admission. Depends on
47-01 (exploratory revision binding) and is coordinated with 47-02 (distinct
`run_contract.py` region per plan-check W1). Zero new runtime dependencies.

## Commits

| Hash | Message |
|------|---------|
| `6d6d835` | feat(phase-47): candidate-ledger-linked admission verdict (47-03-01) |
| `2d17f52` | feat(phase-47): ADMISSION_POLICY_FINGERPRINT + no-edit hardening (47-03-02) |

## What Was Delivered

### `backend/app/research/alpha_scoring.py` (modified) — Task 47-03-01

Candidate-ledger-linked admission verdict (AF-REQ-08 SC4). New export:

- **`record_candidate_admission(*, repo, registry, attempt, revision, universe, start, end,
  horizon, asset_type, engine, admitted_ic_series=None, universe_resolver=None,
  rebalance="daily", warmup_days=0, n_groups=2, catalog=None, artifact_service=None)
  -> dict`** — resolves the exploratory revision's provenance
  (`run_id`/`candidate_id`/`candidate_digest`, minted by 47-01) so the verdict row joins
  the candidate ledger, then runs `run_admission` — passing NO threshold/gate-order kwargs
  (none exist) — and appends one append-only candidate attempt row carrying the terminal
  status (`admitted`/`rejected`/`failed`) and a `reason` mapping
  `{"verdict", "failing_gate", "gate_trail", ...candidate-identity}`.
  - A clean gate failure records `status='rejected'` with the failing gate name + full gate
    trail.
  - An evaluation/chain failure (`run_admission` raising `ValueError`/`SignalChainError`)
    is caught and recorded as `status='failed'` with the terminal diagnostic — rejection is
    never converted to admission and failure is never a zero score (AF-REQ-07).
  - The status is sourced verbatim from the verdict; the appended row is a distinct
    append-only fact linked to the generation attempt by `candidate_digest`.
- **`_json_safe(value)`** — recursively replaces non-finite floats with `None` so the gate
  trail embedded in the ledger `reason` survives `validate_bounded_json` (the authoritative
  `gates_json` in the verdict row is stored via the repo's tolerant serializer).

### `backend/app/research/admission.py` (modified) — Task 47-03-02

Fail-closed admission policy fingerprint + no-edit surface. New exports:

- **`ADMISSION_GATE_ORDER`** — `("no_lookahead", "coverage", "no_label_leakage",
  "similarity_dedup", "train_ic", "val_ic")`, declaring the gate order as part of the
  policy (mirrors the live sequence in `run_admission`).
- **`admission_policy_fingerprint() -> str`** — SHA-256 over `{"policy_version",
  "thresholds": {the seven fixed constants}, "gate_order"}` via
  `run_contract.digest_bytes` (canonical JSON + finite check), reading the live constants at
  call time so a mutated constant or reordered gate produces a different digest.
- **`ADMISSION_POLICY_FINGERPRINT`** — the frozen value, computed at module load.
- **`verify_admission_policy_fingerprint(frozen) -> None`** — recomputes from the live
  constants and raises `AdmissionPolicyMismatchError` on any mismatch/missing value, called
  before any candidate is scored.
- **`AdmissionPolicyMismatchError`** — `ValueError` subclass with structured
  `frozen`/`live` attributes (mirrors the 46-01 `VocabularyMismatchError` pattern).

### `backend/app/research/run_contract.py` (modified) — Task 47-03-02

Server-owned policy fingerprint (T-47-10), in the `freeze_input_snapshot`/`policy` region
(distinct from 47-02's `validate_manifest` scoring block per plan-check W1):

- **`freeze_input_snapshot`** populates `manifest["policy"]["fingerprint"] =
  ADMISSION_POLICY_FINGERPRINT` after fingerprint normalization, so a client-supplied value
  cannot survive freeze (mirrors the 46-01 vocabulary-fingerprint normalization). The
  frozen value is part of the canonical manifest digest.
- **`validate_manifest`** validates the `policy.fingerprint` shape (lowercase 64-hex via
  `validate_sha256`) when present; `policy.thresholds` remains informational provenance and
  is NOT required.
- **`ResearchInputSnapshot.policy_fingerprint`** — property accessor for the frozen
  admission policy fingerprint.

### `backend/app/research/alpha_scoring.py` (modified) — Task 47-03-02

Fail-closed verification wiring + no-edit guard. New exports:

- **`record_candidate_admission`** now calls `verify_admission_policy_fingerprint` at the
  top (resolving the frozen value from the persisted run snapshot via
  `_frozen_policy_fingerprint` → `repo.get_run_snapshot`) BEFORE running admission — a
  divergent policy raises `AdmissionPolicyMismatchError` rather than re-scoring a stored
  run under a changed policy.
- **`assert_admission_no_edit() -> None`** — a source-level (structural) guard mirroring
  `assert_all_scoring_through_chain` (plan-check W3) confirming: (1) `run_admission` exposes
  no threshold/gate-order parameters (`_run_admission_signature_clean`); (2) no scoring
  module (`alpha_factory`/`evaluation`/`walkforward`) assigns to an admission threshold
  constant (`_source_mutates_policy`); and (3) none calls `insert_admission_verdict`
  directly (`_source_inserts_verdict`) — the only admission write path is `run_admission` →
  `_record_verdict`.

## Verification

All task-level pytest selections green; the existing gate contracts are unaffected (the
fingerprint is additive — gates still read the same constants in the same order).

| Command | Result |
|---------|--------|
| `pytest tests/research/test_admission.py -k 'candidate or ledger or verdict or rejected or failed or admitted' -q` (47-03-01) | **8 passed** |
| `pytest tests/research/test_alpha_scoring.py -k 'admission or verdict' -q` (47-03-01) | **6 passed** |
| `pytest tests/research/test_admission.py -k 'fingerprint or policy or no_edit or mismatch' -q` (47-03-02) | **11 passed** |
| `pytest tests/research/test_run_contract.py -k 'policy or freeze' -q` (47-03-02) | **10 passed** |
| `pytest tests/research/test_alpha_scoring.py -k 'no_edit' -q` (47-03-02) | **4 passed** |
| `pytest tests/research/test_admission.py -q` (plan final — additive fingerprint) | **20 passed** |
| `pytest tests/research/ -q` (full research sweep — freeze-change regression) | **448 passed** |

## Test totals

- **New tests added:** 5 in 47-03-01 (4 in `test_alpha_scoring.py` +
  `test_record_candidate_admission_links_verdict_to_candidate_ledger` in `test_admission.py`)
  and 19 in 47-03-02 (10 in `test_admission.py`, 5 in `test_run_contract.py`,
  4 in `test_alpha_scoring.py`) — **24 new tests**.
- **Target-file baseline → final:** 175 passed → 199 passed (+24).
- **Full research sweep:** 448 passed, 0 failed (the `policy.fingerprint` freeze change is
  backward-compatible — no digest is pinned to a literal value; all freeze assertions are
  stability checks).

## Deviations

1. **`_json_safe` gate-trail sanitization (47-03-01).** The candidate-ledger `reason` is
   validated by `validate_bounded_json`, which rejects non-finite numbers; admission gate
   `observed` values can be non-finite for a degenerate panel (e.g. an undefined
   shifted-label IC over a two-date panel). The verdict row stores the authoritative
   `gates_json` via the repo's tolerant serializer; the embedded ledger trail sanitizes
   non-finite → `null` without dropping trail structure. Not named in the plan but required
   for the ledger `reason` to be storable.
2. **`AdmissionPolicyMismatchError` constructor (47-03-02).** The plan names the error but
   not its signature; mirrored the 46-01 `VocabularyMismatchError(frozen=..., live=...)`
   pattern with structured `frozen`/`live` attributes for diagnostics.
3. **Policy fingerprint resolved from the run snapshot (47-03-02).** Plan point (3) calls
   `verify(snapshot.policy_fingerprint)`, but `record_candidate_admission`'s signature
   carries no snapshot; the frozen value is resolved from the persisted run snapshot via
   `repo.get_run_snapshot(run_id)`. A `ResearchInputSnapshot.policy_fingerprint` accessor
   was added for direct snapshot holders.
4. **No-edit guard is source-level/structural (47-03-02).** Per plan-check W3,
   `assert_admission_no_edit` inspects signatures and module source; it cannot see dynamic
   dispatch or runtime monkeypatching. Documented in its docstring; the live-constant
   recompute in `verify_admission_policy_fingerprint` is the behavioral backstop at scoring
   time.
5. **Pre-existing lint untouched.** `I001` (import sorting / long import line) and `SIM102`
   in the touched files pre-date this plan and were left as-is (not introduced here).

## Hand-off

To **47-04** (deterministic selection + selection-OOS exactly-once): the
candidate-ledger-linked admission verdict (terminal status + gate trail), the admitted
population (consume `status='admitted'`), the fail-closed `ADMISSION_POLICY_FINGERPRINT`
(verified before scoring), and the exploratory revision id as the stable join key.
`run_contract.py` was edited only in `freeze_input_snapshot`/`policy` (distinct from
47-02's `validate_manifest` scoring block) per plan-check W1.
