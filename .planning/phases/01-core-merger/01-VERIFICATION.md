---
phase: 01-core-merger
verified: 2026-07-11
status: gaps
verification_ref: f8b49cf
---

# Phase 01 Verification

## Status: gaps

Phase 01 is **not complete**. Commit `f8b49cf` resolves the former unavailable-mirror provenance: `backend/uv.lock` now contains only the public `pypi.org` registry and `files.pythonhosted.org` artifacts, with no Tsinghua reference. In a detached clean worktree at `f8b49cf`, cold `bash compose/phase1/prepare-images.sh` built all three local images and passed the network-disabled verifier smoke. The required follow-on fixture-only `bash compose/phase1/run.sh` nevertheless fails: Compose supplies `PHASE1_FIXTURE_MODE="true"`, while the committed application accepts only the literal value `"1"`. The app exits during startup before the verifier can exercise the acceptance workflow. This concrete committed configuration/guard mismatch blocks CORE-06.

## Scope and evidence basis

Reviewed all 15 Phase 01 plans and their 15 summaries, the requirement mapping, prior verifier reports and repair commits (`2684b96`, `5ac6435`), and the committed source in a detached clean worktree at `f8b49cf`. Unrelated primary-worktree changes were excluded.

| Evidence | Result |
| --- | --- |
| Lock-host audit of `backend/uv.lock` at `f8b49cf` | **Passed**: the complete URL host set is exactly `pypi.org` and `files.pythonhosted.org`; case-insensitive search found no `tsinghua` or `tuna` reference. |
| `QK.alerts` and `compose/phase1.test.yml` at `f8b49cf` | **Passed**: the query key includes source, severity, and delivery; `ports: !override` leaves only `127.0.0.1:13018:3018`. |
| `bash compose/phase1/prepare-images.sh` in the clean `f8b49cf` worktree | **Passed**: application, receiver, and verifier images built; the no-network verifier check reported `phase1 verifier smoke passed`. |
| `bash compose/phase1/run.sh` immediately after preparation | **Failed**: app startup raises `RuntimeError: D-13 fixture mode requires PHASE1_FIXTURE_MODE=1`; Compose configured `PHASE1_FIXTURE_MODE="true"` for app and verifier, so the app exits with code 3 and the runner returns code 137 after cleanup. |
| Prior clean verification at `2684b96` / `5ac6435` | **Passed except for the then-lock blocker**: frontend Docker build completed, resolved Compose was loopback-only, static-image smoke and fixture acceptance passed, and the focused Phase 01 suite reported 37 passed (three existing Polars warnings). The lock-only `f8b49cf` change preserves those repaired frontend and port bindings. |

## Repair assessment

1. **Mirror provenance: closed.** The committed lock no longer directs `uv` to the unavailable Tsinghua mirror; fresh image preparation completed successfully.
2. **Query-key repair: remains closed.** `QK.alerts(source?, severity?, delivery?)` distinguishes all three filters; the prior clean Docker frontend build passed.
3. **Loopback-port repair: remains closed.** The fixture override replaces the inherited port list and retains only `127.0.0.1:13018:3018`.
4. **Fixture acceptance: open.** The test Compose file sets `PHASE1_FIXTURE_MODE="true"`, but `fixture_provider_enabled()` requires `os.environ.get("PHASE1_FIXTURE_MODE") == "1"`. The cold runner cannot reach health, fixture synchronization, API/SSE, receiver, or Playwright checks.

## Requirement traceability

| Requirement | Plans | Status | Concrete committed evidence |
| --- | --- | --- |
| CORE-01 | 01, 02, 11 | passed | Two-file governed fixture bundle, `FixtureProvider`, `run_phase1_fixture_sync`, and focused sync coverage passed before the lock-only commit. |
| CORE-02 | 01, 02, 11 | passed | Contract validator covers key, time, repair-window, and schema-drift failures; focused contract coverage passed. |
| CORE-03 | 03, 08, 09, 11, 13 | passed | SQLite portfolio API/service and typed client are exercised by focused portfolio coverage and the prior fixture acceptance. |
| CORE-04 | 05, 08, 10, 11, 12, 13 | passed | Persisted monitor events and sanitized delivery outcomes are covered by focused tests and prior fixture acceptance. |
| CORE-05 | 08, 09, 11, 12, 13 | passed | Named intraday SSE alert/portfolio events and independent subscriber behavior are covered by focused tests and prior fixture acceptance. |
| CORE-06 | 06, 07, 11 | **gap** | Public-lock cold preparation and no-network smoke now pass, but the mandatory fixture-only runner fails at the `"true"` versus `"1"` fixture-mode boundary. |
| CORE-07 | 11 | passed | `docs/UPSTREAM-SYNC.md` provides source identity, owner, preserved boundary, regressions, and review/update workflow. |
| PLAN-01 | 04, 08, 10, 14 | passed | Deterministic governed-data baseline persistence/API passes focused playbook coverage. |
| PLAN-02 | 08, 10, 14, 15 | passed | Provenance, bounded audit, unavailable fallback, and AI-free replay pass focused adjustment/review/replay coverage. |

## Required next step

Make the Phase 1 Compose fixture-mode value and `fixture_provider_enabled()` contract agree (use `"1"` in the fixture Compose environment or intentionally accept the configured boolean form). Then, from a clean committed worktree, rerun `bash compose/phase1/prepare-images.sh` followed by `bash compose/phase1/run.sh`; change CORE-06 and the phase status to `passed` only after the fixture-only acceptance exits successfully.

## Human verification

No additional human approval blocks this result: the Plan 06 record approves only `@playwright/test@1.61.1`. The remaining blocker is the automated fixture-mode mismatch.
