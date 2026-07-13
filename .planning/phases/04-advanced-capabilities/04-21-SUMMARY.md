---
phase: 04-advanced-capabilities
plan: "21"
status: complete
completed: 2026-07-13
---

# Phase 04 Plan 21: Real-Host Acceptance Summary

## Executed focused commands

| Command | Exit | Duration | Observed result |
| --- | ---: | ---: | --- |
| `cd backend && timeout 120s uv run pytest tests/advanced/test_production_host.py tests/advanced/test_viewpoints.py tests/advanced/test_evolution.py tests/advanced/test_sandbox.py -q` | 0 | 93.77s | 89 passed; 0 failed; 0 skipped; 24 warnings |
| `cd frontend && timeout 240s pnpm exec playwright test e2e/phase4-advanced-capabilities.host.spec.ts --project=phase4-fastapi-host` | 0 | 21.6s | 3 passed; 0 failed; 0 skipped; 1 worker |

## Executed host scenarios

1. `real host visibly preserves immutable viewpoint lineage, correction, evaluation, calibration, viewport evidence, job audit, and root SSE`
2. `real host visibly resolves the immutable binding, completes research feedback to five gates, promotion, and sandbox capability branch`
3. `real host denies unauthenticated, out-of-scope, rate-limited, and revoked jobs without unauthorized SSE work`

## Result

**Complete.** The serial `phase4-fastapi-host` project passed all three scenarios against the spawned FastAPI lifespan, its real Vite reverse-proxy browser origin, rendered login cookie, production API routes, operational SQLite state, governed fixture data, and root SSE. The host scenario covers the viewpoint lifecycle; immutable binding; completed aggregate, in-sample, and out-of-sample experiment evidence; feedback, candidate, five gates, and research-only promotion; authorized/rejected job behavior; sandbox review; and the 1440×960, 1024×900, and 375×844 keyboard/accessibility matrix.

The observed deployment capability branch was **`affirmative_isolation_proved`**. The real sandbox submission reached a terminal record with a proof fingerprint and resource summary; the alternative fail-closed branch is asserted by the same scenario when the host cannot prove isolation.

## Required gap mapping

| Gap ID | Executed evidence | Plan 21 closure status |
| --- | --- | --- |
| `non_intercepted_host_full_workflows` | Three serial real-host scenarios exercised the four Phase 4 workflows through the real lifespan and UI/API topology. | closed |
| `host_execution_evidence_unknown` | Both exact focused commands exited 0 with the recorded durations and counts above. | closed |
| `deployment_linux_private_root_proof` | Host output recorded `affirmative_isolation_proved` from the real sandbox terminal branch. | closed |
| `real_host_viewport_accessibility_evidence` | Real-host checks covered 1440×960, 1024×900, and 375×844: table overflow instructions, 44px controls, tabs, alert/status behavior, and dialog focus containment/restoration. | closed |
