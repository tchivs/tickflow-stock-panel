# Phase 48-02 Summary — Stage 1 Contract + parse_factor Confirmation + Transient Proposal

**Plan:** 48-02 · **Wave:** 2 (depends_on: [48-01]) · **Requirements:** AF-REQ-12
**Status:** Complete · **Verified:** 2026-08-09

## What shipped

| Task | Artifact | Commit |
|---|---|---|
| 48-02-01 | `backend/app/research/agent_stage1.py` — `StageOneRequest`, `StageOneHypothesis`, `decode_stage1_payload`, `STAGE_ONE_SCHEMA_VERSION`/`STAGE_ONE_PROMPT_TEMPLATE_VERSION`, bounds | `0828178` |
| 48-02-02 | `research_alpha_proposals` migration + `record_stage1_proposal`/`list_stage1_proposals`; `Stage1Confirmed` + `confirm_stage1_hypotheses` (server `parse_factor` confirmation, partial labeling) | `7da4631` |
| 48-02-03 | `Stage1Result` + `Stage1Service.run` over the Agent seam (no-fallback, R2 partial labeling) | `cad819c` |

## Success-criteria evidence (AF-REQ-12 SC2)

- **Bounded thesis → strict schema → server confirmation.** `StageOneRequest` validates the thesis (`≤ MAX_JSON_STRING_CHARS`) and that `permitted_fields ⊆ factor_dsl.ALLOWED_FIELDS` / `permitted_functions ⊆` the DSL function set, with bounded-JSON-validated provenance mappings. `decode_stage1_payload` generalizes `_decode_provider_draft` (hypotheses.py:80-101) to a list of expressions: it is pure (no provider call, no input mutation) and rejects unknown/missing fields at **every** nesting level (top-level and per-hypothesis) with field-specific `ValueError`s, plus a `schema_version` mismatch and oversized lists/strings/enum as permanent failures.
- **Every persisted expression equals its server-canonical form.** `confirm_stage1_hypotheses` runs `parse_factor(expression).canonical_expression` for each decoded hypothesis (hypotheses.py:202-225 pattern). Kept proposals store the canonical form; `raw_expression` retains the provider text as provenance only (byte-match test: `rows[0]["canonical_expression"] == parse_factor(raw).canonical_expression`).
- **Transient — absent from the catalog.** Proposals live only in the append-only `research_alpha_proposals` table; `UPDATE`/`DELETE` raise `sqlite3.IntegrityError`. After recording a proposal, a `research_factor_revisions` lookup by `canonical_expression` returns nothing (catalog isolation, mirrors the 47-01 exploratory non-leakage guarantee).
- **No fallback (SC4).** A provider exception propagates `ProviderCallError` with **zero** proposal rows and a failed `research_alpha_analysis_attempts` row. A decode failure records a permanent `malformed_json`/`schema_violation` attempt row and raises. All-dropped parse escalates to a permanent `parse_failure` with no `status='proposed'` rows.
- **Partial labeling (R2).** When some (not all) hypotheses fail parse, the valid subset is kept (`status='proposed'`), each failure is a `status='dropped'` row + `validation_error`, `Stage1Result.partial=True`, and **every** persisted row carries the distinct `partial=1` flag — a degraded response cannot look equivalent to a clean complete one.

## Verification output

| Selection | Result |
|---|---|
| `pytest tests/research/test_agent_stage1.py -k 'schema or decode or stage1_request'` | **22 passed** |
| `pytest tests/research/test_agent_stage1.py -k 'confirm or canonical or proposal or catalog_isolation'` | **10 passed** |
| `pytest tests/research/test_agent_stage1.py -k 'stage1_service or partial or no_fallback'` | **8 passed** |
| `pytest tests/research/test_agent_stage1.py` (full Stage 1 suite) | **36 passed** |
| `pytest tests/research/test_hypothesis_workflow.py tests/research/test_factor_dsl.py` (baseline unaffected) | **36 passed** |
| `pytest tests/test_operational_migrations.py` (migration additive) | **23 passed** |
| `pytest tests/research/` (full research suite, no regressions from `repository.py`/`migrations.py`) | **560 passed** |

`test_agent_stage1.py` = 36 tests (6 request + 16 decode + 4 proposals-table + 6 confirm + 6 service). The new `research_alpha_proposals` table is additive; `PRAGMA user_version` advances by exactly one.

## Deviations & decisions

1. **`Stage1Service` owns provider/model/model_version, not the seam.** The plan sketches `seam.provider`/`seam.model`, but `AgentProviderSeam.request` (48-01) takes `provider`/`model`/`model_version` per-call by design (provider-agnostic seam). `agent_provider.py` is **not** in 48-02's `files_modified` and was left untouched (Wave-1 territory). `Stage1Service` stores `provider`/`model`/`model_version` as constructor attributes (mirroring `ConfiguredFactorHypothesisGateway`, hypotheses.py:139-141) and passes them to `seam.request(...)`. This satisfies "Stage 1 runs over the Agent seam" and records full provenance without modifying Wave-1 code.
2. **Decode / all-dropped failures record a distinct `+1` attempt row.** The seam records the transport attempt (ordinal *N*, `outcome='proposed'` on transport success, `parsed_output_sha256=None`). Because the table is append-only, a downstream decode failure or all-dropped parse cannot amend that row; `Stage1Service` records a **second** attempt row at ordinal *N+1* (`outcome='failed'`, `failure_class=malformed_json`/`schema_violation`/`parse_failure`, `validation_errors`) before raising. The ordinal pair (*N* transport-ok, *N+1* downstream-failed) is the audit trail; clean/partial runs keep just ordinal *N*.
3. **"No proposal rows" on all-dropped = no `status='proposed'` rows.** Task 48-02-02 writes a `status='dropped'` row for every failed hypothesis and "does NOT abort"; task 48-02-03 says all-dropped is "permanent failure with no proposal rows." Resolution: the dropped rows persist in **all** cases (including all-dropped) as audit evidence of why each expression failed (research §5.4 — record the failure, never synthesize a draft); `all_dropped` means zero `status='proposed'` rows plus a raised `ProviderCallError`. The acceptance test asserts `list_stage1_proposals(status='proposed') == []` while the dropped rows remain.
4. **Empty `canonical_expression` for dropped rows.** A parse failure leaves no canonical form. `record_stage1_proposal` permits an empty `canonical_expression` for a `status='dropped'` row (the column is `NOT NULL`; empty string satisfies it and unambiguously signals "no canonical form"), with `status='dropped'` + `validation_error` as the discriminators. Kept rows always carry `parse_factor(raw).canonical_expression`.
5. **`status='partial'` is reserved.** The `status` enum is `('proposed','partial','dropped')` (plan-specified). Kept hypotheses are `status='proposed'`; failed parses are `status='dropped'`; the distinct degraded flag is the separate `partial INTEGER` column (0/1) on every row (R2). `status='partial'` is unused in this phase (reserved for a future self-degraded proposal state).
6. **Repository class + test-path nits.** The plan references `AlphaRunRepository`; the concrete class is `ResearchRepository` (single repository class) — the proposal methods were added there in a **distinct region** (after the AnalysisRecord block, before `append_checkpoint`), leaving the checkpoint/evidence region for 48-03 (plan-check W1). The plan's verify path `tests/research/test_hypotheses_workflow.py` is `tests/research/test_hypothesis_workflow.py` (singular) in the tree; used the correct path. `proposal_digest` is `sha256(canonical_bounded_json(proposal_payload))` over the bounded proposal content.

## Handoff to 48-03 / 48-04

- **`Stage1Service.run` + `Stage1Result`** — the Stage 1 entry point over the seam; returns `confirmed` (`kept`/`dropped`/`validation_errors`/`all_dropped`/`partial`), `attempt_ordinal`, the distinct `partial` flag, and full provenance. 48-03 reads Stage 1 proposals via `list_stage1_proposals` and appends the stage-boundary checkpoint; 48-04 wires resume-from-checkpoint + the offline-fixture provider.
- **`list_stage1_proposals(run_id, *, attempt_ordinal=None, status=None)`** — the durable exploratory proposal read path (survives a crash) for Stage 2 and resume.
- **`STAGE_ONE_SCHEMA_VERSION` / `STAGE_ONE_PROMPT_TEMPLATE_VERSION`** — recorded on every proposal row and every `research_alpha_analysis_attempts` row; 48-03's Stage 2 + checkpoint consume them for provenance continuity.
- **`research_alpha_proposals`** is exploratory only; promotion to `factor_registry` is Phase 49 (AF-REQ-15) via `reviewed_draft` byte-match (hypotheses.py:227-246).
