---
phase: 04
slug: advanced-capabilities
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-12
---

# Phase 04 - Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio; Playwright |
| **Config file** | `backend/pyproject.toml`; `frontend/playwright.config.ts` |
| **Commit fast-feedback rule** | Every task uses its mapped focused pytest or TypeScript smoke command under `timeout 30s`; timeout is a failing verification result, not a waiver. |
| **Wave-completion command** | `cd backend && uv run pytest tests/advanced -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |
| **Maximum feedback latency** | <=30 seconds per task commit; full backend plus Playwright command after every completed wave. |

## Sampling Rate

- **After every task commit:** Run that task's `Commit Fast Feedback` command. It must finish within 30 seconds, including setup invoked by the command.
- **After every plan wave:** Run the Wave-completion command. It is the required full backend plus production-build plus Playwright gate and is intentionally not subject to the commit latency budget.
- **Before `/gsd-verify-work`:** Re-run the Wave-completion command, the hostile sandbox matrix, and the desktop/tablet/mobile paths in `phase4-advanced-capabilities.spec.ts`.
- **Wave 0 rule:** Its RED contracts must be created before any consumer is implemented. Later tasks listed below consume those exact contract files; no production task may replace or bypass them.

## Task-ID Convention And Status

Task IDs are taken from the numbered `Task N` labels in the actual `<task>` elements. Plan `04-08` contains `Task 1` and `Task 3`; consequently this map contains `04-08-01` and `04-08-03` only. There is no actual `<task>` for `04-08-02`, so no such row is fabricated.

All rows are **planned, pending implementation**: no Phase 4 `SUMMARY.md` exists, the Wave 0 test contracts are not yet present, and the Phase 4 Playwright file is not yet present. “Consumes” lists the declared Wave 0 contract(s) and immediate implementation precursor(s) that the task must preserve.

## Per-Task Verification Map

| Task ID | Plan / Wave | Requirements | Threat / secure behavior | Test file(s) | Exact task automated command | Commit Fast Feedback <=30s | Wave 0 dependency / consumes | Status |
|---------|-------------|--------------|--------------------------|--------------|------------------------------|-----------------------------|-------------------------------|--------|
| `04-01-01` | 01 / 0 | ADV-01, ADV-02, ADV-03 | T-04-01: immutable viewpoint facts, frozen plans, unevaluable outcomes, and calibration cannot be rewritten. | `backend/tests/advanced/test_viewpoints.py` | `cd backend && uv run pytest tests/advanced/test_viewpoints.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py -q` | Wave 0 producer; none. | planned; RED contract file pending |
| `04-01-02` | 01 / 0 | ADV-01, ADV-02, ADV-03 | T-04-03: append-only experiment spec/run/feedback lineage and retry semantics remain attributable. | `backend/tests/advanced/test_experiments.py` | `cd backend && uv run pytest tests/advanced/test_experiments.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_experiments.py -q` | Wave 0 producer; none. | planned; RED contract file pending |
| `04-01-03` | 01 / 0 | ADV-01, ADV-02, ADV-03 | T-04-02, T-04-03: five independent gates, server principal, rationale, replay safety, and no execution-adapter invocation. | `backend/tests/advanced/test_evolution.py` | `cd backend && uv run pytest tests/advanced/test_evolution.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_evolution.py -q` | Wave 0 producer; none. | planned; RED contract file pending |
| `04-02-01` | 02 / 0 | SAFE-01 | T-04-04, T-04-05: server-derived principal, scoped opaque authorization, audit-only denial, idempotency, and pre-run revocation/policy/quota recheck. | `backend/tests/advanced/test_authorization_jobs.py` | `cd backend && uv run pytest tests/advanced/test_authorization_jobs.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_authorization_jobs.py -q` | Wave 0 producer; none. | planned; RED contract file pending |
| `04-02-02` | 02 / 0 | SAFE-01 | T-04-06: persisted ownership and subscriber scope are checked before safe allowlisted DTO/SSE projection. | `backend/tests/advanced/test_api_sse.py` | `cd backend && uv run pytest tests/advanced/test_api_sse.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_api_sse.py -q` | Wave 0 producer; none. | planned; RED contract file pending |
| `04-02-03` | 02 / 0 | SAFE-01 | T-04-07: fixed graph topology, server thread ownership, pure interrupt, and single authoritative outcome on resume. | `backend/tests/advanced/test_workflow.py` | `cd backend && uv run pytest tests/advanced/test_workflow.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_workflow.py -q` | Wave 0 producer; none. | planned; RED contract file pending |
| `04-03-01` | 03 / 0 | SAFE-02, ADV-01, ADV-02, ADV-03, SAFE-01 | T-04-08, T-04-09: strict same-request source/contract admission, proven isolation, resource bounds, redaction, and zero host-code spawn on rejection. | `backend/tests/advanced/test_sandbox.py` | `cd backend && uv run pytest tests/advanced/test_sandbox.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_sandbox.py -q` | Wave 0 producer; none. | planned; RED contract file pending |
| `04-03-02` | 03 / 0 | SAFE-02, ADV-01, ADV-02, ADV-03, SAFE-01 | T-04-10: fixture-backed UI proves safe redaction, rejection behavior, root-only SSE, and responsive/keyboard flows. | `frontend/e2e/phase4-advanced-capabilities.spec.ts` | `cd frontend && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium` | `cd frontend && timeout 30s pnpm exec tsc -b --pretty false` | Wave 0 producer; none. | planned; RED browser contract file pending |
| `04-04-01` | 04 / 1 | ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02 | T-04-12, T-04-13: strict bounded input models reject client authority; projection allowlists keep source, tokens, policy, paths, and raw diagnostics unreachable. | `backend/tests/advanced/test_api_sse.py`; `backend/tests/advanced/test_sandbox.py` | `cd backend && uv run pytest tests/advanced/test_api_sse.py tests/advanced/test_sandbox.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_api_sse.py tests/advanced/test_sandbox.py -q` | Consumes `04-02-02` and `04-03-01`; plan dependency also requires all Wave 0 contracts. | planned; awaits Wave 0 |
| `04-04-02` | 04 / 1 | ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02 | T-04-11: immutable SQLite facts, FK/check constraints, conditional job cursor, and unique idempotent/outcome keys prevent tampering and duplicate authority. | `backend/tests/advanced/test_viewpoints.py`; `backend/tests/advanced/test_experiments.py`; `backend/tests/advanced/test_evolution.py`; `backend/tests/advanced/test_authorization_jobs.py` | `cd backend && uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py tests/advanced/test_evolution.py tests/advanced/test_authorization_jobs.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py tests/advanced/test_evolution.py tests/advanced/test_authorization_jobs.py -q` | Consumes `04-01-01..03` and `04-02-01`; plan dependency also requires all Wave 0 contracts. | planned; awaits Wave 0 |
| `04-05-01` | 05 / 2 | ADV-01 | T-04-14, T-04-16: append-only attributed viewpoint versions and safe projections prevent lineage tampering or disclosure. | `backend/tests/advanced/test_viewpoints.py` | `cd backend && uv run pytest tests/advanced/test_viewpoints.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py -q` | Consumes `04-01-01` through `04-04-01/02`. | planned; awaits Plan 04 |
| `04-05-02` | 05 / 2 | ADV-01 | T-04-15: server freezes benchmark/window/input fingerprint and persists unevaluable and insufficient-sample states rather than recomputing history. | `backend/tests/advanced/test_viewpoints.py` | `cd backend && uv run pytest tests/advanced/test_viewpoints.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py -q` | Consumes `04-01-01` through `04-04-01/02`. | planned; awaits Plan 04 |
| `04-06-01` | 06 / 2 | ADV-02, ADV-03 | T-04-17, T-04-19: immutable specs/runs, governed manifests, redacted constraints, and feedback only for eligible completed runs. | `backend/tests/advanced/test_experiments.py` | `cd backend && uv run pytest tests/advanced/test_experiments.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_experiments.py -q` | Consumes `04-01-02` through `04-04-01/02`. | planned; awaits Plan 04 |
| `04-06-02` | 06 / 2 | ADV-02, ADV-03 | T-04-18: each of five persisted gates is independently required; server principal/rationale and atomic uniqueness prevent replayed promotion and execution. | `backend/tests/advanced/test_evolution.py` | `cd backend && uv run pytest tests/advanced/test_evolution.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_evolution.py -q` | Consumes `04-01-03` through `04-04-01/02`. | planned; awaits Plan 04 |
| `04-07-01` | 07 / 2 | SAFE-01, SAFE-02 | T-04-20, T-04-21: hashed server-bound authorization, transactional issuance, redacted audit-only denial, and just-in-time revocation/policy revalidation. | `backend/tests/advanced/test_authorization_jobs.py` | `cd backend && uv run pytest tests/advanced/test_authorization_jobs.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_authorization_jobs.py -q` | Consumes `04-02-01` through `04-04-01/02`. | planned; awaits Plan 04 |
| `04-07-02` | 07 / 2 | SAFE-01, SAFE-02 | T-04-22, T-04-23: AST/import admission plus affirmative isolation proof, caps, cleanup, and no host dynamic execution. | `backend/tests/advanced/test_sandbox.py` | `cd backend && uv run pytest tests/advanced/test_sandbox.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_sandbox.py -q` | Consumes `04-03-01` through `04-04-01/02`. | planned; awaits Plan 04 |
| `04-08-01` | 08 / 3 | ADV-03, SAFE-01 | T-04-24, T-04-25, T-04-27: authorize/freeze before graph work, server-owned checkpoint binding, deterministic routing, pure interrupt, and record-once recovery. | `backend/tests/advanced/test_workflow.py` | `cd backend && uv run pytest tests/advanced/test_workflow.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_workflow.py -q` | Consumes `04-02-03`, plus job/auth foundations from `04-07-01` and domain services from `04-05`/`04-06`. | planned; awaits Waves 1-2 |
| `04-08-03` | 08 / 3 | ADV-03, SAFE-01 | T-04-26: only post-commit, scope-filtered, allowlisted `advanced_progress` stages may enter an authorized subscriber queue. | `backend/tests/advanced/test_api_sse.py` | `cd backend && uv run pytest tests/advanced/test_api_sse.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_api_sse.py -q` | Consumes `04-02-02`, `04-07-01`, and protected job/domain state from `04-05`/`04-06`. | planned; awaits Waves 1-2 |
| `04-09-01` | 09 / 4 | ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02 | T-04-28, T-04-29, T-04-30: authenticated ownership-before-projection, strict immutable create/read paths, non-enumerating safe errors, and no fact PATCH/DELETE. | `backend/tests/advanced/test_viewpoints.py`; `backend/tests/advanced/test_experiments.py` | `cd backend && uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py -q` | Consumes `04-01-01/02`, `04-05-01/02`, `04-06-01`, and the Wave 3 workflow/SSE prerequisite. | planned; awaits Waves 1-3 |
| `04-09-02` | 09 / 4 | ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02 | T-04-28, T-04-29, T-04-30: server-owned promotion/job/sandbox authority, ownership-safe resume, redacted audits, and no broker/monitor/execution route. | `backend/tests/advanced/test_evolution.py`; `backend/tests/advanced/test_api_sse.py`; `backend/tests/advanced/test_sandbox.py` | `cd backend && uv run pytest tests/advanced/test_evolution.py tests/advanced/test_api_sse.py tests/advanced/test_sandbox.py -q` | `cd backend && timeout 30s uv run pytest tests/advanced/test_evolution.py tests/advanced/test_api_sse.py tests/advanced/test_sandbox.py -q` | Consumes `04-01-03`, `04-02-01/02`, `04-03-01`, `04-06-02`, `04-07-01/02`, and `04-08-03`. | planned; awaits Waves 1-3 |
| `04-10-01` | 10 / 5 | ADV-01, SAFE-01 | T-04-31, T-04-32, T-04-33: typed safe DTOs, resource-scoped cache keys, strict root SSE parsing, and no client scope/authority or task-specific EventSource. | `frontend/e2e/phase4-advanced-capabilities.spec.ts` | `cd frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium` | `cd frontend && timeout 30s pnpm exec tsc -b --pretty false` | Consumes `04-03-02` browser contract and `04-09-01/02` authenticated API/SSE artifacts. | planned; awaits Plan 09 |
| `04-10-02` | 10 / 5 | ADV-01, SAFE-01 | T-04-31, T-04-32, T-04-33: UI renders only frozen server facts and committed safe stages; rejection has no loader or task-specific stream. | `frontend/e2e/phase4-advanced-capabilities.spec.ts` | `cd frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium` | `cd frontend && timeout 30s pnpm exec tsc -b --pretty false` | Consumes `04-03-02`, `04-10-01`, and `04-09-01/02`. | planned; awaits Plan 09 and task `04-10-01` |
| `04-11-01` | 11 / 6 | ADV-02, ADV-03, SAFE-01, SAFE-02 | T-04-34, T-04-35, T-04-36: server gate DTOs control promotion, sandbox/audit UI remains redacted, and immutable identifiers/mutations prevent feedback tampering. | `frontend/e2e/phase4-advanced-capabilities.spec.ts` | `cd frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium` | `cd frontend && timeout 30s pnpm exec tsc -b --pretty false` | Consumes `04-03-02`, typed client/cache/SSE work from `04-10-01`, and API services from `04-09-01/02`. | planned; awaits Wave 5 |
| `04-11-02` | 11 / 6 | ADV-02, ADV-03, SAFE-01, SAFE-02 | T-04-34, T-04-35, T-04-36: existing Backtest composition adds no parallel shell, direct fetch, independent stream, authority editor, or execution affordance. | `frontend/e2e/phase4-advanced-capabilities.spec.ts` | `cd frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` | `cd frontend && timeout 30s pnpm exec tsc -b --pretty false` | Consumes `04-03-02`, `04-10-01/02`, and all authenticated backend artifacts exposed by `04-09`. | planned; awaits Wave 5 |

## Wave 0 Required Artifacts

- [ ] `backend/tests/advanced/test_viewpoints.py` from `04-01-01`: immutable version, frozen evaluation, calibration, and explicit unevaluable contracts.
- [ ] `backend/tests/advanced/test_experiments.py` from `04-01-02`: frozen spec/run/feedback and retry lineage contracts.
- [ ] `backend/tests/advanced/test_evolution.py` from `04-01-03`: five-gate approval and registered-only promotion contracts.
- [ ] `backend/tests/advanced/test_authorization_jobs.py` from `04-02-01`: two-stage authorization, revocation, quota, idempotency, and audit-only rejection contracts.
- [ ] `backend/tests/advanced/test_api_sse.py` from `04-02-02`: ownership-safe API projection and scope-filtered durable SSE contracts.
- [ ] `backend/tests/advanced/test_workflow.py` from `04-02-03`: fixed topology, pure interrupt, and replay-safe outcome contracts.
- [ ] `backend/tests/advanced/test_sandbox.py` from `04-03-01`: hostile admission, capability proof, process/resource bounds, cleanup, and redaction contracts.
- [ ] `frontend/e2e/phase4-advanced-capabilities.spec.ts` from `04-03-02`: six fixture-backed desktop/tablet/mobile UI scenarios and root-SSE/rejection coverage.

## Wave Completion Gates

| Completed wave | Required full verification |
|----------------|----------------------------|
| 0 | `cd backend && uv run pytest tests/advanced -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |
| 1 | `cd backend && uv run pytest tests/advanced -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |
| 2 | `cd backend && uv run pytest tests/advanced -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |
| 3 | `cd backend && uv run pytest tests/advanced -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |
| 4 | `cd backend && uv run pytest tests/advanced -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |
| 5 | `cd backend && uv run pytest tests/advanced -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |
| 6 | `cd backend && uv run pytest tests/advanced -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Linux isolation capability | SAFE-02 | Namespace permissions differ by Docker/host deployment. | Run the harmless capability probe; if network/filesystem isolation cannot be proven, confirm all custom-run APIs fail closed with no spawned runner. |
| Responsive review | ADV-01..03 | Visual hierarchy requires human assessment beyond semantic browser assertions. | Review approved flows at 1440px, 1024px, and 375px; verify anchor status, rejection, unevaluable, gate, and audit detail visibility. |

## Validation Sign-Off

- [x] Every actual `<task>` across all 11 Phase 4 plans has a mapped task ID, plan, wave, requirements, threat behavior, test file(s), exact plan command, Wave 0 dependency, and status.
- [x] The Wave 0 map includes `04-01-01..03`, `04-02-01..03`, and `04-03-01..02`; every later consumer is explicitly mapped.
- [x] Each task has a targeted pytest or TypeScript smoke command capped at 30 seconds for commit-level feedback.
- [x] Full backend plus production-build plus Playwright verification remains mandatory after every wave.
- [x] Sampling continuity has no three-task automated-verification gap.
- [x] No watch-mode flags.
- [x] `nyquist_compliant: true` remains set in frontmatter.

**Approval:** pending implementation
