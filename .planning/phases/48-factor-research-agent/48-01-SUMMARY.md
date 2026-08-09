# Phase 48-01 Summary — Preflight + AnalysisRecord + Provider Seam (Wave 1)

**Plan:** 48-01 · **Wave:** 1 (depends_on: []) · **Requirements:** AF-REQ-11, AF-REQ-14
**Status:** Complete · **Verified:** 2026-08-09

## What shipped

| Task | Artifact | Commit |
|---|---|---|
| 48-01-01 | `backend/app/research/preflight.py` — `PreflightCheck`, `PreflightResult`, pure `preflight()` | `e30b542` |
| 48-01-02 | `research_alpha_analysis_attempts` migration + `record_analysis_attempt` / `get_analysis_attempt` / `list_analysis_attempts` | `a9dc5cf` |
| 48-01-03 | `backend/app/research/agent_provider.py` — `FAILURE_CLASSES`, `ProviderFailure`, `RetryDecision`, `classify_provider_failure`, `retry_policy` (+ `AgentProviderSeam`/`AnalysisAttempt`/`ProviderCallError` scaffolding) | `764d875` |
| 48-01-04 | `AgentProviderSeam` test coverage — retry/backoff/cancel/no-fallback (SC4) | `39900ce` |

## Success-criteria evidence

- **SC1 (AF-REQ-11):** `preflight()` is pure (two calls over the same snapshot return an identical `PreflightResult`), maps every AF-REQ-11 capability to one observable check, returns bounded machine-readable reasons on failure, and makes zero provider calls when it fails (a spy on `generate_ai_text` is never invoked on the failed-preflight path). Folded capabilities expose distinct `sub_reason` discriminators so each folded sub-item is independently failable (plan-check W2 — see Deviations).
- **SC4 (AF-REQ-14):** every §7.1 transport failure class (`malformed_json`, `schema_violation`, `parse_failure`, `refused`, `timeout`, `rate_limited`, `unavailable`) produces a failed `research_alpha_analysis_attempts` row and re-raises `ProviderCallError` with **zero** proposed/validated rows (table-driven no-fallback test). Transient classes retry up to `max_retries=3` with jitter-bounded exponential backoff (1.0→2.0→4.0, cap 30.0); permanent classes record+raise immediately with `retries=0`. `cancel_check()` yields a `cancelled` row. Success records `response_sha256`/`response_byte_size`/`latency_ms` (checksum-by-default); a `retain_raw_artifact_service` stores the full response as a referenced managed artifact.

## Verification output

| Selection | Result |
|---|---|
| `pytest tests/research/test_preflight.py -k 'preflight'` | **17 passed** |
| `pytest tests/test_operational_migrations.py tests/research/test_agent_provider.py -k 'analysis_attempt or attempts_table'` | **7 passed** |
| `pytest tests/research/test_agent_provider.py -k 'taxonomy or classify or retry_policy'` | **27 passed** |
| `pytest tests/research/test_agent_provider.py -k 'seam or no_fallback or retry or cancel or backoff'` | **22 passed** |
| `pytest tests/research/test_run_contract.py tests/test_operational_migrations.py` (regression) | **160 passed** |
| `pytest tests/research/` (full research suite, no regressions from `repository.py` edits) | **524 passed** |

`test_preflight.py` = 17 tests; `test_agent_provider.py` = 46 tests (7 table + 27 taxonomy + 12 seam). The new table is additive; `PRAGMA user_version` advances by exactly one (37 = `len(MIGRATIONS)`).

## Deviations & decisions

1. **W2 folded sub-items (granularity, resolved).** `data_availability_freshness` folds data availability/freshness with source quality, each independently failable via distinct `sub_reason` values (`data_fingerprint`, `partition_fingerprint`, `measured_window`). `required_fields_sample_length` folds required fields with sample length via `sub_reason` values (`required_fields`, `sample_length`). A fixture that degrades only one sub-item flips that consolidated check to `fail` with the matching discriminator.
2. **`preflight()` purity.** The gate is read-only over the frozen snapshot; it recomputes component digests (`digest_bytes` over the manifest groups) and compares to `component_digests`, recomputes grammar/vocabulary/policy fingerprints against the live build, and parses budgets — no DB write, no provider call. The `connection` parameter is accepted as a forward hook for an optional live universe-membership resolution but is **deliberately unused** so the result stays byte-identical across calls (the live lookup is a Phase 48-04 concern that may only strengthen, never weaken, the gate).
3. **`partial` is a Stage-service concept, not a seam-transport failure.** `classify_provider_failure` recognises `partial` only when `raw_response` is present and the exception carries a `partial_failure` marker — i.e. downstream validation of a *received* response. The seam calls `classify_provider_failure(exc, raw_response=None)` on transport errors, so `partial` is never produced by a transport exception; it is set by the Stage 1/2 services (48-02/48-03) after parsing. The taxonomy test covers `partial` directly; the seam no-fallback table covers the seven transport classes.
4. **`classify_provider_failure` ordering honours the `ValueError` hierarchy.** `JSONDecodeError` and `FactorDslError` are `ValueError` subclasses, so they are matched before the generic schema-marker branch (which detects messages like "unsupported field"/"missing field"/"schema" or an explicit `provider_schema_error` / `provider_failure_class` attribute). Unknown transport errors default to `unavailable` (transient) — retried boundedly, then fail terminally; never a fallback.
5. **Repository class naming.** The plan references `AlphaRunRepository`; the concrete class is `ResearchRepository` (the single repository class). The three methods were added there. `failure_class` enum enforcement is the DB `CHECK` constraint (single source of truth shared with `FAILURE_CLASSES`); the repo does not import `agent_provider` (no cross-module coupling).
6. **Test path.** The plan's verify path `tests/operational/test_operational_migrations.py` is `tests/test_operational_migrations.py` in the tree; used the correct path.

## Handoff to 48-02 / 48-03 / 48-04

- `preflight()` + `PreflightResult` — call before the first provider call; a `passed=False` result means do not reach the seam.
- `AgentProviderSeam.request(...)` + `AnalysisAttempt` — the only provider transport; inject `generate_text`/`record_analysis_attempt`, pass `cancel_check`, optional `retain_raw_artifact_service`.
- `record_analysis_attempt` / `list_analysis_attempts` + the `research_alpha_analysis_attempts` table — one immutable row per attempt; the Stage services set `parsed_output_sha256` and `outcome='proposed'|'validated'|'failed'` after parsing/referential checks.
- `ProviderFailure` / `classify_provider_failure` / `retry_policy` — reuse for any provider-error classification; `partial` is the Stage-service path for a received-but-degraded response.
