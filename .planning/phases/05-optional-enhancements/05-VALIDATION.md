---
phase: 05
slug: optional-enhancements
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-15
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0, pytest-asyncio >=0.23, FastAPI TestClient; Playwright 1.61.1 |
| **Config file** | `backend/pyproject.toml`, `frontend/playwright.config.ts` |
| **Quick run command** | `cd backend && uv run pytest tests/shadow tests/theses tests/forecast -x` |
| **Full suite command** | `cd backend && uv run pytest tests/shadow tests/theses tests/forecast tests/test_phase5_optional_host.py -x && cd ../frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium` |
| **Estimated runtime** | Target <30 seconds per focused backend task; phase gate bounded by focused backend plus one Playwright spec |

The optional real-model smoke is `cd backend && uv run --extra forecast pytest tests/forecast/test_kronos_regression.py -m kronos_model -x`. It runs only with a human-reviewed pinned local Kronos-mini/tokenizer pair and MUST NOT download a checkpoint during the test.

---

## Sampling Rate

- **After every task commit:** Run the task's single-domain `pytest ... -x` command; UI tasks run the Phase 05 Playwright spec.
- **After every plan wave:** Run all three focused backend domain suites; waves containing UI changes also run the desktop Playwright spec.
- **Before `/gsd:verify-work`:** Run default/no-extra, Shadow-only, Forecast-only, and Shadow+Forecast host availability contracts, then the complete Phase 05 focused backend and Playwright acceptance commands.
- **Max feedback latency:** 30 seconds for focused task checks; real-model smoke is isolated from the routine feedback loop.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-W0-01 | 05-02 Task 1 → 05-08 Task 1 | 0 contract / 2 green | SHDW-01 | T-05-02-01..04, T-05-08-01..03 | Immutable bounded import; invalid files create no evidence set | strict RED then unit/integration | `cd backend && uv run python tests/shadow/verify_red_contract.py --group import-evidence`; green owner: `uv run pytest tests/shadow/test_imports.py tests/shadow/test_evidence_sets.py -x` | ✅ exists | ✅ green |
| 05-W0-02 | 05-02 Task 2 → 05-08 Task 2 / 05-11 Task 1 | 0 contract / 2–3 green | SHDW-01 | T-05-02-05..06, T-05-08-04, T-05-11-01..02 | Candidate is allowlisted explainable rules; retention needs frozen non-overlap IS/OOS and no activation | strict RED then integration | `cd backend && uv run python tests/shadow/verify_red_contract.py --group distillation-evaluation`; green owner: `uv run pytest tests/shadow/test_distillation.py tests/shadow/test_evaluation_retention.py -x` | ✅ exists | ✅ green |
| 05-W0-03 | 05-03 Task 1 → 05-09 Task 1 | 0 contract / 2 green | THES-01 | T-05-03-01..03, T-05-09-01..03 | Versions/anchors/conditions append; restricted AST rejects injected fields/operators | strict RED then unit/integration | `cd backend && uv run python tests/theses/verify_red_contract.py --group contracts-versions`; green owner: `uv run pytest tests/theses/test_contracts.py tests/theses/test_versions.py -x` | ✅ exists | ✅ green |
| 05-W0-04 | 05-03 Task 2 → 05-12 Tasks 1–2 | 0 contract / 3 green | THES-01 | T-05-03-04..06, T-05-12-01..04 | Due checks are restart-idempotent; only server-authorized confirmation changes official state | strict RED then integration/API | `cd backend && uv run python tests/theses/verify_red_contract.py --group scheduler-lifecycle`; green owner: `uv run pytest tests/theses/test_scheduler.py tests/theses/test_lifecycle.py -x` | ✅ exists | ✅ green |
| 05-W0-05 | 05-04 Task 1 → 05-10 Task 1 | 0 contract / 2 green | FORE-01 | T-05-04-01..03, T-05-10-01..03 | Catalog rejects moving refs, mismatch, digest/type/root failure, unsafe loading, and foreign scope | strict RED then unit/host | `cd backend && uv run python tests/forecast/verify_red_contract.py --group catalog-input`; green owner: `uv run pytest tests/forecast/test_catalog.py -x` | ✅ exists | ✅ green |
| 05-W0-06 | 05-04 Task 1 → 05-10 Task 1 | 0 contract / 2 green | FORE-01 | T-05-04-03, T-05-10-03 | Only authorized governed daily stock OHLCV and exact 5/20/60 CN-A sessions enter frozen input | strict RED then integration | same catalog-input harness; green owner: `cd backend && uv run pytest tests/forecast/test_input.py -x` | ✅ exists | ✅ green |
| 05-W0-07 | 05-04 Task 2 → 05-10 Task 2 | 0 contract / 2 green | FORE-01 | T-05-04-02/05, T-05-10-02/04 | P10/P50/P90 derive from 32 retained pre-mean paths | strict RED then fixture/unit | `cd backend && uv run python tests/forecast/verify_red_contract.py --group adapter-runner`; green owner: `uv run pytest tests/forecast/test_kronos_adapter.py -x` | ✅ exists | ✅ green |
| 05-W0-08 | 05-04 Task 2 → 05-13 Tasks 1–2 | 0 contract / 3 green | FORE-01 | T-05-04-04..08, T-05-13-01..06 | CAS/idempotency/lease/retry/restart and bounded worker create no partial record | strict RED then integration | same adapter-runner harness; green owner: `cd backend && uv run pytest tests/forecast/test_runner.py -x` | ✅ exists | ✅ green |
| 05-W0-09 | 05-04 Task 3 → 05-14 Task 1 | 0 contract / 4 green | FORE-01 | T-05-04-09, T-05-14-01 | Mature outcomes/calibration append uniquely; retries never rewrite forecast | strict RED then integration | `cd backend && uv run python tests/forecast/verify_red_contract.py --group calibration`; green owner: `cd backend && uv run pytest tests/forecast/test_calibration.py -x` | ✅ exists | ✅ green |
| 05-W0-10 | 05-05 Tasks 1–2 → 05-14 Task 2 / 05-15 / 05-16 / 05-17 | 0 contract / 4–7 green | SHDW-01, THES-01, FORE-01 | T-05-05-01..05, T-05-14-04..05, T-05-17-01..05 | Eight real-host combinations, completed-v1/no-action, and all 13 approved browser scenarios | strict RED then real host/browser | final green commands in Plan 05-17: 177 backend passed, exactly 13 browser scenarios passed | ✅ exists | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `backend/tests/shadow/test_imports.py`, `test_evidence_sets.py`, `test_distillation.py`, `test_evaluation_retention.py`
- [x] `backend/tests/theses/test_contracts.py`, `test_versions.py`, `test_scheduler.py`, `test_lifecycle.py`
- [x] `backend/tests/forecast/test_catalog.py`, `test_input.py`, `test_kronos_adapter.py`, `test_runner.py`, `test_calibration.py`
- [x] `backend/tests/test_phase5_optional_host.py` — optional-module combinations, completed-v1 non-regression, and no-live-execution contract
- [x] `frontend/e2e/phase5-optional-enhancements.spec.ts` — desktop/narrow viewport, immutable history, pending confirmation, quantiles/paths, unavailable modules, and SSE reconnection
- [x] Deterministic fixtures for broker CSV/XLSX imports, duplicate/partial fills, governed OHLCV/calendar Parquet, a fixed sampled tensor, and maturity outcomes
- [x] Human-approved offline Kronos source/checkpoint policy; routine tests must never download models

---

## Sampling Continuity Audit

| Plan/task sequence | Automated sample | Continuity result |
|---|---|---|
| 05-01 Task 1 | blocking human gate; executable approval precondition is first command in 05-07 Tasks 1–3 | gated; no mutation can cross unsampled |
| 05-02 Tasks 1–2, 05-03 Tasks 1–2, 05-04 Tasks 1–3, 05-05 Tasks 1–2 | one strict exact-failure harness per task/group | continuous |
| 05-06 Tasks 1–2 | focused `test_phase5_foundation.py` migration/artifact/optional-identity subsets | continuous |
| 05-07 Tasks 1–3 | separate optional-dependency, vendor-sync, and provisioner suites | continuous |
| 05-08 Tasks 1–2 through 05-14 Tasks 1–2 | each task runs the exact production contract module(s) it makes green | continuous |
| 05-15 Tasks 1–2 and 05-16 Tasks 1–3 | scenario-filtered production Playwright samples after every task | continuous |
| 05-17 Tasks 1–2 | complete focused backend and full 13-scenario browser gates | continuous |

No sequence contains three implementation tasks without an automated sample. No command uses watch mode. Wave 0 strict harnesses reject collection, syntax, fixture, infrastructure, timeout, unexpected-request, changed-node, xpass, or unrelated failures; production owners use ordinary zero-exit pytest/Playwright commands.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pinned Kronos-mini/tokenizer can load and produce the expected regression output on the target CPU runtime | FORE-01 | The optional checkpoint is large, deployment-provisioned, and intentionally absent from routine CI | Install the approved local source and checkpoint catalog without network access, run `uv run --extra forecast pytest tests/forecast/test_kronos_regression.py -m kronos_model -x`, confirm exact checkpoint revisions/digests and bounded runtime output |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or an explicit blocking Wave 0/package gate with downstream executable precondition
- [x] Sampling continuity: no 3 consecutive implementation tasks without automated verify
- [x] Wave 0 covers all planned MISSING test references and maps each to its production green owner
- [x] No watch-mode flags
- [x] Focused task commands target <30s; optional real-model smoke is isolated from routine sampling
- [x] Routine suites make no external model/network requests
- [x] `nyquist_compliant: true` set in frontmatter
- [x] `wave_0_complete: true` after all production owners and final host/browser gates passed

**Approval:** approved — planning review completed 2026-07-15; execution completed 2026-07-16 with 177 backend tests and exactly 13 browser scenarios green.

---

## Gap Closure Validation — Additive Plans 05-18–05-29 (Pending)

This section is additive. The `approved`, `nyquist_compliant`, `wave_0_complete`, and green sign-off above describe the executed 05-01–05-17 baseline only. They are not evidence that the gap-closure plans have executed. Every row below remains **⬜ pending** until its named command is observed on the post-gap revision; only Plan 05-29 may record the integrated result.

| Task ID | Plan | Wave / dependencies | Requirement | Threat refs | Automated command | Status |
|---|---|---|---|---|---|---|
| 05-GC-18-1 | 05-18 Task 1 | 1 / 05-17 | SHDW-01 | T-05-18-01..05 | `pytest tests/shadow/test_distillation.py -k "bounded_assumption_schema or assumption_byte_ceiling or direct_boundary_rejects_oversize" -x`; production host test; Shadow production Playwright scenario | ⬜ pending |
| 05-GC-19-1 | 05-19 Task 1 | 2 / 05-18 | SHDW-01 | T-05-19-01..02 | `pytest tests/shadow/test_distillation.py::test_candidate_replay_digest_covers_all_identity_defining_content tests/shadow/test_evaluation_retention.py::test_retention_replay_requires_exact_principal_and_rationale -x` | ⬜ pending |
| 05-GC-19-2 | 05-19 Task 2 | 2 / 05-18 | SHDW-01 | T-05-19-03..04 | `pytest tests/shadow/test_evaluation_retention.py -k "paired_operation or interrupted_attempt or parallel_pair" -x` | ⬜ pending |
| 05-GC-20-1 | 05-20 Task 1 | 3 / 05-19 | SHDW-01 | T-05-20-01 | import preview-identity pytest plus `--grep "Shadow preview identity"` Playwright | ⬜ pending |
| 05-GC-20-2 | 05-20 Task 2 | 3 / 05-19 | SHDW-01 | T-05-20-02..04 | principal-lineage and aggregate-member/repository-pagination pytest | ⬜ pending |
| 05-GC-20-3 | 05-20 Task 3 | 3 / 05-19 | SHDW-01 | T-05-20-05..06 | cleanup fault-injection pytest plus `--grep "Shadow retention dialog validates rationale and contains errors"` | ⬜ pending |
| 05-GC-21-1 | 05-21 Task 1 | 2 / 05-18 | THES-01 | T-05-21-01..04 | lifecycle strict/timezone/pending/history pytest plus Thesis API versions/checks/pending/history/ownership pagination pytest | ⬜ pending |
| 05-GC-21-2 | 05-21 Task 2 | 2 / 05-18 | THES-01 | T-05-21-04..05 | scheduler poison/reader/readiness pytest plus production Thesis host test | ⬜ pending |
| 05-GC-22-1 | 05-22 Task 1 | 3 / 05-21 | FORE-01 | T-05-22-01/05 | production Forecast host completion/independence and service-revalidation pytest | ⬜ pending |
| 05-GC-22-2 | 05-22 Task 2 | 3 / 05-21 | FORE-01 | T-05-22-02..04 | input frame/artifact/calendar/amount and immutable commit/path containment pytest | ⬜ pending |
| 05-GC-25-1 | 05-25 Task 1 | 4 / 05-19, 05-22 | SHDW-01, THES-01, FORE-01 | T-05-25-01 | `pytest tests/test_operational_migrations.py -k "atomic_version_and_user_version or restart_after_mid_script_failure" -x` | ⬜ pending |
| 05-GC-25-2 | 05-25 Task 2 | 4 / 05-19, 05-22 | SHDW-01, THES-01, FORE-01 | T-05-25-02..05 | trusted/hostile Origin/Host, readiness, eight-combination, no-action host pytest | ⬜ pending |
| 05-GC-23-1 | 05-23 Task 1 | 5 / 05-22, 05-25 | FORE-01 | T-05-23-01 | Forecast API distinct-path/corrupt-relation/path-quantile consistency pytest | ⬜ pending |
| 05-GC-23-2 | 05-23 Task 2 | 5 / 05-22, 05-25 | FORE-01 | T-05-23-02..04 | maturity-cursor migration rollback/upgrade, calibration cursor/restart/repair/parallel, record-scoped API pytest | ⬜ pending |
| 05-GC-23-3 | 05-23 Task 3 | 5 / 05-22, 05-25 | FORE-01 | T-05-23-05 | Forecast API persisted event ID, Last-Event-ID resume, subscription limit, and slow-consumer cleanup pytest | ⬜ pending |
| 05-GC-24-1 | 05-24 Task 1 | 6 / 05-20, 05-21, 05-23 | SHDW-01, THES-01, FORE-01 | T-05-24-01/03/06 | `--grep "rapid stock switch keeps Phase 05 object authority local|StockAnalysis narrow dialog focus contract"` Playwright | ⬜ pending |
| 05-GC-24-2 | 05-24 Task 2 | 6 / 05-20, 05-21, 05-23 | THES-01, FORE-01 | T-05-24-02/04/05 | complete page/retry, Thesis pagination/validation, Forecast persisted SSE/flapping Playwright | ⬜ pending |
| 05-GC-28-1 | 05-28 Task 1 | 1 / 05-17 | FORE-01 | T-05-28-01..03 | blocking human gate; 05-26 automated precondition rejects incomplete approval | ⬜ pending / blocking-human |
| 05-GC-26-1 | 05-26 Task 1 | 2 / 05-28 | FORE-01 | T-05-26-01 | approved-summary/config/Torch provisioner tests, optional-dependency pin/isolation tests, `uv lock --check` | ⬜ pending |
| 05-GC-26-2 | 05-26 Task 2 | 2 / 05-28 | FORE-01 | T-05-26-02..04 | parallel catalog/CAS/shared rollback/crash provisioner pytest | ⬜ pending |
| 05-GC-27-1 | 05-27 Task 1 | 3 / 05-26 | FORE-01 | T-05-27-01..02 | source/config tamper and verified import-origin catalog/adapter pytest | ⬜ pending |
| 05-GC-27-2 | 05-27 Task 2 | 3 / 05-26 | FORE-01 | T-05-27-03..05 | pre-allocation output cap, byte IPC, ready race, fallback and descendant cleanup pytest | ⬜ pending |
| 05-GC-29-1 | 05-29 Task 1 | 7 / terminal backend plans | all | T-05-29-01..03 | complete focused Phase 05 backend/domain/migration/artifact/dependency/vendor/provisioner/host command with `ATHENA_ALLOW_NETWORK=0` | ⬜ pending / final gate |
| 05-GC-29-2 | 05-29 Task 2 | 7 / terminal UI/runtime plans | all | T-05-29-01..03 | full unfiltered Phase 05 desktop-chromium Playwright spec with `ATHENA_ALLOW_NETWORK=0` | ⬜ pending / final gate |

### Gap Closure Sampling Continuity

| Wave | Required sample before advancing | Current state |
|---|---|---|
| 1 | 05-18 bounded production Shadow tracer and explicit 05-28 human supply decision | pending |
| 2 | 05-19 replay/pair, 05-21 Thesis API/readiness, and 05-26 approved supply/pin/provisioning checks | pending |
| 3 | 05-20 import/cleanup/dialog, 05-22 production Forecast, and 05-27 runtime-byte/process checks | pending |
| 4 | 05-25 atomic migration and trusted host/readiness/no-action checks | pending |
| 5 | 05-23 cursor migration, path/quantile, calibration, and SSE checks | pending |
| 6 | 05-24 complete browser object/paging/narrow/dialog/SSE scenarios | pending |
| 7 | 05-29 complete focused backend plus full unfiltered Phase 05 browser gate | pending |

### Gap Closure Sign-Off

- [ ] Every 05-GC row has an observed zero exit or an explicit approved blocking-human record.
- [ ] The 05-28 summary contains all five config identities and exact PyTorch CPU build/index/wheel hash; 05-26 proves the precondition and exact lock.
- [ ] 05-29 backend acceptance has no required failure/unexpected skip, external request, live-action call, or temporary artifact residue.
- [ ] 05-29 browser acceptance runs every currently discovered Phase 05 scenario without grep filtering and reports zero unexpected external/action requests.
- [ ] Only after these checks may gap-closure evidence be called green; the historical 05-01–05-17 sign-off remains unchanged.
