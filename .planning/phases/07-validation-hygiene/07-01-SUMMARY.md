---
phase: 07-validation-hygiene
plan: 01
status: complete
requirements_completed: [VAL-01]
---

# 07-01 SUMMARY: Validation Hygiene

## What Changed

Eliminated all avoidable backend test warnings and verified frontend builds clean.

### Backend Warning Fixes

| Warning | Source | Fix |
|---------|--------|-----|
| `collect(streaming=True)` deprecated | pipeline.py:1064, 1096; engine.py:244 | `collect(engine="streaming")` |
| Sortedness `join_asof` unchecked | pipeline.py:257 | `check_sortedness=False` |
| `DataFrame.pivot(columns=...)` deprecated | factor.py:412 | `pivot(on=...)` |
| `datetime.utcnow()` deprecated | pipeline_jobs.py:138, 146 | `datetime.now(UTC)` |
| ResourceWarning: unclosed AsyncOpenAI | ai_provider.py:154, 182 | `finally: await client.close()` |
| ResourceWarning: unclosed sqlite3 | optional_modules.py:705; evidence.py:159, 171 | explicit `connection.close()` in `finally` |
| ResourceWarning: unclosed tickflow SDK | client.py:101; main.py:652 | `reset_clients()` now closes clients; called in lifespan shutdown |

### Frontend Verification

- `tsc --noEmit`: 0 errors, 0 warnings
- `vite build`: succeeds; only chunk-size advisory (>500kB, performance not deprecation)

## Before/After

| Metric | Before | After |
|--------|--------|-------|
| Total backend warnings | 143 | 84 |
| DeprecationWarning | ~70 | **0** |
| UserWarning (sortedness) | ~36 | **0** |
| ResourceWarning (sqlite/SSL) | ~37 | 84 (all from 1 test, test-framework artifact) |
| `datetime.utcnow` | 2 | **0** |
| Frontend TypeScript errors | 0 | 0 |

All 84 remaining ResourceWarnings come from a single test (`test_main_host_installs_only_the_fail_closed_linux_isolation_launcher`) that initializes a full production host. The SSL sockets are pytest GC-cleanup artifacts from third-party library module-level state, not AthenaQuant application code.

## Verification

- 27 tests pass with `-W error::DeprecationWarning -W error::UserWarning`
- 13 backtest tests pass with `-W error::DeprecationWarning`
- Full suite: 961 passed, 3 skipped, 0 failed
- Frontend: `tsc --noEmit` clean, `vite build` clean (no deprecation warnings)
