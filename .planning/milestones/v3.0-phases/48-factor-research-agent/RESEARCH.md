# Phase 48 Research — FactorResearchAgent Two-Stage Workflow

**Status:** Draft · **Phase goal:** A FactorResearchAgent safely orchestrates the proven factory + evidence path (deterministic preflight, strict bounded proposals/reviews, durable recoverable failure traces) **without gaining scientific or operational authority**.
**Requirements:** AF-REQ-11 (preflight), AF-REQ-12 (Stage 1), AF-REQ-13 (Stage 2), AF-REQ-14 (audit), AF-REQ-21 (recoverable + offline fixture), AF-REQ-26 (offline fixture trace).
**Pattern source:** PA_Agent (docs/v3-roadmap.md §PA_Agent:66-91) — `PreflightDataGate` (pure-function fail-closed gate before LLM), two-stage diagnosis→decision, `AnalysisRecord` (immutable process evidence), experience library. Patterns only — no AGPL source/prompts copied (REQUIREMENTS.md:19, 76).

---

## 0. Findings at a glance

| Question | Verdict | Strongest evidence |
|---|---|---|
| 1. LLM infra reuse | **Reuse `ai_provider` + generalize `hypotheses.py`** — the existing gateway is a near-complete Stage 1 seed | `hypotheses.py:128-187` (gateway/offline-fixture), `ai_provider.py:100-200` |
| 2. Preflight | **Pure `preflight()` over the frozen `ResearchInputSnapshot`** — every check maps to a live capability; zero provider calls on failure | `run_contract.py:252-292`, `alpha_factory.py:43-101`, `admission.py:78-120` |
| 3. Stage 1 contract | **Generalize `HypothesisDraft` to a list-of-expressions strict schema**; server `parse_factor` confirms; transient = never written to catalog | `hypotheses.py:104-246`, `factor_dsl.py:500-514` |
| 4. Stage 2 contract | **Read-only projection of frozen run + server evidence**; schema forbids mutable fields; referential-integrity check on every cited ID | `alpha_scoring.py:129-418`, `run_contract.py:252-292` |
| 5. AnalysisRecord | **New append-only `research_alpha_analysis_attempts` table** modeled on the event ledger; **no fallback draft ever synthesized** | `repository.py:2250-2358`, `hypotheses.py:159-160` |
| 6. Recovery | **Reuse Phase 45 checkpoint/event cursor**; Agent stage ∈ checkpoint; offline fixture = explicit provider, never implicit | `run_service.py:208-360,821-872`, `repository.py:2630-2745` |
| 7. Failure taxonomy | **Transient (retry w/ backoff) vs permanent (no retry, record+raise)**; classification from status + exception class | `ai_provider.py:216-261` |
| 8. Experience library | **Deferred-seed offline library** keyed by factor family/objective; no provider calls to populate; MVP = static fixture | `hypotheses.py` (no store exists), `v3-roadmap.md:86` |
| 9. Plan split | **4 plans**: 48-01 preflight+seam+taxonomy · 48-02 Stage 1 · 48-03 Stage 2 · 48-04 audit+recovery+fixture+library | — |

---

## 1. Existing LLM infrastructure (Q1)

### 1.1 Provider client — `backend/app/services/ai_provider.py`

The platform already has a complete, single-provider LLM seam with two execution modes and structured error handling:

- **`generate_ai_text(messages, *, temperature, max_tokens, timeout)`** → `str` — complete non-streaming response (ai_provider.py:100-115). Dispatches on `is_codex_cli_provider()`; default path `_run_openai_once` (ai_provider.py:143-161).
- **`stream_ai_text(...)`** → `AsyncIterator[str]` — delta stream (ai_provider.py:118-140). Used by `ai_generator.stream`.
- **Everything is streaming under the hood** — `_run_openai_once` just concatenates `_stream_openai` chunks (ai_provider.py:150-161). Rationale (ai_provider.py:150-152): the vfing gateway has a 60s hard upstream timeout on non-streaming requests; reasoning models need 60–110s, so streaming avoids 504s.
- **Client config** (`_openai_client`, ai_provider.py:203-213): `AsyncOpenAI(api_key, base_url, timeout, max_retries=0, ...)`. **`max_retries=0`** — the SDK's own retry is deliberately OFF; retry policy is the application's responsibility (this is the seam Phase 48 owns).
- **Provider/model resolution**: `current_ai_provider()` (ai_provider.py:28-29), `current_ai_model()` (ai_provider.py:32-35), `ai_configured(provider)` (ai_provider.py:93-97) — reads `secrets_store` + `settings`. Two providers: `OPENAI_COMPAT_PROVIDER` and `CODEX_CLI_PROVIDER` (ai_provider.py:17-18).
- **Error classification** (`_is_openai_transport_error`, ai_provider.py:216-230; `_format_openai_error`, ai_provider.py:233-261): maps HTTP status → Chinese message, distinguishes `Timeout`/`Connection` by class name, handles 400/401/403/404/408/429/500/502/503/504. HTML/gateway error bodies are compacted (`_compact_error_text`, ai_provider.py:297-301). **This is the raw material for the Phase 48 failure taxonomy (§7).**

**Reuse verdict for Phase 48:** Stage 1/2 calls SHOULD reuse `generate_ai_text`/`stream_ai_text` as the transport, but wrap them in an Agent-owned seam that adds: (a) bounded retry with backoff (the SDK retry is off), (b) raw-response capture + checksum for the AnalysisRecord, (c) cooperative-cancellation token check between retries, (d) structured `ProviderFailure` classification. **No new provider dependency** (locked boundary, ROADMAP.md:12).

### 1.2 Existing Stage-1-shaped gateway — `backend/app/research/hypotheses.py`

`FactorHypothesisService` + `ConfiguredFactorHypothesisGateway` are **already a minimal, correct Stage 1 implementation** — they encode every AF-REQ-12 invariant Phase 48 must generalize:

- **Strict schema decode** (`_decode_provider_draft`, hypotheses.py:80-101): `json.loads` → reject non-object → compute `unknown = set(payload) - allowed` and `missing = required - set(payload)` → reject unknown fields and missing required fields explicitly. This is the `extra="forbid"` + required-set pattern Phase 48 must keep and extend (list of expressions, scope/uncertainty/evidence_refs).
- **Provider failure = availability boundary, never a fallback draft** (hypotheses.py:157-160): `except Exception → raise HypothesisUnavailableError`. **This is exactly AF-REQ-14's "never create a fabricated fallback draft"** — already implemented once; Phase 48 must preserve it for every Stage 1/2 path.
- **Server parser confirmation** (hypotheses.py:202-225): provider text → `_decode_provider_draft` → `parse_factor(expression)` → store `parsed.canonical_expression` as `normalized_expression`. The provider's raw text is never trusted; only the server-canonicalized form is kept. This is the "server parser/canonicalizer confirms expressions" contract (SC2).
- **Provenance recording** (hypotheses.py:216-222): `{provider, model, model_version, prompt_template_version, generated_at}`. This is the seed of the AnalysisRecord provenance (SC4).
- **Offline fixture gateway** (`OfflineFakeHypothesisGateway`, hypotheses.py:163-187): deterministic test-only text source, **never performs provider I/O**, `provider="offline_fake"`, `model="offline-fixture"`. **This is the AF-REQ-26 offline-fixture pattern, already proven** — Phase 48 generalizes it into an explicit, declared, non-production provider.
- **Issued-draft re-validation** (`reviewed_draft`, hypotheses.py:227-246): a route may only create a revision if expression/explanation/provenance byte-match the issued draft. This is the "transient until explicit review" boundary (SC2, AF-REQ-15 handoff to Phase 49).

### 1.3 AST-whitelist precedent — `backend/app/strategy/ai_generator.py`

`_validate_safety` (ai_generator.py:123-143) is the established **allowlist-not-blocklist** security pattern: `_ALLOWED_IMPORT_MODULES = frozenset({"polars", "__future__"})` (ai_generator.py:121) + dangerous-builtin call interception. Phase 48 does NOT generate code (no `ai_generator` reuse), but the **allowlist discipline** carries over: Stage 1 output is bounded by `factor_dsl.ALLOWED_FIELDS` + the restricted function/operator set, not by blocking known-bad tokens.

---

## 2. Preflight design — AF-REQ-11 (Q2)

### 2.1 Shape

A **pure function** over the already-frozen `ResearchInputSnapshot` (run_contract.py:252-292) returning a `PreflightResult`. Pure = no provider call, no side effect, deterministic from the snapshot. Modeled on PA_Agent `PreflightDataGate` (v3-roadmap.md:68, 83: "LLM 前纯函数 fail-closed; 可计算事实由程序主导, 模型只能解释").

```python
@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str            # "data_freshness", "measured_calendar", ...
    status: str          # "pass" | "fail"
    reason: Mapping[str, Any] | None   # machine-readable; None on pass

@dataclass(frozen=True, slots=True)
class PreflightResult:
    passed: bool
    checks: tuple[PreflightCheck, ...]
    # failed result => caller MUST NOT call the provider
```

A failed preflight transitions the run to `preflight_failed` (run_contract.py:47-49) with `terminal_reason` (run_service.py:64-80) and makes **zero provider calls** (SC1).

### 2.2 Check → capability mapping (file:line evidence)

| AF-REQ-11 check | Source of truth | Evidence |
|---|---|---|
| Data availability/freshness + source quality | Frozen `data_manifest.fingerprint` + live partition scan; `measured_window.{start,end}` | run_contract.py:61, 221-222, 231; manifest validation run_contract.py:200-251 |
| Measured calendar | `fold_geometry.{train_size,gap_size,test_size,n_folds}` + `measured_window` | run_contract.py:223-226; required group run_contract.py:61 |
| PIT universe scope | `universe.membership_fingerprint` (frozen) vs live `resolve_universe_daily` | run_contract.py:280; universe.py:67-137 (`resolve_universe_daily` per-date `[symbol,date]` frame) |
| Required fields / sample length | `factor_dsl.ALLOWED_FIELDS` ∩ expression field set; sample length from measured window | factor_dsl.py:27-37; extract_features fields factor_dsl.py:446-465 |
| DSL/grammar compatibility | `verify_vocabulary_fingerprint(frozen)` + `grammar_fingerprint` recompute | alpha_factory.py:43-62 (vocab over DSL_VERSION+fields+functions+arity+partition+max_window), alpha_factory.py:127-138 (`verify_*` raises `VocabularyMismatchError`), alpha_factory.py:65-81 (grammar) |
| Budgets | `BudgetLimits.from_manifest` + `BudgetGuard.exhausted` | alpha_factory.py:976-1015, 1018-1069 |
| Provider availability | `ai_provider.ai_configured(provider)` + `current_ai_model()` non-empty | ai_provider.py:93-97, 32-35 |
| Policy mode | `verify_admission_policy_fingerprint(snapshot.policy_fingerprint)` | admission.py:78-120; `ADMISSION_POLICY_FINGERPRINT` admission.py:107; snapshot.policy_fingerprint run_contract.py:287-292 |

### 2.3 Design decisions

- **D-48-01 (preflight is read-only over the snapshot).** Every check consumes either the frozen snapshot's component digests (run_contract.py:332-342) or recomputes a live fingerprint and compares. It never mutates the run. A mismatch (e.g. vocabulary drift) is a `fail`, not a repair.
- **D-48-02 (per-check machine-readable reason).** Each failed check carries a bounded JSON reason (`canonical_bounded_json`, run_contract.py:125-127) using the existing 64 KiB / 4096-char bounds (run_contract.py:25-28). No raw text, no provider echo.
- **D-48-03 (preflight runs before `start_or_resume`).** Mirrors the existing preflight gate in `freeze_input_snapshot`/`validate_manifest` (run_contract.py:200-251, 316) — the snapshot is already validated at freeze; Phase 48 adds a *liveness* layer (is the data still here *now*, is the provider up *now*) right before the first provider call.
- **D-48-04 (Stage 2 has its own preflight).** Stage 2 additionally checks that referenced candidate/evaluation/gate evidence **exists** for the run before the review call (referential pre-check, §4.4).

---

## 3. Stage 1 contract — AF-REQ-12 (Q3)

### 3.1 Bounded input (thesis)

Generalize the single `hypothesis: str` + `options` (hypotheses.py:60-77, 197-199) into an explicit bounded request:

```python
@dataclass(frozen=True, slots=True)
class StageOneRequest:
    thesis: str                      # bounded text (MAX_JSON_STRING_CHARS=4096)
    permitted_grammar: Mapping[str, Any]  # frozen grammar fingerprint + max_depth/max_nodes
    permitted_fields: frozenset[str]      # subset of factor_dsl.ALLOWED_FIELDS
    permitted_functions: frozenset[str]   # subset of DSL functions
    budget_hints: Mapping[str, Any]       # max_expressions, max_explanation_chars
    snapshot_ref: Mapping[str, Any]       # frozen manifest digests (provenance only)
```

### 3.2 Versioned strict output schema

```jsonc
{
  "schema_version": "factor-stage1-v1",
  "hypotheses": [           // bounded: budget_hints.max_expressions (default 3)
    {
      "expression": "rolling_mean(close, 20) / close",   // DSL text, server-confirmed
      "explanation": "...",                                // bounded chars
      "assumptions": ["..."],                              // array of text
      "scope": "...",                                      // bounded text
      "uncertainty": "low|medium|high",
      "evidence_refs": ["..."]                             // free-text citations of thesis/data
    }
  ]
}
```

- **`extra="forbid"`** is enforced by extending `_decode_provider_draft`'s unknown-field rejection (hypotheses.py:87-91) to nested objects. Unknown keys → permanent failure (§7), no truncation repair that silently drops fields.
- **Every `expression` is server-confirmed**: `parse_factor(expr)` (factor_dsl.py:500-509) → store `parsed.canonical_expression`. A hypothesis whose raw text does not re-serialize to the canonical form is recorded with the canonical form but **the raw text is retained in the AnalysisRecord** (provenance, not authority). An expression that fails to parse → the hypothesis is dropped and recorded as a validation error, but **does not abort the whole stage** unless *all* hypotheses fail (then: permanent failure, no fallback draft — hypotheses.py:159-160 pattern).
- **Bounded**: `max_expressions` (default 3), `max_explanation_chars` per hypothesis (default 2000), `max_assumptions` (default 8). These reuse `MAX_JSON_*` bounds (run_contract.py:25-28).
- **Transient**: a Stage 1 result is stored only in the AnalysisRecord / a transient proposal store (in-memory or a `research_alpha_proposals` table marked `exploratory`). It is **never** written to `factor_registry` / catalog. Promotion is Phase 49 (AF-REQ-15) and requires `reviewed_draft` byte-match (hypotheses.py:227-246).

### 3.3 Prompt template versioning

Reuse `HYPOTHESIS_PROMPT_TEMPLATE_VERSION = "factor-hypothesis-v1"` (hypotheses.py:19) discipline → `STAGE_ONE_PROMPT_TEMPLATE_VERSION = "factor-stage1-v1"`, recorded in every AnalysisRecord's provenance (SC4).

---

## 4. Stage 2 contract — AF-REQ-13 (Q4)

### 4.1 Input = frozen run + server evidence ONLY

Stage 2 receives **nothing the model could have authored**:

- The frozen `ResearchInputSnapshot` (run_contract.py:252-292) — read-only.
- Server-produced candidate/evaluation/gate evidence, read from the Phase 47 ledger:
  - Candidate attempts: `repository.list_candidates(run_id)` (repository.py:2513-2564), projections `AlphaCandidateAttempt` (run_contract.py:450-468).
  - Per-fold evidence: `record_candidate_evidence` / `record_selection_fold_evidence` (alpha_scoring.py:129-241), persisted via `record_alpha_fold_evidence` / `list_alpha_fold_evidence` (repository.py:1169-1306).
  - Admission verdicts: `record_candidate_admission` (alpha_scoring.py:287-418), stored via `insert_admission_verdict` (repository.py:712-766).
  - Winner + exactly-once OOS: `select_winner` (alpha_scoring.py:535-617), `evaluate_selection_oos` (alpha_scoring.py:620-734).

### 4.2 Output schema — caveats + bounded recommendation, NO mutable fields

```jsonc
{
  "schema_version": "factor-stage2-v1",
  "caveats": [
    {
      "kind": "missing_assumption|contradictory_metric|gate_failure|narrow_coverage|redundancy",
      "claim": "...",                                   // bounded text
      "evidence_refs": [                                // referential integrity (§4.4)
        {"kind": "candidate", "id": "acand_..."},
        {"kind": "evaluation", "id": "afe_..."},
        {"kind": "gate", "id": "avrd_..."},
        {"kind": "artifact", "id": "aart_..."}
      ]
    }
  ],
  "recommendation": {
    "disposition": "inspect|retain|propose_new_run|no_action",  // bounded enum
    "rationale": "...",                                // bounded text
    "follow_up_run_dims": ["..."] | null               // dimensions for a NEW run, never in-place edit
  }
}
```

**`disposition` is the only "action" and it is advisory.** There is no field for a new expression, a metric value, a threshold, an OOS flag, or an admission override. This is the schema-level enforcement of SC3 ("cannot change expressions, metrics, thresholds, OOS state, or admission status"). The existing no-edit guard (`assert_admission_no_edit`, alpha_scoring.py:479-505) already forbids scoring modules from carrying threshold params — Stage 2's *output* schema is the symmetric constraint on the *response*.

### 4.3 AF-REQ-21 (SC5 wording) coverage

`disposition: "propose_new_run"` with `follow_up_run_dims` is how Stage 2 expresses "follow-up is a bounded new run, never an unbounded autonomous loop" (AF-REQ-21, ROADMAP non-goal: "no autonomous/unbounded loops", ROADMAP.md:128). The Agent cannot spawn it; a human clones the run changing only declared dims (AF-REQ-22, Phase 50).

### 4.4 Referential integrity check

Each `evidence_refs[].id` MUST resolve within the same run:
- candidate → `research_alpha_candidate_attempts.id` WHERE run_id matches (repository.py:1786-1788 pattern).
- evaluation → fold-evidence row bound to run_id (repository.py:1169-1306).
- gate → admission verdict bound to a candidate in the run.
- artifact → `research_alpha_artifacts` bound to run_id (repository.py:2718-2724 pattern).

An unresolvable or cross-run reference is a **permanent validation failure** (§7) — recorded, no fallback review. This is the server-side enforcement of "each challenge links to valid candidate/evaluation/gate/artifact IDs" (SC3).

---

## 5. Audit / AnalysisRecord — AF-REQ-14 (Q5)

### 5.1 Storage: new append-only table

**Recommendation: a new `research_alpha_analysis_attempts` table** (not the event ledger, not artifacts). Rationale:
- The event ledger (`research_alpha_events`, repository.py:2250-2358) records *run lifecycle* events with idempotency keys and contiguous seq — wrong grain (one event per transition, not one per provider attempt).
- Artifacts (`research_alpha_artifacts`) are content-addressed blobs — good for the *bounded raw response* (§5.3) but not for the attempt row.
- The new table mirrors the candidate ledger's append-only, immutable, attempt-ordinal shape (repository.py:2360-2441) and is written through the same token/version fence as checkpoints (repository.py:2679-2745).

Schema (sketch):
```
research_alpha_analysis_attempts(
  id, run_id, attempt_ordinal, stage,            -- stage ∈ {preflight, stage1, stage2}
  template_version, schema_version,
  provider, model, model_version,                 -- provenance
  request_scope_sha256,                           -- bounded request digest (not raw prompt in prod)
  response_sha256, response_byte_size,            -- raw checksum (default retention)
  response_artifact_id NULL,                      -- optional approved full response (debug)
  parsed_output_sha256,                           -- canonical parsed output digest
  validation_errors_json,                         -- bounded list of {field, code, detail}
  failure_class NULL, failure_reason_json NULL,   -- §7 taxonomy
  retries INTEGER, cancelled INTEGER,
  latency_ms INTEGER,
  outcome,                                        -- proposed|validated|failed|cancelled
  created_at
)
```

### 5.2 Recorded per attempt (SC4 mapping)

| SC4 field | Column / source |
|---|---|
| template/schema/provider/model provenance | `template_version, schema_version, provider, model, model_version` (hypotheses.py:216-222 pattern) |
| request scope | `request_scope_sha256` over the bounded `StageOneRequest`/Stage 2 input digest (raw prompt NOT persisted in prod by default) |
| raw-response checksum **or** approved response | `response_sha256` always; `response_artifact_id` only when an explicit debug/approval flag retains the full text (§5.3) |
| parsed output | `parsed_output_sha256` over canonical-JSON parsed payload |
| validation errors | `validation_errors_json` (bounded; reuse `_bounded_json`, repository.py:2286) |
| retries | `retries` counter |
| cancellation | `cancelled` flag + the cooperative token state at cancel time |
| latency | `latency_ms` (monotonic, like `BudgetGuard._monotonic`, alpha_factory.py:1028) |
| partial/terminal failure | `outcome` + `failure_class`/`failure_reason_json` |

### 5.3 Response retention / hash policy (research flag)

**Decision: checksum-by-default, full-retention-by-explicit-approval.**
- **Default (production):** store only `sha256(raw_response)` + `byte_size`. The raw provider text is never persisted unless an operator explicitly enables per-run debug retention. This bounds storage and avoids retaining potentially sensitive/error text indefinitely.
- **Approved retention:** when `response_artifact_id` is set, the full response is stored as a *content-addressed managed artifact* via the existing `append_artifact` (repository.py:2566-2629) + checksum verification (run_service.py:832-847). The artifact is referenced by the attempt row, never inlined (so the 64 KiB JSON bound, run_contract.py:25, is never threatened).
- **Why not always hash-and-discard:** the AnalysisRecord must remain *reproducible evidence* (PA_Agent pattern, v3-roadmap.md:72: "不可删除的过程证据"). The checksum lets an auditor re-derive identity without retaining bytes; the artifact path lets a sanctioned reviewer inspect the full text. Both paths fail closed — a missing artifact referenced by an attempt is a checkpoint-validation error (run_service.py:832-840).

### 5.4 No fabricated fallback — the failure path

The single most important invariant (SC4). Implemented by structurally forbidding any code path that synthesizes a draft when the provider fails:

```
provider call
  ├─ success → decode → validate → (ok: record "proposed/validated") | (bad: record failure_class, NO draft)
  └─ exception → classify (§7) → record failure_class + reason → RAISE (terminal or retry-per-taxonomy)
```

There is **no `except: return default_draft`** anywhere. The existing precedent (hypotheses.py:157-160: `except Exception → raise HypothesisUnavailableError`) is the template; Phase 48 wraps it with structured classification and the AnalysisRecord write, but never adds a synthetic-success branch. A test must assert: every provider-exception class in §7 produces a failed AnalysisRecord row and raises, with zero proposal rows.

---

## 6. Recovery / checkpoint — AF-REQ-21 (Q6)

### 6.1 Reuse the Phase 45 cursor

Phase 45 already delivers exactly-once, fail-closed checkpoint recovery. Phase 48 adds the Agent stage to the cursor; it does **not** invent a new mechanism (locked boundary, ROADMAP.md:71: "no second Agent/validation framework").

- **Cursor identity:** `AlphaRunCheckpoint{committed_event_seq, stage, state_checksum, snapshot_sha256, manifest_sha256, referenced_candidate_ids, frontier_artifact_id}` (run_contract.py:484-530, repository.py:2630-2745). Phase 48 uses `stage ∈ {"preflight", "stage1", "stage2"}`.
- **Resume read:** `get_latest_valid_checkpoint(run_id)` (run_service.py:821-830) → re-validates snapshot/manifest binding, event-sequence contiguity, candidate references, and artifact verification (run_service.py:832-872, repository.py:2682-2724).
- **Re-fence on resume:** `recover_running_attempt` (run_service.py:256-293) issues a fresh attempt token; the old token's digest is invalidated (run_service.py:362-386). A checkpoint written under a stale token is rejected by `append_checkpoint`'s `expected_attempt_token_digest` fence (repository.py:2692-2700).
- **No repeated side effects:** candidate attempts, fold evidence, admission verdicts, and the exactly-once selection OOS (alpha_scoring.py:620-734) are all append-only with UNIQUE constraints / idempotency keys (repository.py:2250-2358, 1078-1135). Resuming Stage 2 reads the already-committed evidence rather than recomputing it. A crash mid-Stage-2 cannot re-evaluate OOS because the OOS binding is exactly-once durable (alpha_scoring.py:620-734).

### 6.2 Stage-to-event/checkpoint transaction boundary (research flag)

**Decision: one checkpoint per stage boundary, written in the same `BEGIN IMMEDIATE` transaction as the stage's terminal event.**
- Stage 1 completion: append `stage1_completed` event + checkpoint{stage:"stage2_pending", referenced_candidate_ids:[proposal-derived candidate ids if any]} atomically. Mirrors the event/checkpoint contiguity check (repository.py:2705-2710).
- Stage 2 completion: append `stage2_completed` + the run's `completed` terminal — Stage 2 is terminal for the Agent; no "stage3".
- A checkpoint whose `committed_event_seq` is not contiguous with the live event ledger is rejected (repository.py:2703-2710). This is the existing fail-closed guarantee; Phase 48 only adds the `stage` discriminator.

### 6.3 Offline fixture mode — AF-REQ-26

Generalize `OfflineFakeHypothesisGateway` (hypotheses.py:163-187) into a first-class, declared provider:

- **Explicit declaration only:** the fixture provider is selected by an explicit, non-default config (e.g. `FIXTURE_MODE=1` + a fixture name), never by a missing-provider fallback. `ai_provider.ai_configured()` returning false → preflight `provider_availability` **fails** for production; it only passes when the fixture is explicitly selected (D-48-04).
- **Known full trace:** the fixture returns canned Stage 1/Stage 2 JSON **and** a canned validation trace, so an operator/test can reproduce the entire `preflight → stage1 → stage2 → AnalysisRecord` chain with no network. The fixture's `provider="offline_fixture"`, `model="offline-fixture-v1"` (hypotheses.py:171-173 pattern) is recorded in every AnalysisRecord, so fixture evidence is **always labeled non-production** (SC5, AF-REQ-26).
- **Never an implicit production fallback:** production paths must not branch to the fixture when a real provider errors (that would violate SC4's no-fallback invariant). The fixture is a *peer* provider selectable only by explicit declaration.

---

## 7. Provider failure / retry taxonomy (research flag, Q7)

### 7.1 Classification

Derived from `ai_provider`'s existing status/exception handling (ai_provider.py:216-261):

| Class | Trigger | Retry? | Terminal? |
|---|---|---|---|
| `malformed_json` | `json.JSONDecodeError` (hypotheses.py:83-84) | **No** (permanent) | Yes |
| `schema_violation` | unknown/missing field, wrong type (hypotheses.py:87-101) | **No** (permanent) | Yes |
| `parse_failure` | `FactorDslError` on server confirmation (hypotheses.py:206-207) | **No** (permanent) | Yes |
| `timeout` | HTTP 408/504, `*Timeout` class (ai_provider.py:240-241, 251, 256) | **Yes** (transient) | only after retries exhausted |
| `rate_limited` | HTTP 429 (ai_provider.py:252) | **Yes** (transient) | only after retries exhausted |
| `unavailable` | HTTP 500/502/503, `*Connection` (ai_provider.py:242-243, 253-255) | **Yes** (transient) | only after retries exhausted |
| `refused` | HTTP 400/401/403/404 (ai_provider.py:247-250) | **No** (permanent) | Yes |
| `partial` | provider returned data but downstream validation failed for some hypotheses | **No** (record partial; salvage valid subset) | No (stage may still complete with subset) |
| `cancelled` | cooperative token observed cancel_requested | **No** | Yes (→ cancelled) |

### 7.2 Retry policy

- **Transient only** (`timeout`, `rate_limited`, `unavailable`): bounded retries, default `max_retries=3`, **exponential backoff** with jitter (base 1.0s, factor 2.0, cap 30s). Each retry is its own AnalysisRecord-attempt row (`attempt_ordinal` increments), all sharing the `request_scope_sha256`.
- **Permanent** (`malformed_json`, `schema_violation`, `parse_failure`, `refused`): zero retries — record + raise immediately. Retrying a malformed JSON response would just burn budget.
- **`partial`**: not retried at the stage level; valid hypotheses are kept, failed ones are recorded as validation errors. If *all* hypotheses in Stage 1 fail validation, the stage escalates to permanent failure.
- **Cancellation cooperation:** before each retry, check the run status; if `cancel_requested` (run_service.py:294-326) was appended, abandon the retry, record `cancelled`, and let the lifecycle reach `cancelled`. This reuses the existing cooperative-cancellation token (run_service.py:362-386) — no new cancellation channel.

### 7.3 Backoff injection point

The retry loop wraps `ai_provider.generate_ai_text` inside the Agent seam (§1.1). The SDK's own retry stays OFF (`max_retries=0`, ai_provider.py:211) so the Agent owns all retry timing/latency recording (SC4 `latency_ms`).

---

## 8. Experience library — AF-REQ-26 (Q8)

### 8.1 Current state

`hypotheses.py` has **no hypothesis/experience store** — drafts live in `FactorHypothesisService._issued` (hypotheses.py:195), an in-memory dict keyed by `draft_id`, used only for `reviewed_draft` re-validation (hypotheses.py:227-246). There is no persistence, no regime classification, no retrieval-by-similarity. PA_Agent's experience library (v3-roadmap.md:86: "按市场形态分类检索历史案例; 成功/失败分库") is **not present**.

### 8.2 Phase 48 scope — minimal, offline-seeded

**Recommendation: defer a full experience library to post-v3.0; ship only the offline-seeded MVP needed for AF-REQ-26's "known full trace".**
- **MVP = static fixture library.** The offline fixture (§6.3) carries a canned experience entry (a known-good Stage 1 proposal + a known Stage 2 review) keyed by `(factor_family, objective)`. This satisfies "tests and operators can run an explicitly declared offline Agent fixture with known proposal and validation trace" (AF-REQ-26) without any provider call to populate it.
- **Keying:** by **factor family** (momentum/mean-reversion/volatility/quality — derivable from `extract_features` field set, factor_dsl.py:446-465) × **objective** (`manifest.objective.name`, run_contract.py:229), NOT by PA_Agent's Price-Action regimes (v3-roadmap.md:237 notes A-share adaptation is needed; out of Phase 48 scope).
- **Usage without provider calls:** the library is a read-only fixture consulted to *augment the prompt context* (like `ai_generator` reads `strategy-guide-compact.md`, ai_generator.py:15). It never becomes a fallback response (would violate SC4). In production, an empty library is valid — the Agent simply runs without experience context.

### 8.3 Non-goal reaffirmation

A retrieval-by-similarity experience library, success/failure partitioning, and regime classification are explicitly **deferred** (ROADMAP future requirements: "multi-agent debate, self-modifying prompts"; v3-roadmap.md:244 risk note). Phase 48 ships the *seam* (a `ExperienceLibrary` protocol with one offline-fixture implementation) so a later phase can add a populated implementation without touching the Stage 1/2 contracts.

---

## 9. Recommended plan split (Q9)

Four plans, dependency-ordered, each independently verifiable:

### 48-01 — Preflight + provider seam + failure taxonomy
- **Target:** `preflight()` pure function over `ResearchInputSnapshot` (§2); Agent provider seam wrapping `ai_provider` with retry/backoff/cancellation (§1.1, §7); `research_alpha_analysis_attempts` table + write path (§5); `ProviderFailure` classification (§7.1).
- **Acceptance:** a failed preflight makes zero provider calls and returns machine-readable reasons; every §7.1 failure class produces a failed AnalysisRecord row + raises (no fallback draft); transient failures retry with backoff and respect cancellation.
- **Why first:** every Stage 1/2 path depends on the seam, the audit table, and the taxonomy. No Stage contract yet.

### 48-02 — Stage 1 contract + schema + server canonicalization
- **Target:** `StageOneRequest`/strict versioned schema (§3); generalize `FactorHypothesisService` → Stage 1 service over the seam from 48-01; server `parse_factor` confirmation per expression; transient proposal store; offline-fixture Stage 1 response.
- **Acceptance:** provider output with unknown/missing fields is rejected (permanent failure); every persisted expression equals its `canonical_expression`; a provider exception never yields a proposal row; transient proposals are absent from `factor_registry`/catalog.
- **Depends on:** 48-01.

### 48-03 — Stage 2 contract + evidence-linked review + referential integrity
- **Target:** `StageTwoRequest` (frozen snapshot + server evidence projection) and read-only output schema (§4); referential-integrity check over candidate/evaluation/gate/artifact IDs; offline-fixture Stage 2 response; stage-boundary checkpoint (§6.2).
- **Acceptance:** output schema has no mutable field (no expression/metric/threshold/OOS/admission); every cited ID resolves within the run; an unresolvable reference is a permanent failure; disposition is advisory only.
- **Depends on:** 48-01, 48-02 (Stage 2 reads Stage 1 proposals + the evidence Phase 47 already produced).

### 48-04 — Recovery + offline fixture trace + experience-library seam
- **Target:** explicit-declaration offline-fixture provider (§6.3) with a known full trace (AF-REQ-26); `ExperienceLibrary` protocol + offline-fixture implementation (§8.2); resume-from-checkpoint wiring for Stage 1/Stage 2 (§6.1); end-to-end fixture-mode run (preflight→stage1→stage2→AnalysisRecord) labeled non-production.
- **Acceptance:** retry/restart resumes from the checkpoint cursor without repeating committed candidate/OOS/promotion side effects; fixture mode is selectable only by explicit declaration and is labeled non-production in every AnalysisRecord; an empty experience library is valid in production.
- **Depends on:** 48-01, 48-02, 48-03.

---

## 10. Risks & open questions

- **R1 (raw-response retention cost).** Checksum-by-default (§5.3) bounds storage but means a post-hoc auditor cannot inspect text without re-running. **Mitigation:** explicit per-run debug-retention flag → managed artifact; accepted trade-off.
- **R2 (partial Stage 1 success semantics).** Keeping the valid subset when some hypotheses fail parse (§7.1 `partial`) is convenient but could let a degraded response look "complete". **Mitigation:** the AnalysisRecord `outcome` and the proposal store must mark partial proposals distinctly (links to AF-REQ-25's "exploratory vs clean" labeling, Phase 50).
- **R3 (fixture-mode detection).** A misconfigured production run must never silently pick the fixture. **Mitigation:** preflight `provider_availability` check (D-48-04) fails production when the fixture is the only configured provider; the fixture requires an explicit, non-default selector.
- **OQ-1:** Should the AnalysisRecord table live in the same SQLite DB as the run ledger (simple, same transaction fence) or a side DB (isolation)? **Lean: same DB** — the checkpoint/event atomicity (repository.py:2679-2745) is the strongest argument; revisit if audit volume proves large.
- **OQ-2:** Does Stage 2 need to cite *admission gate* IDs individually, or is the verdict row (one per candidate) sufficient? The verdict row already lists every gate's observed value/threshold/reason (alpha_scoring.py:287-418). **Lean: verdict-row reference is sufficient**; cite the candidate + verdict, not each gate, to avoid a brittle 1:N citation model.

## 11. Confidence

**High** on reuse (Q1, Q6): Phase 45-47 already deliver the snapshot, event/checkpoint ledger, evidence, admission, and OOS contracts Phase 48 consumes verbatim. **High** on preflight (Q2): every check maps to a live, file-evidenced capability. **Medium-High** on Stage 1/2 schemas (Q3, Q4): the contracts are clear but the exact bounded field set / `partial` semantics need plan-time ratification (R2). **Medium** on the experience library (Q8): deliberately scoped down to a fixture seam; full retrieval deferred. **No new dependency, no new framework, no AGPL source** — all locked boundaries honored.
