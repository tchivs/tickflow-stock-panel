---
phase: 05-optional-enhancements
plan: "10"
subsystem: forecast-numerical-core
tags: [kronos, local-only, parquet, cn-a-calendar, sha256, numpy, quantiles, safetensors]
requires:
  - phase: 05-optional-enhancements
    plan: "04"
    provides: deterministic Forecast RED contracts and governed fixtures
  - phase: 05-optional-enhancements
    plan: "06"
    provides: managed immutable artifact store and independent optional-module foundation
  - phase: 05-optional-enhancements
    plan: "07"
    provides: approved dependency lock, pinned Kronos source, checkpoint identities, and provisioning manifest
provides:
  - strict deployment-owned typed catalog for approved mini, small, and base local checkpoint pairs
  - Parquet-backed governed CN-A session resolution and authorized daily OHLCV input freezing
  - pinned worker-only Kronos seam retaining exactly 32 pre-mean paths
  - fixed path-axis P10/P50/P90 derivation with immutable path and quantile Parquet artifacts
  - bounded path-free manifests and explicit economic validation warnings without numerical mutation
affects: [05-13, 05-14, 05-16, 05-17, FORE-01, forecast-runner, forecast-ui]
tech-stack:
  added: []
  patterns:
    - deployment-owned catalog canonicalization with task-time local integrity revalidation
    - exact governed trading-session identities instead of weekday approximation
    - parent-side immutable input fingerprint and atomic Parquet promotion
    - pinned pre-mean model seam with fixed 32-path axis-zero quantiles
key-files:
  created:
    - backend/app/forecast/catalog.py
    - backend/app/forecast/calendar.py
    - backend/app/forecast/input.py
    - backend/app/forecast/kronos_adapter.py
    - backend/app/forecast/artifacts.py
  modified: []
key-decisions:
  - "Catalog probing remains dependency-light and path-free; torch and vendored Kronos import only inside the verified worker runner."
  - "The governed calendar resolves only versioned local Parquet rows, and the input fingerprint freezes exact historical and future session identities."
  - "The pinned adapter copies only the reviewed decode seam necessary to return the sample axis before upstream mean(axis=1); P10/P50/P90 derive from axis 0."
  - "All 32 paths are promoted before the quantile descriptor is created, and public manifests expose only bounded checksummed descriptors and warning codes."
patterns-established:
  - "Forecast supply chain: approved identity, root containment, exact file allowlist, SHA-256, pairing, context, device, and source revision all pass before allocation."
  - "Forecast numerical evidence: exact finite [32,horizon,feature] paths are immutable primary evidence; quantiles are derived secondary evidence."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "Approved local mini, small, and base catalog entries pass only with exact pinned source/model/tokenizer identities, pairings, digests, safetensors files, roots, context, devices, and local-only policy."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest tests/forecast/test_catalog.py -x"
        status: pass
    human_judgment: false
  - id: D2
    description: "One authorized persisted CN-A stock freezes bounded daily OHLCV/optional amount plus exact 5/20/60 governed future sessions into deterministic immutable input provenance."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/forecast/test_input.py -x"
        status: pass
    human_judgment: false
  - id: D3
    description: "The pinned local-only Kronos adapter preserves exactly 32 pre-mean paths, derives P10/P50/P90 over path axis zero, rejects invalid tensors, and reports immutable economic warnings."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest tests/forecast/test_kronos_adapter.py -x"
        status: pass
    human_judgment: false
metrics:
  duration: 20m 20s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 10: Governed Local Kronos Numerical Core Summary

**A deployment-pinned local catalog, exact governed CN-A input freezer, and worker-only pre-mean Kronos seam now preserve 32 immutable sampled paths and derive fixed path-axis P10/P50/P90 without runtime network authority.**

## Performance

- **Duration:** 20m 20s
- **Started:** 2026-07-16T05:53:28Z
- **Completed:** 2026-07-16T06:13:48Z
- **Tasks:** 2/2
- **Files created:** 5

## Accomplishments

- Added a dependency-light catalog that accepts only approved mini/2k, small/base, and base/base checkpoint identities and revalidates local source revision, exact config/safetensors allowlists, full weight digests, pairings, context, device, root containment, and local-only loading before worker allocation.
- Added a versioned local Parquet CN-A calendar and parent-side freezer that resolves only an authorized persisted stock, validates sorted unique finite daily OHLCV with optional amount and governed adjustment/source semantics, freezes exact historical/future session IDs, and atomically promotes a deterministic checksummed input artifact.
- Added a lazy worker-only Kronos runner at reviewed source revision `67b630e67f6a18c9e9be918d9b4337c960db1e9a`, preserving the decoded `[32,horizon,feature]` tensor before upstream averaging and applying fixed seed/T/top-k/top-p/count configuration.
- Added axis-zero P10/P50/P90 derivation, hard failure for wrong shape/count/non-finite values, immutable OHLC/volume/amount/quantile-crossing warnings without mutation, and path-first immutable Parquet artifact promotion with capped path-free manifests.

## Task Commits

The pre-existing Plan 05-04 RED contracts were exercised before each GREEN implementation, and each production task was committed atomically:

1. **Task 1 RED: Approved catalog and governed input contracts** — `62ee24fdc4fcec1d88892a6e3e135335c2839873` (`test`, Plan 05-04)
2. **Task 1 GREEN: Verify local catalog and governed input** — `e2c56aa6dd31356906e18051fc4873fb2a844c97` (`feat`)
3. **Task 2 RED: Retained pre-mean path-axis contracts** — `f08c1d8102bb1364ce4235145690e17523a1ee7e` (`test`, Plan 05-04)
4. **Task 2 GREEN: Retain pre-mean Kronos paths** — `797ccd5ee546a36f1c32a4565d50a0d5f032b1a8` (`feat`)
5. **Task 1 supply-chain hardening: Reject source/root ambiguity** — `ee68ef7e7a5fb0de0ac3683b4851ac0a64a0731e` (`fix`)

## Files Created/Modified

- `backend/app/forecast/catalog.py` — sanitized typed availability, strict approved catalog parsing, local asset integrity checks, and pre-spawn revalidation.
- `backend/app/forecast/calendar.py` — governed versioned CN-A Parquet session protocol with exact 5/20/60 coverage failure.
- `backend/app/forecast/input.py` — strict browser request DTO, persisted stock authorization, daily input validation, deterministic fingerprint, and immutable Parquet freezer.
- `backend/app/forecast/kronos_adapter.py` — fixed sampling contract, local-only worker loader, reviewed pre-mean decode seam, path validation, quantiles, warnings, and opt-in approved regression adapter.
- `backend/app/forecast/artifacts.py` — path-first immutable sampled-path and quantile Parquet persistence with verified capped manifests.

## Verification

```text
cd backend && uv run --offline pytest tests/forecast/test_catalog.py tests/forecast/test_input.py tests/forecast/test_kronos_adapter.py -x
pytest: 46 passed
```

The test environment was synchronized exclusively from the existing lock with `--offline`. The focused suites use local fixtures and injected loaders; no runtime network, model download, formatter, linter, browser suite, runner/concurrency suite, or project-wide command was executed.

## Threat Mitigation Evidence

- **T-05-10-01:** Catalog contracts cover moving revisions, unapproved pairings, source identity, tampered or partial assets, non-safetensors files, symlinks/root escapes, context/device policy, and pre-spawn digest changes.
- **T-05-10-02:** Torch and vendored Kronos stay behind the worker-only lazy boundary; the runner requires a verified local-only pair and the loading seam disables remote-code/network fallback.
- **T-05-10-03:** `ForecastRequest` rejects all undeclared browser authority, while the freezer resolves principal/object scope from the persisted repository before its single governed daily read.
- **T-05-10-04:** Only exact finite `[32,horizon,feature]` output is accepted; path-axis quantiles derive after validation, all paths persist first, and economic inconsistencies become warnings without clamping or reordering.
- **T-05-10-05:** Availability, input descriptors, and result manifests are explicit allowlists that omit absolute paths, model objects, full tensors, raw tracebacks, and unbounded payloads.

## Decisions Made

- Kept the catalog probe independent of heavy Forecast dependencies so absent checkpoints degrade only Forecast and never affect completed-v1 startup.
- Used server-derived `CNA-YYYYMMDD` session identities for calendar joins and converted only the governed repository read boundary to ISO dates; no weekday or holiday approximation exists.
- Retained the pinned decode algorithm in the adapter rather than changing vendored upstream bytes, preserving Plan 05-07's exact source verification while removing only the final mean from the application-owned seam.
- Made sampled paths the primary artifact and bound quantile artifact scope to the sampled-path checksum, preventing quantile-only evidence from substituting for retained paths.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Rejected symlinked roots and non-official source repositories**
- **Found during:** Final supply-chain invariant check after Task 2
- **Issue:** A resolved root path alone did not prove the configured root itself was not a symlink, and an injected approved profile that omitted `source_repository` could otherwise leave that field unchecked.
- **Fix:** Reject configured-root symlinks before resolution and require the exact reviewed Kronos source repository independent of profile field presence.
- **Files modified:** `backend/app/forecast/catalog.py`
- **Verification:** All 17 focused catalog contracts and the final 46-test plan suite pass.
- **Committed in:** `ee68ef7e7a5fb0de0ac3683b4851ac0a64a0731e`

---

**Total deviations:** 1 auto-fixed (1 Rule 2 missing critical supply-chain check).
**Impact on plan:** The fix closes ambiguity at the declared catalog trust boundary without adding dependencies, network access, or scope.

## Issues Encountered

- The isolated worktree started at detached `HEAD`; it was attached to `worktree-agent-05-10` before any commit.
- The default worktree environment initially lacked pytest. The already-declared locked `dev` tools were synchronized with `uv run --offline --extra dev`; no dependency, lock, provisioning, or container file changed.
- The governed calendar fixture intentionally begins after the as-of session, so future resolution compares opaque governed session identities rather than requiring the anchor row to be duplicated in the future-session dataset.

## TDD Gate Compliance

- Task 1 RED commit `62ee24fdc4fcec1d88892a6e3e135335c2839873` predates GREEN commit `e2c56aa6dd31356906e18051fc4873fb2a844c97`.
- Task 2 RED commit `f08c1d8102bb1364ce4235145690e17523a1ee7e` predates GREEN commit `797ccd5ee546a36f1c32a4565d50a0d5f032b1a8`.
- Both RED suites were observed failing on their absent production modules in this worktree before implementation; the final ordinary pytest command passes 46/46.

## Known Stubs

None. Optional `None` fields represent an intentionally unconfigured artifact store, historical-session input for pure injected test inference, or lazy unloaded model state; production local inference requires governed historical sessions and catalog-verified assets. Empty lists and mappings are bounded accumulators or manifest containers, not fake outputs or UI data sources.

## User Setup Required

None for routine application startup or focused verification. Real checkpoint acquisition remains the explicit operator-only Plan 05-07 provisioning action; absent assets produce typed Forecast unavailability.

## Next Phase Readiness

- Plan 05-13 can pass a revalidated `ResolvedCheckpoint`, frozen input descriptor, governed session IDs, and artifact scope into the bounded runner while preserving exactly 32 paths.
- Plans 05-14 and 05-16 can consume immutable quantile/path descriptors and fingerprints without gaining market-data, checkpoint, or downstream-action authority.
- FORE-01 concurrency remains intentionally owned by Plan 05-13; this plan does not expose a host API or auto-dismiss duplicate/interruption/parallel/retry/restart semantics.

## Self-Check: PASSED

Verified all five declared production artifacts and this summary exist, all three Plan 05-10 commits resolve as commits, the final focused suite passes 46/46, no tracked file was deleted, and no dependency, lock, provisioning, container, endpoint, or unrelated source file changed.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
