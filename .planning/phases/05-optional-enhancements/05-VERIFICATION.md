---
phase: 05-optional-enhancements
verified: 2026-07-16T10:34:11Z
status: gaps_found
score: 1/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
next_action: "Close the confirmed production-path and audit/supply-chain gaps, then re-run Phase 05 verification."
next_command: "/gsd:plan-phase 5 --gaps"
gaps:
  - truth: "A user can create and evaluate a Shadow Account-derived strategy from actual local trading logs."
    status: failed
    reason: "The production browser request cannot satisfy the strict backend distillation schema, the production Shadow factory deliberately supplies no distiller and an evaluation service that always fails, and multiple immutable/idempotency boundaries alias or lose attributable work."
    artifacts:
      - path: "frontend/src/lib/phase5Api.ts"
        issue: "ShadowDistillInput sends min_samples_leaf, min_support, min_precision, and training_window instead of required min_leaf_support; backend forbids the extra fields."
      - path: "frontend/src/pages/backtest/ShadowAccount.tsx"
        issue: "The production mutation sends that incompatible payload, and mapping/timezone edits do not invalidate the already displayed preview before confirmation."
      - path: "backend/app/optional_modules.py"
        issue: "The production Shadow bundle sets distiller=None and _UnavailableShadowEvaluation, so advertised availability is not usable end to end."
      - path: "backend/app/shadow/repository.py"
        issue: "Candidate replay identity omits material request content; interrupted reservations are not queryable; retention replay ignores reviewer/rationale divergence; duplicate-content lookup is cross-principal."
      - path: "backend/app/shadow/evaluation.py"
        issue: "IS is independently completed before OOS freezing/execution; failure of the later split leaves an orphaned IS fact and retry does not resume the pair atomically."
    missing:
      - "Align the typed distillation request exactly with the backend contract."
      - "Wire a real production distiller, governed feature freezer, bounded evaluator, and complete availability probe."
      - "Make candidate, evaluation-pair, and retention idempotency content-complete and conflict-safe."
      - "Scope duplicate lineage to the principal and bind confirmation to the previewed mapping/content identity."
  - truth: "A user can view and operate an investment-thesis lifecycle with valuation anchors, invalidation conditions, and periodic governed evidence checks."
    status: failed
    reason: "Normal production governed evidence resolution receives forbidden repository metadata and degrades to an error check; actionable pending data includes stale old-version conclusions, and production evidence readers are empty placeholders."
    artifacts:
      - path: "backend/app/theses/repository.py"
        issue: "get_condition/get_pending add thesis_id to the condition mapping; list_pending returns all thesis versions without actionable current/unreviewed filtering."
      - path: "backend/app/theses/evidence.py"
        issue: "_validated_inputs strips id/version/instrument metadata but not thesis_id before ThesisCondition(extra=forbid) validation; due dates are normalized to UTC rather than the condition timezone."
      - path: "backend/app/theses/service.py"
        issue: "The complete augmented condition is passed to the resolver and pending_for_instrument projects every thesis-level pending record."
      - path: "backend/app/optional_modules.py"
        issue: "Production Thesis is reported available while market, financial, and analysis readers all return None."
    missing:
      - "Construct an explicit allowlisted ThesisCondition payload at the resolver boundary."
      - "Use the declared condition timezone for evidence calendar dates."
      - "Separate current actionable pending conclusions from immutable all-version history."
      - "Wire real governed readers and make availability depend on complete service/scanner readiness."
  - truth: "A researcher can request and inspect a Kronos time-series forecast with P10/P50/P90, sampled paths, and exact checkpoint provenance."
    status: failed
    reason: "The production factory does not wire the approved catalog/input/runner, sampled-path paging is row-based and incompatible with the frontend path contract, and the immutable input/record identities can accept materially different or defaulted provenance."
    artifacts:
      - path: "backend/app/optional_modules.py"
        issue: "Forecast uses a repository-only request service, an actuals adapter that always returns None, and row-based Parquet paging; the complete approved catalog/freezer/runner is not the production service."
      - path: "backend/app/forecast/input.py"
        issue: "input_fingerprint hashes metadata/session IDs but not the selected OHLCV/amount values or promoted artifact checksum; partially-null amount is admitted as a feature."
      - path: "backend/app/forecast/repository.py"
        issue: "Commit defaults missing revisions/digests and sampling fields, does not bind descriptor horizon to the job, and only performs lexical output-path checks."
      - path: "frontend/src/components/analysis/ForecastPanel.tsx"
        issue: "The UI expects path_index and path-count paging, but production artifacts expose sample_index rows; retry keys/config use fresh or stale render state."
      - path: "backend/app/forecast/calendar.py"
        issue: "Future sessions are selected by lexicographic ID without resolving the as-of row/sequence in the selected calendar revision."
    missing:
      - "Wire the complete approved catalog, governed input freezer, bounded runner, actuals, and calibration service in production."
      - "Bind input identity to canonical frame bytes/artifact checksum."
      - "Fail closed on every immutable provenance field and shape relation at commit."
      - "Page distinct paths and return complete path/session rows with a 32-path total."
      - "Resolve calendar horizons from an exact governed as-of sequence."
  - truth: "Shadow, Thesis, and Forecast are independently deployable and fail locally without breaking the completed v1 loop."
    status: failed
    reason: "The real capability factories advertise incomplete services as available, Forecast can remain unavailable regardless of approved assets, and the supported unconfigured-local host path exposes wildcard-CORS API access without assigning the principal required by Phase 05 routes."
    artifacts:
      - path: "backend/app/optional_modules.py"
        issue: "Probe status is dependency-level rather than complete service readiness; production Shadow/Thesis/Forecast collaborators are placeholders or incomplete."
      - path: "backend/app/main.py"
        issue: "Wildcard CORS is combined with an unauthenticated local-network branch; that branch does not set reviewer_principal, so Phase 05 principal-scoped routes cannot operate even when status says available."
    missing:
      - "Probe complete per-module operational readiness and only advertise usable services."
      - "Require authenticated initialization or a tightly trusted loopback Origin/Host policy and a stable server-owned principal."
      - "Keep absence/failure typed and local after complete factory/scanner wiring."
  - truth: "Phase 05 records and artifacts are immutable, attributable, append-safe, and auditable across failure, retry, restart, and correction."
    status: failed
    reason: "Although fact-table mutation triggers exist, the forward migration is not atomic, several replay keys silently substitute materially different facts, and recovery/pagination paths can lose discoverability or exhaust workers."
    artifacts:
      - path: "backend/app/operational/migrations.py"
        issue: "executescript runs without an explicit migration transaction; a mid-script failure can leave partial schema with user_version unchanged."
      - path: "backend/app/shadow/repository.py"
        issue: "Candidate/retention replay keys omit identity-defining content, interrupted evaluation attempts are not discoverable through get/list, and large evidence/history queries materialize unbounded rows."
      - path: "backend/app/theses/service.py"
        issue: "Version/check/history resources are materialized before API pagination, including per-condition query expansion."
      - path: "backend/app/forecast/calibration.py"
        issue: "Oldest-first bounded scanning repeatedly consumes canonical/not-mature entries and can starve newer forecasts; missing actual is persisted terminally and later repair is blocked."
    missing:
      - "Make each migration plus user_version update atomic."
      - "Use canonical payload digests and conflict-on-divergence for immutable replay."
      - "Persist/query interrupted attempts and paired split operation identity."
      - "Move ownership, deterministic pagination, and bounded scans into repositories with durable cursors."
  - truth: "Kronos execution is pinned, byte-bound, local-only, and reproducibly provisioned."
    status: failed
    reason: "Runtime source/config verification is not bound to all executed bytes, the worker import is not proven to come from the verified directory, and checkpoint provisioning has no inter-process serialization or safe shared-asset rollback."
    artifacts:
      - path: "backend/app/forecast/catalog.py"
        issue: "Source verification trusts UPSTREAM.json's self-reported revision; model/tokenizer config.json bytes are not digest-bound."
      - path: "backend/app/forecast/kronos_adapter.py"
        issue: "The worker imports app.vendor.kronos rather than proving import from the catalog-verified source_dir."
      - path: "backend/scripts/provision_kronos.py"
        issue: "Catalog read-modify-write and promotions have no inter-process lock/CAS; rollback can delete a shared promoted tokenizer directory."
      - path: "backend/app/forecast/runner.py"
        issue: "Child stdout and manifest cross memory/IPC before the advertised output cap; process-group cleanup races setsid and has no terminate/kill fallback."
    missing:
      - "Approve and verify hashes for every executed vendored/config byte before spawn and again in the child."
      - "Bind the loaded module directory to the verified catalog source directory."
      - "Serialize or CAS provision/catalog publication and never delete shared final assets during rollback."
      - "Enforce output bounds before allocation/IPC and add a child-ready cleanup handshake with fallback termination."
---

# Phase 05: Optional Enhancements Verification Report

**Phase Goal:** The approved optional Shadow Account, investment-thesis lifecycle, and Kronos probabilistic forecasting capabilities are independently deployable, immutable/auditable, local-only where required, and cannot break or gain authority over the completed v1 loop.

**Verified:** 2026-07-16T10:34:11Z
**Status:** `gaps_found`
**Re-verification:** No — initial Phase 05 verification; no prior `05-VERIFICATION.md` existed.
**Next action:** Close the structured gaps, then re-run verification. Suggested command: `/gsd:plan-phase 5 --gaps`.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A user can create and evaluate a Shadow Account-derived strategy from actual local trading logs. | ✗ FAILED | Backend domain artifacts are substantive, but the production factory supplies `distiller=None` and `_UnavailableShadowEvaluation` (`optional_modules.py:307-323`). The frontend sends a schema-incompatible distillation body (`phase5Api.ts:215-225`; `ShadowAccount.tsx:332-343`) to the strict backend body (`shadow/api.py:32-40`). Candidate/evaluation/retention replay defects are visible in `shadow/repository.py:407-417,557-578,636-660,704-729`. |
| 2 | A user can view an investment thesis with valuation anchors, invalidation conditions, and periodic evidence checks. | ✗ FAILED | Immutable schemas/repository/UI exist, but the real resolver path receives forbidden `thesis_id`: repository adds it (`theses/repository.py:214-232,585-590`), service forwards the full mapping (`theses/service.py:88-100,121-123`), and resolver does not strip it before `extra="forbid"` validation (`theses/evidence.py:191-203`). Production readers are all `None` lambdas (`optional_modules.py:333-347`). |
| 3 | A researcher can request and inspect a forecast with quantiles, sampled paths, and checkpoint provenance. | ✗ FAILED | Numerical adapter tests pass, but the production host does not wire the catalog/freezer/runner (`optional_modules.py:357-380`), path paging slices raw rows (`optional_modules.py:260-279`) while the UI groups `path_index` (`ForecastPanel.tsx:160-177`), and input/record identities omit or default material evidence (`forecast/input.py:168-197`; `forecast/repository.py:453-481`). |
| 4 | The three capabilities are independently deployable and unavailable/failing peers cannot break v1. | ✗ FAILED | The eight-combination acceptance is valuable regression evidence, but it uses deployment probe overrides while real factories expose incomplete services. The supported unconfigured-local branch combines wildcard CORS (`main.py:633-642`) with unauthenticated local-network access and no `reviewer_principal` (`main.py:669-686`), so Phase 05 can be advertised available while principal-scoped routes fail. |
| 5 | Phase 05 evidence is immutable, append-safe, attributable, and auditable across retries/restarts. | ✗ FAILED | Fact triggers exist (`migrations.py:1189-1207`), but migration application is not atomic (`migrations.py:1219-1222`), Shadow replay identities can silently substitute facts, and Forecast maturity scanning can starve later records (`calibration.py:129-144`). |
| 6 | Kronos source/checkpoints are pinned, byte-bound, local-only, and reproducibly provisioned. | ✗ FAILED | Network-free intent and immutable revision checks exist, but source verification trusts only manifest revision and hashes only safetensors (`catalog.py:303-331`); config and executed vendored bytes are not all bound, the worker import directory is not tied to `source_dir`, and provisioning read-modify-write/rollback is race-prone (`provision_kronos.py:428-516`). |
| 7 | Optional research outputs cannot activate or invoke completed-v1 strategy, monitor, plan, position, ledger, broker, provider, or market actions. | ✓ VERIFIED | Source boundaries expose explicit empty/no-action collaborators, and four verifier-run named spot checks passed: Shadow no-action, Thesis confirmation, path-axis quantiles, and real-host success/failure/terminal no-action. The host no-action test passed with three pre-existing Polars warnings. |

**Score:** **1/7** truths verified. `behavior_unverified: 0` — remaining truths are observably failed, not merely uncertain.

## Required Artifacts

`gsd-tools query verify.artifacts` returned `valid` for Plans 05-06 and 05-11 through 05-16. Existence and substantive implementation are not the blocker; production wiring and behavioral integrity are.

| Artifact group | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/app/shadow/*` | Immutable local import, explainable candidate, IS/OOS, safe retention/API | ⚠️ PARTIAL / HOLLOW IN PRODUCTION | Substantive domain code exists. Production host omits a real distiller/evaluator; replay, pair atomicity, attribution, and scope defects remain. |
| `backend/app/theses/*` | Immutable versions, governed checks, pending-only human lifecycle | ⚠️ PARTIAL / HOLLOW IN PRODUCTION | Version/condition/check storage is substantive. Production resolver receives forbidden metadata and production evidence readers are empty. |
| `backend/app/forecast/*` | Approved catalog/input, bounded runner, immutable record/path/calibration/API | ⚠️ PARTIAL / HOLLOW IN PRODUCTION | Numerical and repository modules exist, but production factory does not compose them; input/provenance/path/calibration integrity gaps remain. |
| `backend/app/optional_modules.py`, `backend/app/main.py` | Independent complete module factories in one safe host | ✗ FAILED | Factories advertise incomplete services; local unauthenticated principal/CORS boundary prevents safe usable Phase 05 routes. |
| `backend/app/operational/migrations.py`, `backend/app/optional_artifacts.py` | Atomic append-only schema and immutable managed artifacts | ⚠️ PARTIAL | Triggers and checksum store are substantive; migration is non-atomic and Parquet-library exceptions can bypass temporary cleanup/error translation. |
| `frontend/src/pages/backtest/ShadowAccount.tsx` | Usable Shadow workflow in Backtest | ✗ FAILED | Mounted and substantial, but sends an incompatible distillation body and allows confirmation after mapping changes without a matching fresh preview. |
| `frontend/src/components/analysis/ThesisPanel.tsx`, `ForecastPanel.tsx`, `AnalysisWorkspace.tsx` | Stock-only thesis/forecast review with object-local data | ⚠️ PARTIAL | UI is substantive and browser scenarios pass against fixtures, but `keepPreviousData` plus retained object IDs can render/mutate the previous subject after stock switches; path DTO semantics diverge from production. |
| Phase 05 tests and E2E spec | Behavioral acceptance | ✓ SUBSTANTIVE, COVERAGE GAPS | Exactly 13 browser scenarios and focused backend contracts exist. They do not exercise the contradictory production factory composition or several review-confirmed edge identities. |

## Key Link Verification

`gsd-tools query verify.key-links` returned `valid` for Plans 05-11 through 05-16, but manual Level-3/4 tracing found broken or hollow runtime links.

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `ShadowAccount` | `shadow/api.py::DistillRequest` | typed `phase5Api.shadowDistill` | ✗ NOT WIRED CONTRACTUALLY | Client field names/shape cannot validate against the server's extra-forbid request. |
| `OptionalModuleHost` | Shadow distillation/evaluation | `_ConcreteFactory._create_shadow` | ✗ HOLLOW | Factory supplies no distiller and a deliberately unavailable evaluator. |
| `ThesisService` | `GovernedEvidenceResolver` | `_resolve(condition=dict(condition))` | ✗ BROKEN | Repository metadata reaches strict condition validation and produces error checks. |
| `OptionalModuleHost` | governed Thesis sources | `_create_thesis` | ✗ HOLLOW | All governed readers return `None`. |
| `OptionalModuleHost` | Forecast catalog/freezer/runner | `_create_forecast` | ✗ NOT WIRED | Production creates a repository request service and inert actuals scanner rather than the approved full pipeline. |
| Forecast path API | `ForecastPanel` | Parquet page DTO | ✗ BROKEN | Server pages raw rows/sample indexes; client expects complete distinct path indexes. |
| Forecast request | immutable record | freezer → runner → repository commit | ⚠️ PARTIAL | Components exist, but production composition is absent and the fingerprint/commit validation accepts hollow provenance. |
| Optional mutations | completed-v1 action domains | explicit no-action seams | ✓ WIRED NEGATIVELY | Named unit/host checks confirm no live-action collaborator call. |

## Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Produces real authoritative data | Status |
| --- | --- | --- | --- | --- |
| Shadow panel | batches/evidence/candidates/evaluations | typed API → production Shadow factory | No, not for distillation/evaluation | ✗ HOLLOW |
| Thesis panel | versions/checks/pending | typed API → ThesisService → governed resolver | Versions yes; normal governed checks degrade to error and readers are empty | ✗ HOLLOW |
| Forecast panel | jobs/records/paths/calibration | typed API → production Forecast bundle | Repository fixtures/rows exist; approved model pipeline and actuals are not production-wired | ✗ HOLLOW |
| v1 action domains | strategy/monitor/plan/position/broker mutations | optional services | No calls are available or observed | ✓ ISOLATED |

## Behavioral Spot-Checks

The assignment prohibited project-wide commands. Verification ran only four named, focused checks.

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Shadow retention invokes no completed-v1 action | `uv run pytest tests/shadow/test_evaluation_retention.py::test_retention_invokes_zero_strategy_monitor_plan_position_ledger_broker_or_market_actions -q` | `1 passed` | ✓ PASS |
| Thesis confirmation revalidates evidence and appends one official event | `uv run pytest tests/theses/test_lifecycle.py::test_confirmation_revalidates_evidence_and_appends_one_official_event -q` | `1 passed` | ✓ PASS (fake resolver path; does not cover production metadata defect) |
| Forecast quantiles derive over path axis zero | `uv run pytest tests/forecast/test_kronos_adapter.py::test_adapter_quantiles_are_computed_over_path_axis_zero -q` | `1 passed` | ✓ PASS |
| Real-host optional success/failure/terminal paths invoke no live actions | `uv run pytest tests/test_phase5_optional_host.py::test_optional_success_failure_and_terminal_paths_call_no_live_actions -q` | `1 passed`, 3 pre-existing Polars warnings | ✓ PASS |

## Final Acceptance Evidence Accounted For

The supplied final evidence and `05-17-SUMMARY.md` were considered, but completion claims were not treated as source proof.

| Evidence | Recorded result | Verification interpretation |
| --- | --- | --- |
| Phase 05 focused backend | `177 passed, 1 approved environment-unavailable local-model skip` | Strong evidence for the encoded contracts and no-action regression. It does not cover the source-confirmed production factory, request-schema, metadata, replay-identity, or supply-chain defects. |
| Phase 05 browser | Exactly `13/13` scenarios | Strong fixture-backed UI evidence. Production Shadow request and Forecast path contracts still contradict source; previous-subject retention is not made safe by fixture success. |
| TypeScript and production build | `tsc` and production build pass | Confirms compilation/bundling, not API semantic compatibility or production data flow. |
| Phase 02/03/04 regression gates after append-safe/scoped test fixes | Passed | Positive evidence that Phase 05 changes did not regress the tested earlier loops. The confirmed Phase 05 availability/auth/migration issues still prevent the stronger goal. |
| Optional pinned local Kronos model | One approved local-model skip | Correctly reported as environment-unavailable, not accepted. The skip itself is not a gap; byte-binding/provisioning/runtime composition defects are. |

## Requirements Coverage

| Requirement | Source plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| **SHDW-01** | 05-01/02/05/06/07/08/11/14/15/17 | Derive and evaluate strategy from immutable actual trading logs | ✗ BLOCKED | Domain tests exist, but production factory and frontend/backend request link are unusable; audit/idempotency/scoping gaps remain. |
| **THES-01** | 05-03/05/06/09/12/14/16/17 | Track versioned thesis, anchors, conditions, periodic checks, and human review | ✗ BLOCKED | Immutable versions exist, but production governed checks systematically error and readers are placeholders. |
| **FORE-01** | 05-01/04/05/06/07/10/13/14/15/16/17 | Request Kronos quantiles, sampled paths, and model checkpoints | ✗ BLOCKED | Adapter and runner tests exist, but production composition/path flow/provenance/supply-chain integrity are incomplete. |

`REQUIREMENTS.md` maps exactly SHDW-01, THES-01, and FORE-01 to Phase 05. No orphaned Phase 05 requirement exists, and there is no later milestone phase to which these goal gaps can be deferred.

## Anti-Patterns and Review Findings

The targeted debt-marker scan found no unreferenced `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, or placeholder delivery marker in the Phase 05 source paths. The blockers are implemented behavior, not comments.

| Area | Pattern | Severity | Impact |
| --- | --- | --- | --- |
| Production capability factory | Advertises incomplete/hollow services | 🛑 BLOCKER | All three roadmap user flows can be unavailable or unusable despite `available`. |
| API/client contracts | Strict server request and typed client diverge | 🛑 BLOCKER | Shadow distillation returns 422 for the production UI request. |
| Immutable identity | Replay keys omit material content/attribution | 🛑 BLOCKER | Audited facts can silently represent a different request/reviewer. |
| Migration/recovery | Partial schema and undiscoverable/starved work | 🛑 BLOCKER | Shared operational DB can brick or omit truthful retry/recovery behavior. |
| Forecast supply chain | Executed/config bytes not fully digest-bound | 🛑 BLOCKER | A local revision label can pass while modified code/config executes. |
| Authorization/local host | Wildcard CORS plus unauthenticated local branch | 🛑 BLOCKER | Local browser origins can read unconfigured APIs; Phase 05 lacks the required principal. |
| Frontend object state | Previous-subject data and IDs survive subject changes | 🛑 BLOCKER | Old-instrument data can appear under and mutate from a new stock context. |
| Targeted source scan | No debt markers found | ℹ️ INFO | No marker-based blocker; the source-confirmed review findings determine status. |

## Probe Execution

No Phase 05 shell probe was declared. The Phase 05 contract is expressed through pytest and Playwright artifacts. No project-wide command or model provisioning/download was run.

## Human Verification Required

None for this verdict. The blocking gaps are directly observable in current source. The optional deployment-specific Kronos CPU/resource check remains correctly unavailable until approved local assets are provisioned, but human execution of that check cannot resolve the source-confirmed production and supply-chain gaps above.

## Gaps Summary

Phase 05 is **not goal-complete** despite substantial implementation and strong focused acceptance results. The codebase contains all major domain/UI artifacts and preserves a verified no-live-action boundary, but the actual production composition is hollow for all three capabilities, key frontend/backend contracts diverge, several immutable identities are incomplete, the shared migration is non-atomic, and Kronos execution/provisioning is not fully byte-bound or concurrency-safe.

The unresolved `05-REVIEW.md` blockers are confirmed by current source rather than accepted from review prose. Because each roadmap success criterion fails at the real production wiring/data-flow level, the correct canonical status is `gaps_found`, not `human_needed` or `passed`.

---

_Verified: 2026-07-16T10:34:11Z_
_Verifier: OMP (gsd-verifier)_
