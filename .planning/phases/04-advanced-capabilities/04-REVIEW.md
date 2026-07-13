---
phase: 04-advanced-capabilities
reviewed: 2026-07-13
depth: standard
files_reviewed: 37
files_reviewed_list:
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
  - backend/app/main.py
  - backend/app/operational/migrations.py
  - backend/app/api/intraday.py
  - backend/app/services/quote_service.py
  - frontend/src/components/advanced/ViewpointPanel.tsx
  - frontend/src/components/advanced/AdvancedResearchPanels.tsx
  - frontend/src/lib/api.ts
  - frontend/src/lib/queryKeys.ts
findings:
  critical: 1
  warning: 3
  info: 0
  total: 4
status: findings
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-13  
**Depth:** standard  
**Files Reviewed:** 37 Phase 4 source and contract files named by `04-01` through `04-20` summaries, with the advanced API, lifecycle, persistence, workflow, sandbox, SSE, and UI interfaces traced.  
**Status:** findings

## Scope and method

Reviewed the Phase 4 implementation range beginning at `0d00971`, all Phase 4 `*-SUMMARY.md` artifacts, and the required Phase contracts (`04-CONTEXT.md`, `04-RESEARCH.md`, `04-AI-SPEC.md`, `04-UI-SPEC.md`, `04-VALIDATION.md`, and `04-VERIFICATION.md`). This review focused on authorization, immutable data authority, lifecycle/concurrency, sandbox isolation, and promotion evidence. No formatter, linter, build, or test command was run.

## Findings

### Critical — Verify the isolation topology used for the actual child

**File:** `backend/app/advanced/sandbox.py:290-300`

The affirmative capability probe creates a private mount tree and read-only tmpfs root, but `_bootstrap_script()` does neither before it executes submitted code. It also ignores every `mount` result. A fresh cached proof therefore does not prove the mount topology used by the child: on a host with shared mounts, a strategy running with namespace capabilities can create mounts that propagate outside the sandbox. Construct and verify the same private-root topology in the execution bootstrap, failing before `execve` when any mount/remount operation fails.

### Warning — Scope sandbox validation history to its parent asset

**File:** `backend/app/advanced/api.py:470-475`

`GET /sandbox/validations` returns every persisted validation after checking only that the caller is authenticated. Unlike terminal runs, it does not reauthorize each record's persisted `parent_asset_id`. A caller authorized for one research asset can obtain other assets' validation status, source hash, reason, and audit reference. Filter this list with the same server-side parent-asset check used for sandbox runs.

### Warning — Bind viewpoint versions to their exact policy fingerprint

**File:** `backend/app/advanced/repository.py:385-387`

A valid deployment policy can change allowed task types or rate limits while retaining the required `advanced_policy_v1` version. This lookup then reuses an older row by revision when the requested fingerprint differs, permanently attributing a new immutable viewpoint version to the old policy snapshot. Require an exact fingerprint match and persist a distinct policy fact for changed contents (with compatible versioning/schema support).

### Warning — Derive promotion split evidence from separate evaluations

**File:** `backend/app/advanced/governed_runner.py:105-110`

The runner executes one whole-period backtest, then copies its aggregate metrics into both generated in-sample and out-of-sample ranges. The promotion gate only checks that both metric maps are nonempty, so a candidate can pass the independent split-evidence gate without any actual out-of-sample result. Run and persist genuine non-overlapping evaluations before producing the split evidence used by promotion.

## Verification

Static review only, as required. The requested formatters, linters, builds, and test suites were intentionally not run.

---
_Reviewed: 2026-07-13_  
_Reviewer: Phase04CodeReview_  
_Depth: standard_
