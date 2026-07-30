---
phase: 06-release-reproducibility
verified: 2026-07-30T17:07:31Z
status: human_needed
score: 5/7 must-haves verified
behavior_unverified: 2
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/7
  gaps_closed:
    - "The documented backend/ command now resolves relative planning-artifact arguments against canonical --repo-root, and a focused test reaches provenance preflight with the documented cwd/argument shape."
  gaps_remaining: []
  regressions: []
behavior_unverified_items:
  - truth: "A clean Windows checkout can run the documented command end to end and produce the complete frozen-source evidence bundle."
    test: "Run the documented command without --github-run-id in a clean Windows checkout with WSL available."
    expected: "Four labeled reports, four adjacent provenance sidecars, and a passing parser verdict are produced; the Linux leg runs through WSL."
    why_human: "Repository-relative path preflight and Windows/WSL unit contracts pass, but no test executes the complete producer-to-parser transition on a real Windows host."
  - truth: "A clean native-Linux checkout can run the same command end to end without historical CI access."
    test: "Run the documented command without --github-run-id in a clean native-Linux checkout."
    expected: "The Linux producer runs directly, no WSL or GitHub evidence is used, and the same four-report/provenance/verdict bundle passes."
    why_human: "The focused tests exercise path preflight, native producer specs, sidecars, and parsing separately; they do not execute the full state-mutating orchestration in a clean checkout."
human_verification:
  - test: "Run the documented command without --github-run-id in a clean Windows checkout with WSL available."
    expected: "Four labeled reports, four adjacent provenance sidecars, and a passing parser verdict are produced; the Linux leg runs through WSL."
    why_human: "A real Windows/WSL producer run was not available to this Linux verification."
  - test: "Run the documented command without --github-run-id in a clean native-Linux checkout."
    expected: "Native Linux produces and validates the complete bundle without WSL or historical GitHub artifacts."
    why_human: "The current checkout contains concurrent changes inside the gate's provenance scope, and the assignment excluded the full producer run."
---

# Phase 6: Release Reproducibility Verification Report

**Phase Goal:** Operators can regenerate the complete release evidence bundle from a clean checkout on either supported host, with no dependency on historical attestations or CI-only artifacts.
**Verified:** 2026-07-30T17:07:31Z
**Status:** human_needed
**Re-verification:** Yes — after documented-command path gap closure

## Goal Achievement

The roadmap's three success criteria were merged with the five PLAN truths. The PLAN truth about four reports, provenance sidecars, and a parser verdict is evaluated within the two host outcomes and the fresh-report final-gate outcome rather than counted again.

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | A clean Windows checkout can run the single documented command and produce the backend JUnit report, both Playwright reports, and final-gate evidence matching the frozen source. | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | The former path blocker is closed: `_canonical_from_repo()` resolves relative paths against canonical `--repo-root` (`verify_phase5_final_gate.py:352-354,2180-2189`), and `test_documented_command_resolves_planning_paths_from_repo_root` reaches provenance preflight from the documented `backend/` cwd. WSL path/error and producer-spec tests pass. No real Windows/WSL run exercises all producers, sidecars, parser, and final update. |
| 2 | A clean Linux checkout can run the same command and produce the same bundle shape without historical CI access. | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | The documented path regression passes; native Linux specs execute directly with `cwd=backend` and no `wsl.exe`, while omission of `--github-run-id` selects the local branch. Four-report parsing and sidecar tests pass. No clean-checkout end-to-end producer run was performed. |
| 3 | The final-gate verifier accepts fresh, same-run reports and fails closed without cached attestations or CI-only artifacts. | ✓ VERIFIED | `validate_report_envelopes()` requires exactly four labels and adjacent same-run sidecars; `test_four_bound_reports_parse_all_fifteen_findings` plus sidecar/stale/out-of-root rejection tests passed in the current 75-test module run. The local branch does not fetch CI evidence unless `github_run_id` is explicit. |
| 4 | Final-gate planning paths are archival-layout-independent, and vendor sync has no archival approval-summary dependency. | ✓ VERIFIED | `_find_phase05_dir(repo_root)` searches milestone archives then falls back to active phases; runtime artifact arguments are now normalized relative to `repo_root`. No hardcoded active Phase 05 literal exists in the relevant scripts/tests. `sync_kronos.py` contains no approval-summary path or paperwork read. |
| 5 | Linux evidence is local-first (native Linux or WSL on Windows), while GitHub download is explicit opt-in and retained. | ✓ VERIFIED | `orchestrate()` branches on `github_run_id is None` and `os.name`. Native-Linux specs, WSL failure handling, GitHub artifact binding, workflow contract, and CLI optional-help behavior are covered by passing focused tests. |
| 6 | Historical approval paperwork is not a supply gate, while source identity and SHA-256/config/weight checks remain fail-closed. | ✓ VERIFIED | Quick regression check found no restored approval-summary symbol or prohibited path. Initial focused evidence remains applicable: vendor-sync tests passed, and four catalog rejection tests passed for moving revisions, weight tamper, config/source tamper, and missing config digests. Pinned identities remain wired through `bootstrap.py`, `catalog.py`, and `provision.py`. |
| 7 | The nine named pre-existing final-gate/path and vendor-approval failures are resolved without moving Phase 05 back into active phases. | ✓ VERIFIED | Current final-gate module: `75 passed, 1 skipped`. Initial focused three-module result: `93 passed, 1 skipped`. Phase 05 remains archived under `.planning/milestones/v1.0-phases/`; the active phases directory contains Phase 06 only. |

**Score:** 5/7 truths verified (2 present, behavior-unverified)

## Gap Closure Verification

| Previous Gap | Fix Evidence | Regression Evidence | Status |
|---|---|---|---|
| Documented `backend/` command resolved `.planning/...` below `backend/` and failed canonical path preflight | `_canonical_from_repo()` joins non-absolute artifact arguments to canonical `repo_root`; `orchestrate()` applies it to validation, summary, and plan paths. The SUMMARY now explicitly documents repository-root-relative semantics and has a valid code fence. | `test_documented_command_resolves_planning_paths_from_repo_root` changes cwd to `backend/`, supplies the documented argument shape, verifies the resolved summary, and reaches `capture_git_provenance`. It passed in `75 passed, 1 skipped`. | ✓ CLOSED |

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/scripts/verify_phase5_final_gate.py` | Dynamic Phase 05 resolution, repository-relative CLI paths, local-first Linux production, four-producer orchestration | ✓ VERIFIED | Exists, substantive, and wired from CLI through path preflight, provenance, producer specs, sidecars, parser, and scoped atomic update. |
| `backend/scripts/sync_kronos.py` | Supply sync independent of historical paperwork, with fail-closed source identity | ✓ VERIFIED | Exists and substantive. The PLAN artifact wording about a “dynamic approval-summary path” is stale and conflicts with Task 3; complete removal is the required outcome. |
| `backend/tests/test_phase5_final_gate.py` | Path/platform/report/provenance regression coverage | ✓ VERIFIED | Current focused execution: `75 passed, 1 skipped`; the new documented-command regression is substantive and reaches provenance preflight. |
| `backend/tests/test_kronos_vendor_sync.py` | Vendor identity and digest rejection without paperwork mocks | ✓ VERIFIED | Present and unchanged from the initial passing focused run; quick symbol scan confirms no approval gate returned. |
| `.github/workflows/phase5-linux-evidence.yml` | Retained opt-in CI Linux evidence producer | ✓ VERIFIED | Present and still contract-tested by the passing final-gate module. |
| `.planning/phases/06-release-reproducibility/06-01-SUMMARY.md` | Runnable single operator command | ✓ VERIFIED | Valid fence; command runs from `backend/`; lines 60-61 accurately state that relative planning paths resolve against `--repo-root`. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| documented operator command | canonical Phase 05 artifacts | `_canonical_from_repo(path, repo_root)` | ✓ WIRED | The exact documented cwd and relative argument shape reaches provenance preflight in the new focused regression test. |
| `verify_phase5_final_gate.py` | archived or active Phase 05 directory | `_find_phase05_dir(repo_root)` | ✓ WIRED | Milestone directories are searched first; active phases are the fallback; canonical comparisons use that resolved directory. |
| `sync_kronos.py` | approval summary artifact | PLAN frontmatter pattern `APPROVAL_SUMMARY\|resolve_planning_path` | N/A — INTENTIONALLY ABSENT | Wiring this link would contradict Task 3 and the truth requiring paperwork removal. Vendor authority is linked directly to pinned constants and `UPSTREAM.json`. |
| `orchestrate()` | local Linux or explicit GitHub Linux evidence | `github_run_id`/`os.name` branch | ✓ WIRED | No run ID selects native Linux or WSL; a run ID selects the retained GitHub path; both feed the same strict envelope validator. |
| `sync_kronos.verify_vendor()` | pinned source and vendored bytes | repository/commit/blob/SHA-256 comparisons | ✓ WIRED | Actual bytes flow through allowlist, identity, approved-diff, and digest checks before verification returns. |

## Data-Flow Trace (Level 4)

| Artifact | Data | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `orchestrate()` path preflight | Canonical validation, summary, and plan paths | CLI arguments resolved against `--repo-root` | Existing canonical files are required before provenance capture | ✓ FLOWING |
| `orchestrate()` evidence flow | Four report paths and provenance envelopes | Four local producers by default; explicit GitHub fallback for Linux only | Producers must create real files; sidecars bind HEAD/tree/run ID; parser writes `parser-verdict.json` | ✓ WIRED; complete cross-host transition awaits human execution |
| `verify_report_envelopes()` | Fifteen required findings | Two JUnit and two Playwright reports with adjacent sidecars | Strict parsers reject missing, skipped, duplicate, stale, out-of-root, or mismatched evidence | ✓ FLOWING |
| `sync_kronos.verify_vendor()` | Verified destination SHA-256 map | Local vendor files plus `UPSTREAM.json` and pinned constants | Reads actual bytes and compares source/vendored/reviewed identities | ✓ FLOWING |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Gap closure and final-gate regression | `cd backend && uv run pytest tests/test_phase5_final_gate.py -q --tb=short` | `75 passed, 1 skipped in 0.58s` | ✓ PASS |
| Documented command path semantics | `test_documented_command_resolves_planning_paths_from_repo_root` within the focused module | Documented `backend/` cwd and `.planning/...` arguments resolve to repository-root artifacts and reach provenance preflight | ✓ PASS |
| Supply identity/digest regression (initial verification evidence) | Four named `tests/forecast/test_catalog.py` rejection tests | `4 passed in 0.08s` | ✓ PASS |
| Phase 06 combined regression (initial verification evidence) | Three PLAN-targeted modules | `93 passed, 1 skipped in 1.86s` | ✓ PASS |

A project-wide test suite was intentionally not run. Re-verification focused on the fixed final-gate module and used quick regression checks for previously verified, unchanged supply artifacts.

## Probe Execution

No probe script or probe-based criterion is declared by the Phase 06 PLAN or SUMMARY.

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| REL-01 | `06-01-PLAN.md` | Operator can regenerate the complete release evidence bundle from a clean Windows or Linux checkout without historical attestations or CI-only artifacts. | ? NEEDS HUMAN | The documented command now reaches provenance preflight, and all component contracts pass focused tests. Complete clean-host runs on Windows/WSL and native Linux remain unexecuted. |

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| Phase 06 changed files | — | `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, placeholder, malformed fence, prohibited active Phase 05 literal, or restored approval-summary gate | None | No blocker or warning marker found in the re-verification scan. |

## Human Verification Required

### 1. Clean Windows/WSL end-to-end regeneration

**Test:** In a clean Windows checkout with WSL available, run the documented command without `--github-run-id`.
**Expected:** Four labeled reports, four adjacent provenance sidecars, and a passing parser verdict are produced; the Linux leg runs through WSL and the validation update remains scoped.
**Why human:** The current verification ran on Linux. The focused module validates Windows/WSL contracts but does not execute the complete producer-to-parser transition on a real Windows host; one Windows-only test was skipped.

### 2. Clean native-Linux end-to-end regeneration

**Test:** In a clean Linux checkout, run the documented command without `--github-run-id`.
**Expected:** The Linux producer executes directly with no `wsl.exe` or GitHub artifact access, and the same four-report/provenance/verdict bundle is accepted.
**Why human:** The current checkout contains concurrent changes under the gate's `backend` provenance scope, and the assignment excluded the state-mutating full producer run. Unit tests prove path, branch, spec, sidecar, and parser behavior separately.

## Gaps Summary

The prior automated blocker is closed, with no remaining programmatically observed gap or regression. The phase remains at the escalation gate because both roadmap host outcomes are runtime behaviors not exercised end to end on clean supported hosts. Their implementation is present and wired, but presence and component tests do not certify the full cross-host transition.

---

_Verified: 2026-07-30T17:07:31Z_
_Verifier: Claude (gsd-verifier)_
