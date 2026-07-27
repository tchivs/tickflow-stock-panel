---
phase: 01
slug: core-merger
status: validated
nyquist_compliant: true
wave_0_complete: true
validated_at: 2026-07-27T09:29:56+08:00
plans_audited: 15
tasks_mapped: 30
requirements_covered: 9
gaps_found: 2
gaps_resolved: 2
current_compose_reproduction: unavailable
compose_evidence: attested-not-rerun
---

# Phase 01 Validation Strategy

## Validation verdict

**VALIDATED — Phase 01 is Nyquist-compliant; Compose acceptance is attested, not rerun.**

All 15 executed plans and all 30 plan tasks map to automated evidence. The nine Phase 01 requirements (`CORE-01` through `CORE-07`, `PLAN-01`, and `PLAN-02`) have current portable test coverage or accepted hermetic Compose evidence.

The current audit found two genuine time-determinism gaps in Phase 01 tests. Both were fixed only in test code:

1. The position-rule isolation test depended on wall-clock market hours and failed before its 09:30 active window. It now injects a fixed clock.
2. The operational alert-history test used a fixed 2026-07-10 event while relying on the API's moving seven-day cutoff. It now freezes the repository clock around the original fixture date.

After those fixes, the complete focused backend gate passes 39/39. No production code changed.

Docker is not installed on the current Windows host, so the Compose runner and its dependent Phase 1 desktop/mobile browser workflows were not rerun. Their accepted evidence remains the clean detached-worktree certification recorded in `01-VERIFICATION.md` at revision `1034413f6f9c0fd4686c05e49cecfd422bb33ac5`.

## Scope and source inventory

| Source | Audit result |
|---|---|
| `01-01-PLAN.md` through `01-15-PLAN.md` | 15/15 read |
| `01-01-SUMMARY.md` through `01-15-SUMMARY.md` | 15/15 present; 13 explicitly declare `status: complete`; legacy summaries 01-09 and 01-11 omit the field but contain completion evidence and are accepted by verification |
| Plan tasks | 30/30 mapped below |
| `01-VERIFICATION.md` | `status: passed` at certified revision `1034413` |
| Requirements | 9/9 marked complete and mapped |
| Post-phase browser completion | `ccab55d82abcfe1ad3a130ac6b3373c3e7a3ced8` and `8c3bf4e` included in current HEAD |

## Test infrastructure and current execution

| Gate | Command / evidence | Current result | Classification |
|---|---|---|---|
| Focused Phase 01 backend, first run | `cd backend && .\.venv\Scripts\python.exe -m pytest tests\test_phase1_fixture_sync.py tests\test_data_contracts.py tests\test_portfolio_api.py tests\test_position_monitor.py tests\test_notification_delivery.py tests\test_portfolio_sse.py tests\test_decision_playbook.py tests\test_decision_adjustments.py tests\test_decision_ai_review.py tests\test_decision_replay.py -q` | 37 passed, 2 failed, 3 warnings | GAPS FOUND — two moving-clock test failures |
| Resolved-gap regression | The two failing test node IDs above | **2 passed** in 1.22s | PASS |
| Focused Phase 01 backend, final run | Same ten-file command | **39 passed, 3 warnings** in 18.39s | PASS |
| Changed-test lint | `cd backend && .\.venv\Scripts\ruff.exe check tests\test_position_monitor.py tests\test_notification_delivery.py` | PASS | PASS |
| Direct TypeScript build | `cd frontend && .\node_modules\.bin\tsc.cmd -b` | PASS in 20.3s | PASS |
| PLAN-01/02 fixture-browser decision chain | `cd frontend && node .\node_modules\@playwright\test\cli.js test e2e/decision-playbook-flow.spec.ts --project=desktop-chromium --reporter=list` | **3 passed** in 13.9s | PASS |
| Phase 1 Compose-browser collection | `cd frontend && node .\node_modules\@playwright\test\cli.js test e2e/phase1.spec.ts --project=desktop-chromium --project=mobile-chromium-320 --list` | 4 project-cases collected; two are cross-project skips by design | PASS (collection only) |
| Playwright package admission | Installed package metadata | `@playwright/test` **1.61.1** | PASS |
| Upstream ownership map | Required-source static check against `docs/UPSTREAM-SYNC.md` | PanWatch, Hermes, Tickflow, Parquet, and SQLite ownership markers present | PASS |
| Compose availability | `docker version`; `docker compose version` | `docker` command not found | UNAVAILABLE — not executed |

The three backend warnings are existing Polars deprecation/sortedness warnings reached through fixture synchronization; they are not assertion failures.

## Requirement coverage

| Requirement | Primary automated evidence | Current status | Accepted closure |
|---|---|---|---|
| `CORE-01` — governed A-share/financial/enriched synchronization | `test_phase1_fixture_sync.py`; hermetic fixture acceptance | Portable test passes; Compose not rerun | COVERED by current test plus accepted Compose evidence |
| `CORE-02` — keys, time semantics, repair windows, schema drift | `test_data_contracts.py`; fixture acceptance | Current backend passes | COVERED |
| `CORE-03` — account/position lifecycle and current P&L | `test_portfolio_api.py`; Phase 1 desktop/mobile workflow | Current backend passes; browser workflow attested | COVERED |
| `CORE-04` — rules, durable alert history, bounded delivery | `test_position_monitor.py`, `test_notification_delivery.py`; Compose delivery assertions | Current tests pass after deterministic-clock fixes | COVERED |
| `CORE-05` — shared market/portfolio SSE | `test_portfolio_sse.py`; Compose named-event assertions | Current backend passes; network path attested | COVERED |
| `CORE-06` — one-command isolated acceptance without external DB/queue | Compose topology, verifier smoke, runner, desktop/mobile Playwright | Docker unavailable currently | COVERED by accepted clean-worktree Compose certification |
| `CORE-07` — documented upstream synchronization ownership | `docs/UPSTREAM-SYNC.md` static check and verification | Current static check passes | COVERED |
| `PLAN-01` — deterministic baseline playbook | `test_decision_playbook.py`; current decision-browser full flow | Backend and browser pass | COVERED |
| `PLAN-02` — bounded audited AI adjustments and AI-free replay | decision adjustment/review/replay tests; `ccab55d` + `8c3bf4e` browser regressions | Backend and three browser cases pass | COVERED |

## PLAN-01/02 post-phase browser closure

| Evidence | Behavior proved |
|---|---|
| `ccab55d` — `decision flow keeps AI advisory until explicit bounded apply, then compares and replays` | Deterministic run creation; provider proposal remains advisory; explicit apply sends only allowed fields; audit is rendered; replay sends selected run and cutoff |
| `8c3bf4e` enhancement to the main flow | Applied and clamped dispositions show proposed/final values and rationale; the baseline remains unchanged until explicit apply |
| `8c3bf4e` — `late review and replay settlements from the prior run never render into the selected run` | Mutation state is scoped to the selected run; stale review/replay settlements cannot contaminate run B |
| `8c3bf4e` — `failed replay keeps its cutoff and retries with the same run-scoped variables` | Failure retains cutoff and retry reuses identical `{run_ids, as_of}` variables |
| Backend decision suite | Deterministic stable baseline, allowlisted adjustment audit, provider provenance/fallback, as-of-bounded ordered hash-stable AI-free replay |

## Compose evidence boundary

Current environment:

- Windows host
- no `docker` executable
- Compose config cannot be resolved by the Docker CLI
- `compose/phase1/prepare-images.sh` and `compose/phase1/run.sh` were not invoked
- Phase 1 desktop/mobile Playwright execution was not attempted without its required fixture topology

Accepted historical evidence from `01-VERIFICATION.md`:

- clean detached worktree at exact revision `1034413`
- app, receiver, and verifier images prepared successfully
- network-disabled verifier smoke passed
- internal-only topology with sole loopback published port passed
- no-build/no-pull `compose/phase1/run.sh` completed with verifier exit code 0
- fixture sync, SQLite account/position operations, rule trigger, Feishu/Telegram receiver payloads, and named SSE events passed
- deterministic decision review stayed unavailable in fixture mode and replay remained AI-free
- Phase 1 desktop and mobile workflows: **2 passed**, cross-project duplicates skipped

This evidence is explicitly **attested-not-rerun**. No current Compose pass is claimed.

## Complete plan-to-test map

Every task ID below corresponds to an actual `<task>` element in an executed plan.

| Plan | Task IDs mapped | Requirements | Automated evidence | Status |
|---|---|---|---|---|
| 01-01 | 01-01-01 | CORE-01/02 | fixture-sync and data-contract RED/green contracts | PASS |
| 01-02 | 01-02-01, 01-02-02 | CORE-01/02 | `test_phase1_fixture_sync.py`, `test_data_contracts.py` | PASS |
| 01-03 | 01-03-01, 01-03-02 | CORE-03 | `test_portfolio_api.py` | PASS |
| 01-04 | 01-04-01, 01-04-02 | PLAN-01 | `test_decision_playbook.py`; decision-browser generation/open flow | PASS |
| 01-05 | 01-05-01 | CORE-04 | `test_position_monitor.py` with fixed-clock isolation | PASS |
| 01-06 | 01-06-01 | CORE-06 | recorded package legitimacy approval; current version 1.61.1 | PASS |
| 01-07 | 01-07-01, 01-07-02 | CORE-06 | package metadata; current Phase 1 Playwright collection; attested desktop/mobile execution | PASS + ATTESTED |
| 01-08 | 01-08-01, 01-08-02, 01-08-03 | CORE-03/04/05, PLAN-01/02 | direct TypeScript build; backend operational tests; decision browser | PASS |
| 01-09 | 01-09-01, 01-09-02, 01-09-03 | CORE-03/05 | direct TypeScript build, portfolio API, attested Phase 1 browser workflow | PASS + ATTESTED |
| 01-10 | 01-10-01, 01-10-02 | CORE-04, PLAN-01/02 | direct TypeScript build; current decision browser | PASS |
| 01-11 | 01-11-01, 01-11-02, 01-11-03 | CORE-06/07 | current ownership-map check; accepted Compose topology/smoke/runner/browser certification | ATTESTED |
| 01-12 | 01-12-01, 01-12-02 | CORE-04/05 | `test_notification_delivery.py`, `test_portfolio_sse.py` | PASS |
| 01-13 | 01-13-01, 01-13-02 | CORE-03/04/05 | portfolio, monitor, delivery, and shared-SSE tests | PASS |
| 01-14 | 01-14-01, 01-14-02 | PLAN-01/02 | four backend decision contract files; current three-case browser regression | PASS |
| 01-15 | 01-15-01, 01-15-02 | PLAN-02 | configured review/adjustment/replay backend tests; decision browser audit/replay cases | PASS |

## Resolved Nyquist gaps

| Gap | Root cause | Test-only resolution | Verification |
|---|---|---|---|
| Position run isolation test failed outside active hours | `MonitorRuleEngine()` consumed wall clock despite fixture rule declaring 09:30–15:00 | Inject fixed UTC datetime through the engine's existing `clock` seam | Targeted pass; full suite pass |
| Alert-history safety test aged out after seven days | Fixed event date was compared with moving repository `datetime.now()` | Freeze repository `datetime.now()` at 2026-07-10 while preserving the production seven-day cutoff | Targeted pass; full suite pass |

These changes tighten determinism; they do not enlarge time windows, weaken assertions, or modify production behavior.

## Manual-only status

No outstanding manual-only requirement remains:

- Playwright legitimacy was approved for exactly `@playwright/test@1.61.1`; the installed version still matches.
- The upstream adoption map exists and passes the current source/owner marker check.
- Compose is an unavailable current execution environment, not an untested behavior; its accepted hermetic certification remains recorded.

## Validation Audit 2026-07-27

| Metric | Count |
|---|---:|
| Plans audited | 15 |
| Summaries present | 15 |
| Tasks mapped | 30 |
| Requirements covered | 9 |
| Gaps found | 2 |
| Resolved | 2 |
| Escalated | 0 |
| Compose reruns | 0 |

## Final sign-off

- [x] All 15 plans and summaries audited.
- [x] All 30 tasks map to automated or accepted hermetic evidence.
- [x] All nine requirements are covered.
- [x] Two time-dependent tests now use controlled clocks.
- [x] Focused backend, direct TypeScript, and decision browser gates pass.
- [x] `ccab55d` and `8c3bf4e` PLAN-01/02 run-isolation, audit, and replay regressions are included.
- [x] Docker/Compose and Phase 1 browser execution are accurately marked attested-not-rerun.
- [x] No production code changed.
- [x] `status: validated` and `nyquist_compliant: true` are set.

**Approval:** validated
