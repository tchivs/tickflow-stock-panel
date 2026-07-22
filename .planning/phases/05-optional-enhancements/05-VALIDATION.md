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

## Gap Closure Validation — Additive Plans 05-18–05-41 (Pending)

This section is additive. The `approved`, `nyquist_compliant`, `wave_0_complete`, and green sign-off above describe the executed 05-01–05-17 baseline only. They are not evidence that the gap-closure plans have executed. Every row below remains **⬜ pending** until its named command or blocking-human decision is observed on the post-gap revision; only Plan 05-29 may record the integrated machine-report verdict.

### Per-Task Gap Closure Map

| Task ID | Plan | Wave / dependencies | Requirement | Threat refs | Exact automated command | Status |
|---|---|---|---|---|---|---|
| 05-GC-30-1 | 05-30 Task 1 | 1 / 05-17 | SHDW-01 | T-05-30-01..04 | bounded schema/depth/key/list/string/byte and direct-boundary Shadow pytest from 05-30 | ⬜ pending |
| 05-GC-28-1 | 05-28 Task 1 | 1 / 05-17 | FORE-01 | T-05-28-01..03 | canonical historical human-action record; `05-28-SUMMARY.md` remains byte-for-byte `approval: rejected`, `gate_status: blocked` and links only to 05-40 | ✅ complete / immutable rejected history |
| 05-GC-18-1 | 05-18 Task 1 | 2 / 05-17, 05-30 | SHDW-01 | T-05-18-01..04 | production Shadow host node and `--grep "Shadow production distillation contract"` Playwright from 05-18 | ✅ green |
| 05-GC-40-1 | 05-40 Task 1 | 2 / 05-28 | FORE-01 | T-05-40-01..04 | canonical blocking-human action; validate exactly six named rows, every required field, positive lengths, 64-character lowercase hashes, per-row/overall approvals, independent author/UTC time, no-executor attestation, and unchanged 05-28 checksum; any defect writes rejected/blocked | ⬜ pending / blocking-human |
| 05-GC-19-1 | 05-19 Task 1 | 3 / 05-18 | SHDW-01 | T-05-19-01..02 | candidate replay-digest and exact principal/rationale retention pytest from 05-19 | ✅ green |
| 05-GC-19-2 | 05-19 Task 2 | 3 / 05-18 | SHDW-01 | T-05-19-03..04 | paired operation, interrupted attempt, and parallel pair pytest from 05-19 | ✅ green |
| 05-GC-21-1 | 05-21 Task 1 | 3 / 05-18 | THES-01 | T-05-21-01..04 | lifecycle strict/timezone/pending/history pytest plus API ownership pagination pytest from 05-21 | ✅ green |
| 05-GC-26-1 | 05-26 Task 1 | 3 / 05-40 | FORE-01 | T-05-26-01 | `cd backend && uv run pytest tests/test_kronos_provisioner.py -k "approved_supply_summary_required or config_digest or exact_two_file_identity or torch_cpu_artifact_identity or verify_only_offline" -x && uv run pytest tests/test_phase5_optional_dependencies.py -k "forecast_torch_exact_pin or base_extra_independent" -x && uv lock --check` | ⬜ pending; rejects 05-28-only/partial/non-human approval |
| 05-GC-26-2 | 05-26 Task 2 | 3 / 05-40 | FORE-01 | T-05-26-02..04 | `cd backend && uv run pytest tests/test_kronos_provisioner.py -k "parallel_catalog_merge or publication_cas or shared_asset_rollback or crash_after_promotion" -x` | ⬜ pending |
| 05-GC-20-1 | 05-20 Task 1 | 4 / 05-19 | SHDW-01 | T-05-20-01 | import preview-identity pytest plus `--grep "Shadow preview identity"` Playwright from 05-20 | ✅ green |
| 05-GC-20-2 | 05-20 Task 2 | 4 / 05-19 | SHDW-01 | T-05-20-02..04 | principal-lineage and aggregate-member/repository-pagination pytest from 05-20 | ✅ green |
| 05-GC-32-1 | 05-32 Task 1 | 4 / 05-21 | THES-01 | T-05-32-01..04 | scheduler poison/reader/readiness pytest plus production Thesis host node from 05-32 | ✅ green |
| 05-GC-22-1 | 05-22 Task 1 | 5 / 05-21, 05-32 | FORE-01 | T-05-22-01/05 | standalone production Forecast host node, then `test_runner.py -k production_service_revalidation` from 05-22 | ✅ green |
| 05-GC-22-2 | 05-22 Task 2 | 5 / 05-21, 05-32 | FORE-01 | T-05-22-02..04 | input frame/artifact/calendar/amount and immutable commit/path containment pytest from 05-22 | ✅ green |
| 05-GC-31-1 | 05-31 Task 1 | 5 / 05-20 | SHDW-01 | T-05-31-01..03 | cleanup fault-injection pytest plus `--grep "Shadow retention dialog validates rationale and contains errors"` from 05-31 | ✅ green |
| 05-GC-25-1 | 05-25 Task 1 | 6 / 05-19, 05-22, 05-32 | all | T-05-25-01 | atomic migration rollback/restart pytest from 05-25 | ✅ green |
| 05-GC-25-2 | 05-25 Task 2 | 6 / 05-19, 05-22, 05-32 | all | T-05-25-02..05 | trusted/hostile Origin/Host, readiness, eight-combination, no-action host pytest from 05-25 | ✅ green |
| 05-GC-27-1 | 05-27 Task 1 | 6 / 05-22, 05-26 | FORE-01 | T-05-27-01..02 | `cd backend && uv run pytest tests/forecast/test_catalog.py -k "vendored_byte_manifest or config_digest or source_tamper" -x && uv run pytest tests/forecast/test_kronos_adapter.py -k "verified_source_directory or import_shadow_rejected or child_revalidates_bytes" -x` | ⬜ pending |
| 05-GC-27-2 | 05-27 Task 2 | 6 / 05-22, 05-26 | FORE-01 | T-05-27-03..05 | `cd backend && uv run pytest tests/forecast/test_runner.py -k "output_cap_before_allocation or byte_ipc or child_ready_handshake or startup_race or terminate_kill_fallback or descendants_reaped" -x` | ⬜ pending |
| 05-GC-23-1 | 05-23 Task 1 | 7 / 05-22, 05-25 | FORE-01 | T-05-23-01 | Forecast distinct-path/corrupt-relation/path-quantile consistency pytest from 05-23 | ✅ green |
| 05-GC-23-2 | 05-23 Task 2 | 7 / 05-22, 05-25 | FORE-01 | T-05-23-02..04 | maturity-cursor migration/calibration cursor/restart/repair/parallel/API pytest from 05-23 | ✅ green |
| 05-GC-23-3 | 05-23 Task 3 | 7 / 05-22, 05-25 | FORE-01 | T-05-23-05 | persisted event ID, Last-Event-ID resume, subscription limit, slow-consumer cleanup pytest from 05-23 | ✅ green |
| 05-GC-24-1 | 05-24 Task 1 | 8 / 05-20, 05-21, 05-23, 05-31 | all | T-05-24-01/03/06 | rapid stock switch and StockAnalysis narrow dialog Playwright from 05-24 | ✅ green |
| 05-GC-24-2 | 05-24 Task 2 | 8 / 05-20, 05-21, 05-23, 05-31 | THES-01, FORE-01 | T-05-24-02/04/05 | complete page/retry, Thesis pagination/validation, Forecast persisted SSE/flapping Playwright from 05-24 | ✅ green |
| 05-GC-34-1 | 05-34 Task 1 | 8 / 05-23, 05-25 | FORE-01 / CR-02 | T-05-34-01..02 | `cd backend && uv run pytest tests/test_operational_migrations.py -k "forecast_quantile or quantile_migration" -x && uv run pytest tests/forecast/test_runner.py -k "quantile_bundle_commit or quantile_artifact or strict_commit" -x` | ⬜ pending |
| 05-GC-34-2 | 05-34 Task 2 | 8 / 05-23, 05-25 | FORE-01 / CR-02 | T-05-34-02..03 | `cd backend && uv run pytest tests/forecast/test_calibration.py::test_cr02_projection_and_calibration_use_same_verified_parquet_bytes -x && uv run pytest tests/forecast/test_calibration.py -k "production_committed_quantiles or calibration_computes or immutable or parallel" -x` | ⬜ pending |
| 05-GC-33-1 | 05-33 Task 1 | 9 / 05-20, 05-24 | SHDW-01 / CR-01 | T-05-33-01..03 | `cd backend && uv run pytest tests/shadow/test_evidence_sets.py -k "server_resolved_membership or exclusion or member_limit or foreign" -x && uv run pytest tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory -x` | ⬜ pending |
| 05-GC-33-2 | 05-33 Task 2 | 9 / 05-20, 05-24 | SHDW-01 / CR-01 | T-05-33-01/03 | `cd frontend && ATHENA_ALLOW_NETWORK=0 pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "SHDW-01|Shadow"` | ⬜ pending |
| 05-GC-41-1 | 05-41 Task 1 | 10 / 05-33 | SHDW-01 / CR-01 | T-05-41-01..04 | `cd frontend && ATHENA_ALLOW_NETWORK=0 pnpm exec playwright test --config=playwright.phase5-real-host.config.ts e2e/phase5-shadow-real-host.spec.ts --project=phase5-shadow-real-host --grep "CR-01 real host non-empty Shadow import to evidence distillation and IS-OOS$"` | ⬜ pending / required real-host |
| 05-GC-37-1 | 05-37 Task 1 | 9 / 05-23, 05-25, 05-34 | FORE-01 / CR-03 | T-05-37-01..03 | `cd backend && uv run pytest tests/forecast/test_api.py -k "principal_owner or cross_principal or owned_page or last_event_id" -x` | ⬜ pending |
| 05-GC-35-1 | 05-35 Task 1 | 10 / 05-24, 05-33, 05-34 | FORE-01 / CR-04 | T-05-35-01..03 | `cd frontend && ATHENA_ALLOW_NETWORK=0 pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "CR-04 calibration outcome identity renders 5 20 60 and fails closed$" && ATHENA_ALLOW_NETWORK=0 pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "FORE-01 概率结果|校准身份"` | ⬜ pending |
| 05-GC-38-1 | 05-38 Task 1 | 10 / 05-22, 05-31, 05-37 | FORE-01 / CR-05, WR-01 | T-05-38-01..02/04 | `cd backend && uv run pytest tests/forecast/test_runner.py::test_cr05_final_input_revalidation_precedes_commit_and_commit_spy_zero tests/forecast/test_runner.py::test_wr01_operation_first_replay_race_leaves_no_orphan -x && uv run pytest tests/forecast/test_input.py -k "read_only_handle or post_worker_revalidation or fingerprint" -x && uv run pytest tests/forecast/test_runner.py -k "idempotent_input_namespace or orphan_cleanup or worker_input_tamper or pre_commit_input" -x` | ⬜ pending; commit spy must be zero on failure |
| 05-GC-38-2 | 05-38 Task 2 | 10 / 05-22, 05-31, 05-37 | FORE-01 / WR-02 | T-05-38-03..04 | `cd backend && uv run pytest tests/test_phase5_foundation.py -k "parquet_same_open or toctou or unbound_discard or artifact_metadata" -x` | ⬜ pending |
| 05-GC-36-1 | 05-36 Task 1 | 11 / 05-21, 05-32, 05-35 | THES-01 / WR-03 | T-05-36-01 | `cd backend && uv run pytest tests/theses/test_api.py -k "ledger_row_identity or old_version or ownership_before_pagination" -x` | ⬜ pending |
| 05-GC-36-2 | 05-36 Task 2 | 11 / 05-21, 05-32, 05-35 | THES-01 / WR-03 | T-05-36-02..03 | `cd frontend && ATHENA_ALLOW_NETWORK=0 pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "paged Thesis history"` | ⬜ pending |
| 05-GC-39-1 | 05-39 Task 1 | 11 / 05-27, 05-37, 05-38 | FORE-01 / CR-07 | T-05-39-01..02/04 | `cd backend && uv run pytest tests/test_phase5_optional_host.py::test_cr07_real_host_queued_restart_executes_once -x && uv run pytest tests/forecast/test_runner.py -k "restart_dispatches_queued or concurrent_recovery_one_winner or restart_terminalizes" -x && uv run pytest tests/test_phase5_optional_host.py -k "forecast_queued_restart_executes or forecast_recovery_failure_is_local" -x` | ⬜ pending |
| 05-GC-39-2 | 05-39 Task 2 | 11 / 05-27, 05-37, 05-38 | FORE-01 / CR-06 | T-05-39-03..04 | `cd backend && uv run pytest tests/forecast/test_runner.py::test_cr06_normal_leader_exit_reaps_process_group_before_commit -x && uv run pytest tests/forecast/test_runner.py -k "normal_exit_descendants_reaped or every_return_reaps_group or child_ready_handshake or descendants_reaped" -x` | ⬜ pending |
| 05-GC-29-1 | 05-29 Task 1 | 12 / every terminal gap plan through 05-41 | all | T-05-29-01..04 | `mkdir -p /tmp/athena-phase5-29 && cd backend && uv run pytest tests/test_phase5_final_gate.py -x && ATHENA_ALLOW_NETWORK=0 uv run pytest tests/shadow tests/theses tests/forecast tests/test_operational_migrations.py tests/test_phase5_foundation.py tests/test_phase5_optional_dependencies.py tests/test_kronos_vendor_sync.py tests/test_kronos_provisioner.py tests/test_phase5_optional_host.py --deselect=tests/forecast/test_kronos_regression.py::test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance -o xfail_strict=true --junitxml=/tmp/athena-phase5-29/pytest.xml -x` | ⬜ pending / final gate |
| 05-GC-29-2 | 05-29 Task 2 | 12 / 05-29 Task 1 | all | T-05-29-01..04 | `cd frontend && ATHENA_ALLOW_NETWORK=0 PLAYWRIGHT_JSON_OUTPUT_NAME=/tmp/athena-phase5-29/playwright.json pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --reporter=json && ATHENA_ALLOW_NETWORK=0 PLAYWRIGHT_JSON_OUTPUT_NAME=/tmp/athena-phase5-29/playwright-real-host.json pnpm exec playwright test --config=playwright.phase5-real-host.config.ts e2e/phase5-shadow-real-host.spec.ts --project=phase5-shadow-real-host --reporter=json && cd ../backend && uv run python scripts/verify_phase5_final_gate.py --pytest-junit /tmp/athena-phase5-29/pytest.xml --playwright-json /tmp/athena-phase5-29/playwright.json --playwright-json /tmp/athena-phase5-29/playwright-real-host.json --allow-absent backend/tests/forecast/test_kronos_regression.py::test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance` | ⬜ pending / fail-on-skip final gate |

### CR / WR One-to-One Machine-Report Manifest

The final verifier MUST normalize all JUnit and Playwright nodes and require each selector below to match exactly one discovered, passed node. Zero matches, more than one match, a node assigned to two findings, duplicate normalized IDs, or any non-passed status exits nonzero.

| Finding | Exact primary report node/title | Owning plan | Required report |
|---|---|---|---|
| CR-01 | `frontend/e2e/phase5-shadow-real-host.spec.ts::CR-01 real host non-empty Shadow import to evidence distillation and IS-OOS` | 05-41 Task 1 | real-host Playwright JSON |
| CR-02 | `backend/tests/forecast/test_calibration.py::test_cr02_projection_and_calibration_use_same_verified_parquet_bytes` | 05-34 Task 2 | pytest JUnit |
| CR-03 | `backend/tests/forecast/test_api.py::test_cr03_same_instrument_cross_principal_matrix_denies_every_surface` | 05-37 Task 1 | pytest JUnit |
| CR-04 | `frontend/e2e/phase5-optional-enhancements.spec.ts::CR-04 calibration outcome identity renders 5 20 60 and fails closed` | 05-35 Task 1 | fixture Playwright JSON |
| CR-05 | `backend/tests/forecast/test_runner.py::test_cr05_final_input_revalidation_precedes_commit_and_commit_spy_zero` | 05-38 Task 1 | pytest JUnit |
| CR-06 | `backend/tests/forecast/test_runner.py::test_cr06_normal_leader_exit_reaps_process_group_before_commit` | 05-39 Task 2 | pytest JUnit |
| CR-07 | `backend/tests/test_phase5_optional_host.py::test_cr07_real_host_queued_restart_executes_once` | 05-39 Task 1 | pytest JUnit |
| WR-01 | `backend/tests/forecast/test_runner.py::test_wr01_operation_first_replay_race_leaves_no_orphan` | 05-38 Task 1 | pytest JUnit |
| WR-02 | `backend/tests/test_phase5_foundation.py::test_wr02_parquet_same_open_rejects_toctou` | 05-38 Task 2 | pytest JUnit |
| WR-03 | `frontend/e2e/phase5-optional-enhancements.spec.ts::WR-03 paged Thesis history renders before version page` | 05-36 Task 2 | fixture Playwright JSON |

The sole absent allowlist entry is `backend/tests/forecast/test_kronos_regression.py::test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance`. It is the explicitly optional real-model smoke, is exactly deselected from routine collection, and may be absent only; if collected and skipped/xfail/xpass it fails like every other node.

### Real-Host Browser Contract

| Harness | Config | Spec | Required behavior | Forbidden behavior | Status |
|---|---|---|---|---|---|
| `backend/tests/phase5_real_host_harness.py` | `frontend/playwright.phase5-real-host.config.ts` | `frontend/e2e/phase5-shadow-real-host.spec.ts` | real browser uploads a non-empty log and crosses production `/api/shadow/**` through evidence, distillation, IS, and OOS; repository-ID bypass and all live-action counters are zero | no `page.route`, `browserContext.route`, fulfillment, or other interception for `/api/shadow/**`; no `app.state.shadow_repository` request construction | ⬜ pending |

### Supply Approval Continuity

| Record | Disposition | Permitted downstream use | Required check |
|---|---|---|---|
| `05-28-SUMMARY.md` | immutable `approval: rejected`, `gate_status: blocked` | history/context only; never an identity source | must remain unchanged |
| `05-40-SUMMARY.md` | pending append-only blocking-human retry | sole identity authority for 05-26/29 only when independently human-authored, all six rows complete, every row approved, `approval: approved`, `gate_status: unblocked` | reject missing/blank/inferred/fetched/executor-selected/self-approved config or PyTorch fields |

### Gap Closure Sampling Continuity

| Wave | Required sample before advancing | Current state |
|---|---|---|
| 1 | 05-30 bounded assumption boundary plus preserved 05-28 rejected decision | 05-30 green; 05-28 rejected history retained |
| 2 | 05-18 production Shadow tracer plus independent append-only 05-40 human decision | 05-18 green; 05-40 pending/blocking |
| 3 | 05-19 replay/pair, 05-21 resolver/API pagination, and 05-26 approved supply/pin/provisioning checks | 05-19/21 green; 05-26 blocked on 05-40 |
| 4 | 05-20 preview/history and 05-32 governed Thesis reader/scanner/readiness checks | green |
| 5 | 05-22 production Forecast and 05-31 cleanup/dialog checks | green |
| 6 | 05-25 atomic migration/host and 05-27 runtime-byte/process checks | 05-25 green; 05-27 pending |
| 7 | 05-23 cursor migration, path/quantile, calibration, and SSE checks | green |
| 8 | 05-24 browser object/paging/narrow/dialog/SSE plus 05-34 immutable quantile Parquet/metadata checks | 05-24 green; 05-34 pending |
| 9 | 05-33 strict Shadow production/fixture contracts and 05-37 complete ownership matrix | pending |
| 10 | 05-35 exact calibration identity, 05-38 final input/orphan/same-open contracts, and 05-41 exact real-host CR-01 flow | pending |
| 11 | 05-36 self-identifying Thesis ledger and 05-39 queued recovery/whole-PGID reap | pending |
| 12 | 05-29 pytest JUnit + fixture Playwright JSON + real-host Playwright JSON parsed by fail-on-skip verifier | pending / unique final wave |

No wave advances across an unobserved required sample. The graph is acyclic: `05-28 → 05-40 → 05-26 → 05-27 → 05-39 → 05-29`; `05-34 → 05-37 → 05-38 → 05-39 → 05-29`; `05-33 → 05-41 → 05-29`; `05-33/34 → 05-35 → 05-36 → 05-29`. Plan 05-29 is the sole and final Wave 12 gate.

### Multi-Source Coverage Audit

| Source | ID / constraint | Required outcome | Plan coverage | Status |
|---|---|---|---|---|
| GOAL | Phase 05 goal | Optional strategy distillation, thesis evidence, and forecast capabilities do not change completed v1 | 05-18..41; final 05-29 | COVERED |
| REQ | SHDW-01 | derive/evaluate strategy from actual trading logs | 05-18..20, 24, 30, 31, 33, 41; final 05-29 | COVERED |
| REQ | THES-01 | versioned thesis, anchors, invalidation, periodic evidence | 05-21, 24, 32, 36; final 05-29 | COVERED |
| REQ | FORE-01 | request Kronos forecast with quantiles, paths, checkpoint | 05-22..29, 34, 35, 37..40; final 05-29 | COVERED |
| CONTEXT | D-01..D-04 | local immutable Shadow imports; explainable candidate; frozen IS/OOS; no activation | 05-18..20, 30, 31, 33 and CR-01 real-host node | COVERED |
| CONTEXT | D-05..D-08 | immutable Thesis versions, bounded anchor/conditions, human confirmation, per-condition cadence | 05-21, 24, 32, 36 and WR-03 node | COVERED |
| CONTEXT | D-09..D-12 | object-bound governed input, visible P10/P50/P90 plus paths, approved local checkpoint, immutable records/append calibration/no actions | 05-22..29, 34, 35, 37..40 and CR/WR manifest | COVERED |
| RESEARCH | Architectural Responsibility Map | paths/quantiles stay immutable Parquet; SQLite stores bounded descriptor/provenance/digest metadata | 05-34 Tasks 1–2; CR-02 node | COVERED |
| RESEARCH | strict DTO / minimal browser authority | browser sends bounded selectors; server owns principal, membership, fingerprints, outcomes | 05-33/35/36/37/41; CR-01/03/04 and WR-03 nodes | COVERED |
| RESEARCH | local checkpoint / no runtime network | exact human-approved identities, local-only loading, full byte/import binding | immutable 05-28 history; 05-40→05-26→05-27; final 05-29 | COVERED |
| RESEARCH | bounded worker / immutable managed artifacts | pre-allocation IPC caps, whole-PGID cleanup, same-open decode, final input identity | 05-27, 38, 39; CR-05/06/07 and WR-01/02 nodes | COVERED |
| RESEARCH | single optional host/storage topology | independent modules, one operational.db/lake/container, no queue/database/container expansion | 05-25, 29, 33, 39, 41 | COVERED |
| CONTEXT | Deferred ideas | None | no exclusion needed | COVERED |

**Source audit result:** all GOAL, REQ, RESEARCH, and CONTEXT items are covered; no source item is missing and no deferred item was introduced.

### Gap Closure Sign-Off

- [ ] Every 05-GC row has an observed zero exit or an explicit human decision; the 05-28 rejected record remains unchanged and cannot satisfy 05-40.
- [ ] `05-40-SUMMARY.md` is a separate append-only independently human-authored record with complete approved five-config and exact PyTorch CPU version/build/index/wheel/tags/length/full-hash/license/source/base-extra-isolation fields; otherwise 05-26 and all descendants remain blocked.
- [ ] Every CR-01..CR-07 and WR-01..WR-03 manifest selector matches exactly one discovered passed machine-report node; no normalized node is absent, duplicated, or assigned twice.
- [ ] The named real-host browser row runs without `/api/shadow/**` interception or repository-ID bypass and reports zero live actions/unexpected external requests.
- [ ] 05-29's pytest uses `xfail_strict=true`, excludes only the exact optional real-model smoke, and writes JUnit; both Playwright runs write JSON.
- [ ] `verify_phase5_final_gate.py` exits nonzero for missing/malformed reports, any skip/xfail/xpass/retry/flaky/failure/error, zero/missing/duplicate CR/WR nodes, duplicate normalized IDs, or discovered != passed.
- [ ] 05-29 depends directly or transitively on every terminal plan through 05-41 and remains the unique Wave 12 final gate.
- [ ] The four-source audit has no MISSING row; immutable Parquet/SQLite metadata, no-authority, single-topology, and completed-v1 boundaries remain intact.

**Gap-closure approval:** pending — only the observed approved 05-40 human record plus a zero-exit 05-29 machine-report verifier may turn this additive section green. Historical 05-01–05-17 and rejected 05-28 evidence remain unchanged.
