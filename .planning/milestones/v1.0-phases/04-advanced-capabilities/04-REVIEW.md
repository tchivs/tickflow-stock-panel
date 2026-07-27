---
phase: 04-advanced-capabilities
reviewed: 2026-07-14T03:32:56Z
depth: deep
files_reviewed: 30
files_reviewed_list:
  - backend/app/advanced/__init__.py
  - backend/app/advanced/api.py
  - backend/app/advanced/authorization.py
  - backend/app/advanced/evolution.py
  - backend/app/advanced/experiments.py
  - backend/app/advanced/governed_runner.py
  - backend/app/advanced/jobs.py
  - backend/app/advanced/policy.py
  - backend/app/advanced/projections.py
  - backend/app/advanced/repository.py
  - backend/app/advanced/sandbox.py
  - backend/app/advanced/schemas.py
  - backend/app/advanced/viewpoints.py
  - backend/app/advanced/workflow.py
  - backend/app/api/intraday.py
  - backend/app/contracts/market_data.py
  - backend/app/data_providers/fixture_provider.py
  - backend/app/jobs/daily_pipeline.py
  - backend/app/main.py
  - backend/app/operational/migrations.py
  - backend/app/research/repository.py
  - backend/app/services/quote_service.py
  - frontend/playwright.config.ts
  - frontend/src/components/advanced/AdvancedResearchPanels.tsx
  - frontend/src/components/advanced/ViewpointPanel.tsx
  - frontend/src/components/analysis/AnalysisWorkspace.tsx
  - frontend/src/lib/api.ts
  - frontend/src/lib/queryKeys.ts
  - frontend/src/lib/useQuoteStream.ts
  - frontend/src/pages/Backtest.tsx
findings:
  critical: 3
  warning: 1
  info: 0
  total: 4
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-14T03:32:56Z  
**Depth:** deep  
**Files Reviewed:** 30 committed source files  
**Status:** issues_found

## Summary

Reviewed the committed Phase 04 implementation at `HEAD`, excluding the isolated checkout's uncommitted changes. The authorization, immutable-ledger, SSE filtering, public DTO, sandbox-probe, host-fixture, and frontend/API handoff paths were traced across their module boundaries. The SSE projection is subscription-scoped and the custom-source launcher has no host-process fallback, but three server-side boundaries still permit policy or provenance violations. The host-fixture checks also fall short of the documented fail-before-readiness safeguards.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01 [BLOCKER]: Authorized experiment APIs do not bind a run's strategy to its server-owned research asset

**File:** `backend/app/advanced/api.py:356-365`; `backend/app/advanced/schemas.py:92-115`; `backend/app/advanced/governed_runner.py:47-56, 96-115`

**Issue:** The specification endpoint authorizes only `research_asset_id`, then persists the client-supplied `data_scope.strategy_id` unchanged. `FrozenStrategyScope` accepts any identifier, and the governed worker passes that identifier directly to `StrategyBacktestConfig` while its engine loads built-in, custom, and AI strategy directories. A caller can therefore use the one lifecycle-authorized research asset as a ticket to execute a different installed custom/AI strategy outside the immutable strategy-to-asset binding required by Plan 21. The UI displays the bound strategy, but direct authenticated API calls are not constrained by that UI.

**Fix:** Resolve the persisted binding on the server when creating a specification and require its `strategy_id` to match the scope. Prefer removing `strategy_id` from the browser request and constructing it from the binding. Repeat the invariant in `ExperimentService.create_specification` or the governed runner so non-router callers cannot bypass it. Add a public-route regression that submits a valid asset with a different strategy ID and proves no specification, worker, or sandbox evidence is created.

### CR-02 [BLOCKER]: Per-task deployment quotas are collapsed to the highest quota and can be exceeded

**File:** `backend/app/main.py:242-252`; `backend/app/advanced/repository.py:164-205`

**Issue:** `AdvancedPolicy.rate_limits` is keyed by task type, but the lifecycle converts it into one `quota_per_window=max(...)`. The repository rate-window identity and `quota_is_current` query do not include `task_type`. With the default policy (`research_draft: 10`, `experiment: 5`, `strategy_evaluation: 5`), an authenticated client can create ten experiment or strategy-evaluation jobs in an hour rather than five; those tasks also consume the same undifferentiated counter. This defeats the server-owned resource-control policy at both job creation and start-time revalidation.

**Fix:** Carry a task-specific quota from the policy into authorization/job creation, and make the durable rate-window identity and queries include `task_type` (with an additive migration and immutability trigger update). Revalidate against that same task-specific window before work starts. Add boundary tests proving five experiment jobs exhaust only the experiment bucket and do not consume the research-draft bucket.

### CR-03 [BLOCKER]: The real-host fixture accepts invalid market bars and a wrong benchmark instead of failing closed at startup

**File:** `backend/app/contracts/market_data.py:28-51, 71-86`; `backend/app/jobs/daily_pipeline.py:88-93`; `backend/app/contracts/validator.py:149-160`

**Issue:** `FixtureDailyBar` constrains neither positive/finite OHLC, volume/amount, timestamp nor OHLC ordering. `MarketDataFixtureFile` accepts arbitrary ordering and does not require a specific benchmark symbol. The fixture sync writes those values directly into the governed lake; the final validator checks only schemas, primary-key duplicates, and market-time. Consequently, a non-empty `index_daily` collection containing no `000300.SH`, or bars with negative/NaN prices, invalid OHLC ranges, zero volume/amount, or non-positive timestamps can pass fixture load and begin serving. This contradicts Plan 21's explicit readiness contract and can turn corrupted fixture data into unevaluable or misleading completed research evidence.

**Fix:** Add a dedicated advanced-host fixture preflight before readiness that requires the configured benchmark, chronological unique bars, finite positive OHLC/volume/amount, `low <= open/close <= high`, valid positive in-session timestamps, and the required historical/window coverage. Reject invalid input with `FixtureContractError` before writing any lake data. Exercise each rejected shape and the missing-`000300.SH` case in startup tests.

## Warnings

### WR-01 [WARNING]: Repeated evaluation requests inflate calibration samples with duplicate outcomes for one immutable version

**File:** `backend/app/advanced/api.py:314-335`; `backend/app/advanced/viewpoints.py:157-176`; `backend/app/advanced/repository.py:549-573`

**Issue:** The empty-body evaluation route is repeatable. Each call appends another evaluated fact for the same viewpoint version, and `calibration()` aggregates every evaluated ledger row rather than one latest or canonical outcome per version. A user can repeatedly evaluate a favorable version until its confidence bucket reaches the minimum sample count or biases its hit rate and mean relative return. Append-only storage preserves the duplicate facts, but it does not make them independent calibration observations.

**Fix:** Make server evaluation idempotent once a terminal outcome exists, or keep the append-only attempts but aggregate only the deterministic latest/first terminal outcome per `viewpoint_version_id`. Add a regression that evaluates one version twice and verifies its calibration contribution remains one.

## Verification

Static deep review only. Phase summaries/plans and the committed source paths above were inspected; no formatter, linter, build, or test suite was run. No runtime result is claimed.

## REVIEW COMPLETE

---
_Reviewed: 2026-07-14T03:32:56Z_  
_Reviewer: Claude (gsd-code-reviewer)_  
_Depth: deep_
