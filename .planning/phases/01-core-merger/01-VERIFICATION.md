---
phase: 01-core-merger
verified: 2026-07-11
status: gaps
verification_ref: 2684b96
---

# Phase 01 Verification

## Status: gaps

Commit `2684b96` closes both previously documented defects: the `QK.alerts` cache key now accepts and distinguishes source, severity, and delivery filters, and the fixture Compose override replaces the inherited port list. The committed frontend builds, the network-disabled verifier smoke passes, and the fixture-only Compose acceptance passes. Phase 01 nevertheless remains **not complete**: a clean cold invocation of `bash compose/phase1/prepare-images.sh` cannot build the application image because `backend/uv.lock` pins direct `pypi.tuna.tsinghua.edu.cn` artifact URLs that return HTTP 403. `USE_CN_MIRROR=0` does not change those locked artifact URLs. This newly exposed committed preparation defect still blocks CORE-06's required cold image-preparation contract.

## Scope and evidence basis

Reviewed the 15 Phase 01 plans/summaries, validation strategy, roadmap, requirement mapping, repair commit, and source in a detached clean worktree at `2684b96`; unrelated primary-worktree changes were excluded.

| Evidence | Result |
| --- | --- |
| `git show 2684b96` | `QK.alerts(source?, severity?, delivery?)` emits all three dimensions; `compose/phase1.test.yml` uses `ports: !override`. |
| `docker build --target frontend-builder --build-arg USE_CN_MIRROR=0 -t athenaquant-phase1-frontend-reverify:2684b96 .` | **Passed**: `tsc -b && vite build` completed successfully from clean committed frontend source. |
| `docker compose -p athenaquant-phase1-reverify -f docker-compose.yml -f compose/phase1.test.yml config --format json` | Exactly one app port resolves: `127.0.0.1:13018 -> 3018`; the three services use only internal `phase1_test`, fixture mode, read-only fixture mount, receiver-only notification URLs, cleared credentials, and disabled AI review. |
| `docker run --rm --network none ... athenaquant-phase1-verifier:phase1 --smoke` | **Passed**: `phase1 verifier smoke passed`. |
| `bash compose/phase1/run.sh` with the prepared static Phase 1 tags | **Passed**: fixture acceptance completed; Playwright reported **2 passed, 2 intentionally cross-project skipped**; matching Compose resources were removed. |
| Focused Phase 01 pytest command covering fixture sync, contracts, portfolio, monitoring, delivery, SSE, playbook, AI review, and replay | **37 passed**, three existing Polars warnings. |
| `bash compose/phase1/prepare-images.sh` in the clean `2684b96` worktree | **Failed before smoke**: the app build's `uv sync` follows the direct locked Tsinghua wheel URLs and receives HTTP 403 for `numpy`/`pydantic`; this is independent of the repaired frontend stage. |

## Repair assessment

1. **Query-key repair: closed.** The exact three-argument `Monitor.tsx` call now conforms to `QK.alerts(source?, severity?, delivery?)`; the clean Docker frontend-builder completed TypeScript checking and production Vite build.
2. **Loopback-port repair: closed.** The Compose `!override` replaces the base `3018` publication. Resolved configuration contains only `host_ip: 127.0.0.1`, `published: 13018`, `target: 3018`.
3. **Cold preparation: open.** The preparation script is required to build all three static tags before running the no-network smoke. A clean reproduction cannot reach that step because the committed lock contains unavailable direct mirror artifacts. Existing prepared tags support the passing smoke and fixture acceptance, but do not satisfy the required cold-preparation proof.

## Requirement traceability

| Requirement | Plans | Status | Concrete committed evidence |
| --- | --- | --- | --- |
| CORE-01 | 01, 02, 11 | passed | Two-file governed fixture bundle, `FixtureProvider`, `run_phase1_fixture_sync`, and focused sync coverage pass. |
| CORE-02 | 01, 02, 11 | passed | Contract validator covers key, time, repair-window, and schema-drift failures; focused contract coverage passes. |
| CORE-03 | 03, 08, 09, 11, 13 | passed | SQLite portfolio API/service and typed client are exercised by focused portfolio coverage and fixture acceptance. |
| CORE-04 | 05, 08, 10, 11, 12, 13 | passed | Persisted monitor events and sanitized delivery outcomes are covered by focused tests and verified during fixture acceptance. |
| CORE-05 | 08, 09, 11, 12, 13 | passed | Named intraday SSE alert/portfolio events and independent subscriber behavior are covered by focused tests and acceptance. |
| CORE-06 | 06, 07, 11 | **gap** | Query-key and loopback defects are repaired; smoke and no-build/no-pull fixture acceptance pass with prepared tags, but the clean required `prepare-images.sh` cold build fails on direct locked mirror artifacts. |
| CORE-07 | 11 | passed | `docs/UPSTREAM-SYNC.md` provides source identity, owner, preserved boundary, regressions, and review/update workflow. |
| PLAN-01 | 04, 08, 10, 14 | passed | Deterministic governed-data baseline persistence/API passes focused playbook coverage. |
| PLAN-02 | 08, 10, 14, 15 | passed | Provenance, bounded audit, unavailable fallback, and AI-free replay pass focused adjustment/review/replay coverage. |

## Required next step

Repair the committed backend lock/build source configuration so `bash compose/phase1/prepare-images.sh` can complete from a clean environment without fetching unavailable direct mirror artifacts. Then rerun that script followed by `bash compose/phase1/run.sh` in a clean worktree and change CORE-06 and phase status to `passed` only after the cold preparation succeeds.

## Human verification

No additional human approval blocks this result: the Plan 06 record approves only `@playwright/test@1.61.1`. The remaining blocker is automated cold image preparation, not a human checkpoint.
