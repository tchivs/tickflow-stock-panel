---
phase: 06-release-reproducibility
verified: 2026-07-31T05:14:46Z
status: human_needed
score: 6/7 must-haves verified
behavior_unverified: 1
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/7
  gaps_closed:
    - "The prior native-Linux behavior-unverified item is closed by the supplied detached-clean-checkout full-gate evidence."
  gaps_remaining: []
  regressions: []
behavior_unverified_items:
  - truth: "A clean Windows checkout can run the documented command end to end and produce the complete frozen-source evidence bundle."
    test: "Run the documented command with --evidence-only and without --github-run-id in a clean Windows checkout with WSL available."
    expected: "Four labeled reports, four adjacent provenance sidecars, and a passing parser verdict are produced; the Linux leg runs through WSL and the result reports validationUpdated: false."
    why_human: "The native-Linux clean run proves the shared producer-to-parser path, but no real Windows/WSL run exercises Windows path translation and the WSL process boundary."
human_verification:
  - test: "Run the documented command with --evidence-only and without --github-run-id in a clean Windows checkout with WSL available."
    expected: "Four labeled reports, four adjacent provenance sidecars, and a passing parser verdict with discovered equal to passed are produced; the Linux leg runs through WSL and validationUpdated remains false."
    why_human: "No complete run on a real Windows host with WSL is available; native-Linux evidence cannot exercise that host boundary."
---

# Phase 6: Release Reproducibility Verification Report

**Phase Goal:** Operators can regenerate the complete release evidence bundle from a clean checkout on either supported host, with no dependency on historical attestations or CI-only artifacts.
**Verified:** 2026-07-31T05:14:46Z
**Status:** human_needed
**Re-verification:** Yes — after clean native-Linux end-to-end evidence regeneration

## Goal Achievement

The seven observable truths combine the Phase 6 goal and REL-01's two supported-host outcomes with the five PLAN truths. The PLAN truth about four reports, provenance sidecars, and a parser verdict is evaluated within the host outcomes and the fresh-report final-gate outcome rather than counted twice.

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | A clean Windows checkout can run the single documented command and produce the backend JUnit report, both Playwright reports, and final-gate evidence matching the frozen source. | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Repository-relative preflight, Windows/WSL path conversion, actionable no-WSL handling, producer specs, sidecars, parser, and `--evidence-only` wiring are present and covered by focused contracts. The successful native-Linux run proves the shared end-to-end path but does not exercise a real Windows/WSL boundary. |
| 2 | A clean native-Linux checkout can run the same command and produce the same bundle shape without historical CI access. | ✓ VERIFIED | Supplied authoritative evidence from a detached clean checkout at HEAD `e5244ac4ccb5feffff2fb0054741a4462a6ea2e6`, tree `fc4fa0a8dcae9a83bf5aba66a1008464d74f95d0`: pytest-windows 170 passed, pytest-linux 454 passed, fixture Playwright 34 passed, real-host Playwright 1 passed, and the parser accepted 659 discovered/659 passed. The command omitted `--github-run-id`, used `--evidence-only`, returned `validationUpdated: false`, and wrote under `/home/orca/tmp/athena-phase5-44-8b8a5e02-93a8-4e77-9199-0028c03a98e2`. |
| 3 | The final-gate verifier accepts fresh, same-run reports and fails closed without cached attestations or CI-only artifacts. | ✓ VERIFIED | The detached clean run produced all four reports and adjacent provenance envelopes from the frozen HEAD/tree, then `verify_report_envelopes()` returned `status: passed`, `discovered: 659`, `passed: 659`. No `--github-run-id` was supplied, so no historical CI artifact could satisfy the Linux leg. |
| 4 | Final-gate planning paths are archival-layout-independent, and vendor sync has no archival approval-summary dependency. | ✓ VERIFIED | `_find_phase05_dir(repo_root)` searches milestone archives then falls back to active phases; runtime artifact arguments are now normalized relative to `repo_root`. No hardcoded active Phase 05 literal exists in the relevant scripts/tests. `sync_kronos.py` contains no approval-summary path or paperwork read. |
| 5 | Linux evidence is local-first (native Linux or WSL on Windows), while GitHub download is explicit opt-in and retained. | ✓ VERIFIED | The successful clean native-Linux command omitted `--github-run-id` and completed the native producer directly. `orchestrate()` still selects WSL on Windows and the retained GitHub path only when a run ID is explicit; focused Windows/WSL and GitHub contracts remain the evidence for those branches. |
| 6 | Historical approval paperwork is not a supply gate, while source identity and SHA-256/config/weight checks remain fail-closed. | ✓ VERIFIED | Quick regression check found no restored approval-summary symbol or prohibited path. Initial focused evidence remains applicable: vendor-sync tests passed, and four catalog rejection tests passed for moving revisions, weight tamper, config/source tamper, and missing config digests. Pinned identities remain wired through `bootstrap.py`, `catalog.py`, and `provision.py`. |
| 7 | The nine named pre-existing final-gate/path and vendor-approval failures are resolved without moving Phase 05 back into active phases. | ✓ VERIFIED | The PLAN names four archival path failures plus five vendor-approval failures. Dynamic Phase 05 resolution and removal of the paperwork gate close those causes; prior focused verification recorded `75 passed, 1 skipped` for the final-gate module and `93 passed, 1 skipped` across the three PLAN-targeted modules. The clean full gate then completed both pytest legs (170 + 454 passed) without recurrence, while Phase 05 remains archived. |

**Score:** 6/7 truths verified (1 present, behavior-unverified)

## Prior Failure and Gap Closure Verification

| Prior Item | Fix Evidence | Closure Evidence | Status |
|---|---|---|---|
| Initial verification blocker: the documented command runs from `backend/`, so relative `.planning/...` arguments were previously resolved below `backend/` and failed canonical preflight | `_canonical_from_repo()` joins non-absolute artifact arguments to canonical `repo_root`; `orchestrate()` applies it to validation, summary, and plan paths. The SUMMARY documents repository-root-relative semantics and includes `--evidence-only`. | The prior focused regression reached provenance preflight from the documented cwd/argument shape. More importantly, the same documented shape completed from the detached clean native-Linux checkout. | ✓ CLOSED |
| Previous report left native-Linux complete orchestration behavior unverified | Native Linux runs the Linux producer directly; `--evidence-only` maps to `update_validation=False` while preserving all production, sidecar, and parser stages. | The clean run produced 170 + 454 + 34 + 1 passing results, a 659/659 parser verdict, and `validationUpdated: false`. | ✓ CLOSED |
| PLAN's nine named pre-existing failures: four archival path-drift failures and five vendor approval-paperwork failures | `_find_phase05_dir()` resolves the archived layout; `sync_kronos.py` no longer reads approval paperwork while retaining identity/digest checks. | Prior focused module runs passed; the frozen clean tree completed both pytest producers and the complete parser gate. | ✓ CLOSED |
| SUMMARY's separate POSIX process-tree mock failure | `fake_killpg` handles signal 0 and simulates disappearance after SIGKILL; production assertions are platform-aware. | The final-gate module passed in prior focused verification and the clean full gate completed at the evidence commit. | ✓ CLOSED |

**Count note:** The PLAN contract explicitly names nine failures (4 path drift + 5 vendor approval). The SUMMARY additionally lists one POSIX signal failure and two optional-dependency pin-assertion failures, while its displayed subtotals `5 + 5 + 2` do not equal its `11` headline. This report therefore does not reuse that headline as an exact baseline; closure is grounded in the named causes and the exact clean-gate counts above.

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/scripts/verify_phase5_final_gate.py` | Dynamic Phase 05 resolution, repository-relative CLI paths, local-first Linux production, four-producer orchestration | ✓ VERIFIED | Exists, substantive, and wired from CLI through canonical preflight, frozen provenance, all producers, adjacent sidecars, parser, and optional scoped update. `--evidence-only` passes `update_validation=False`; the clean run proves the non-mutating native-Linux path end to end. |
| `backend/scripts/sync_kronos.py` | Supply sync independent of historical paperwork, with fail-closed source identity | ✓ VERIFIED | Exists and substantive. The PLAN artifact wording about a “dynamic approval-summary path” is stale and conflicts with Task 3; complete removal is the required outcome. |
| `backend/tests/test_phase5_final_gate.py` | Path/platform/report/provenance regression coverage | ✓ VERIFIED | Exists and substantive. Prior focused execution recorded `75 passed, 1 skipped`; the added command-path and evidence-only contracts correspond to the exact successful clean-run shape. |
| `backend/tests/test_kronos_vendor_sync.py` | Vendor identity and digest rejection without paperwork mocks | ✓ VERIFIED | Exists and substantive. Prior focused verification passed; the approval gate remains absent and the source identity/digest path remains wired. |
| `.github/workflows/phase5-linux-evidence.yml` | Retained opt-in CI Linux evidence producer | ✓ VERIFIED | Present and still contract-tested by the passing final-gate module. |
| `.planning/phases/06-release-reproducibility/06-01-SUMMARY.md` | Runnable single operator command | ✓ VERIFIED | The command runs from `backend/`, resolves planning paths against `--repo-root`, omits `--github-run-id`, and includes `--evidence-only`; that shape completed successfully in the detached clean native-Linux checkout. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| documented operator command | canonical Phase 05 artifacts | `_canonical_from_repo(path, repo_root)` | ✓ WIRED | The exact documented cwd, repository-relative argument shape, and `--evidence-only` mode completed through all producers and parser stages in the clean native-Linux run. |
| `verify_phase5_final_gate.py` | archived or active Phase 05 directory | `_find_phase05_dir(repo_root)` | ✓ WIRED | Milestone directories are searched first; active phases are the fallback; canonical comparisons use that resolved directory. |
| `sync_kronos.py` | approval summary artifact | PLAN frontmatter pattern `APPROVAL_SUMMARY\|resolve_planning_path` | N/A — INTENTIONALLY ABSENT | Wiring this link would contradict Task 3 and the truth requiring paperwork removal. Vendor authority is linked directly to pinned constants and `UPSTREAM.json`. |
| `orchestrate()` | local Linux or explicit GitHub Linux evidence | `github_run_id`/`os.name` branch | ✓ WIRED | No run ID selected and successfully completed native Linux; on Windows the same branch selects WSL. A run ID selects the retained GitHub path. All paths feed the same strict envelope validator. |
| `sync_kronos.verify_vendor()` | pinned source and vendored bytes | repository/commit/blob/SHA-256 comparisons | ✓ WIRED | Actual bytes flow through allowlist, identity, approved-diff, and digest checks before verification returns. |

## Data-Flow Trace (Level 4)

| Artifact | Data | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `orchestrate()` path preflight | Canonical validation, summary, and plan paths | CLI arguments resolved against `--repo-root` | Existing canonical files are required before provenance capture | ✓ FLOWING |
| `orchestrate()` evidence flow | Four report paths and provenance envelopes | Four local producers by default; explicit GitHub fallback for Linux only | The native-Linux run produced real 170/454/34/1 report counts, four same-run envelopes, and a 659/659 verdict | ✓ FLOWING on native Linux; Windows/WSL remains human-needed |
| `verify_report_envelopes()` | Fifteen required findings | Two JUnit and two Playwright reports with adjacent sidecars | Strict parsers reject missing, skipped, duplicate, stale, out-of-root, or mismatched evidence | ✓ FLOWING |
| `sync_kronos.verify_vendor()` | Verified destination SHA-256 map | Local vendor files plus `UPSTREAM.json` and pinned constants | Reads actual bytes and compares source/vendored/reviewed identities | ✓ FLOWING |

## Clean Native-Linux End-to-End Evidence

No project-wide test command was run during this re-verification. Per the assignment, the already-completed detached-clean-checkout gate output below is authoritative. It used the SUMMARY command shape with the actual clean checkout substituted for `/path/to/AthenaQuant`, included `--evidence-only`, and omitted `--github-run-id`:

```bash
cd backend
uv run python scripts/verify_phase5_final_gate.py orchestrate \
  --repo-root <detached-clean-checkout> \
  --validation-path .planning/milestones/v1.0-phases/05-optional-enhancements/05-VALIDATION.md \
  --phase43-summary .planning/milestones/v1.0-phases/05-optional-enhancements/05-43-SUMMARY.md \
  --plan-path .planning/milestones/v1.0-phases/05-optional-enhancements/05-44-PLAN.md \
  --evidence-only
```

| Evidence Field | Observed Result |
|---|---|
| Clean committed HEAD | `e5244ac4ccb5feffff2fb0054741a4462a6ea2e6` |
| Frozen tree | `fc4fa0a8dcae9a83bf5aba66a1008464d74f95d0` |
| pytest-windows | 170 passed |
| pytest-linux | 454 passed |
| Playwright fixture | 34 passed |
| Playwright real host | 1 passed |
| Parser verdict | `status: passed`; 659 discovered / 659 passed |
| Report root | `/home/orca/tmp/athena-phase5-44-8b8a5e02-93a8-4e77-9199-0028c03a98e2` |
| Validation history | `validationUpdated: false`; the closed validation artifact was not rewritten |
| Operational cleanup | The deployed `athenaquant` container was restored after the run |

The four producer counts sum to 659, exactly matching the parser aggregate. The clean HEAD/tree also matches the repository object verified during this review.

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Native-Linux complete producer-to-parser transition | Documented `orchestrate` command with `--evidence-only`, no `--github-run-id`, from a detached clean checkout | Four producers passed with counts 170/454/34/1; parser `659/659`; external report root emitted | ✓ PASS — supplied authoritative run |
| Frozen-source and no-history-mutation contract | Same clean run | HEAD/tree matched `e5244ac4...` / `fc4fa0a8...`; `validationUpdated: false` | ✓ PASS — supplied authoritative run |
| Prior command-path/final-gate regression | `cd backend && uv run pytest tests/test_phase5_final_gate.py -q --tb=short` | Prior verification recorded `75 passed, 1 skipped`; not rerun in this assignment | ✓ PRIOR PASS |
| Prior PLAN-targeted regression | Three PLAN-targeted pytest modules | Prior verification recorded `93 passed, 1 skipped`; not rerun in this assignment | ✓ PRIOR PASS |

## Probe Execution

No probe script or probe-based criterion is declared by the Phase 06 PLAN or SUMMARY.

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| REL-01 | `06-01-PLAN.md` | Operator can regenerate the complete release evidence bundle from a clean Windows or Linux checkout without historical attestations or CI-only artifacts. | ? NEEDS HUMAN — WINDOWS/WSL ONLY | Native Linux is verified end to end from frozen clean HEAD/tree without `--github-run-id`, with all four reports, sidecars, a 659/659 parser verdict, and no validation-history mutation. Only the equivalent clean real-Windows/WSL transition remains unexecuted. |

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| Phase 06 source/test/workflow files | — | `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, placeholder, prohibited active Phase 05 literal, or restored approval-summary gate | None | The re-verification scan found no matches. |
| `06-01-SUMMARY.md` | 29-34 | Before/after subtotal arithmetic (`5 + 5 + 2`) differs from the stated total (`11`) | ℹ️ Info | Does not affect the implementation or clean-gate verdict. This report uses the PLAN's nine named failures and exact observed clean-run counts instead of the inconsistent headline. |

## Human Verification Required

### 1. Clean Windows/WSL end-to-end regeneration

**Test:** In a detached clean Windows checkout with WSL available, run the documented command with `--evidence-only` and without `--github-run-id`.
**Expected:** The Windows pytest producer, WSL Linux producer, fixture Playwright producer, and real-host Playwright producer all emit passing reports with adjacent same-run sidecars; the parser reports equal nonzero discovered/passed totals for the frozen HEAD/tree; the result reports `validationUpdated: false`.
**Why human:** The clean native-Linux run proves the shared orchestration, reports, envelopes, parser, and evidence-only behavior, but it cannot exercise Windows path conversion, Windows process semantics, or the real WSL boundary.

## Gaps Summary

There are zero remaining programmatic gaps. The earlier documented-command path blocker remains closed, and clean native-Linux end-to-end behavior is now verified with exact frozen-source evidence. The phase remains at the escalation gate solely because REL-01 and the phase goal cover both supported hosts and no complete run has exercised a clean real Windows checkout with WSL.

---

_Verified: 2026-07-31T05:14:46Z_
_Verifier: Claude (gsd-verifier)_
