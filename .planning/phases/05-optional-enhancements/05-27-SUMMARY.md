---
phase: 05-optional-enhancements
plan: "27"
subsystem: kronos-runtime
tags: [forecast, supply-chain, byte-verify, import-origin, ipc, process-cleanup]
requires:
  - phase: 05-optional-enhancements
    provides: 05-26 config digests + flock provisioner; 05-01 pinned package/source/weight identities
provides:
  - full UPSTREAM destination SHA-256 verification with frozen source_file_digests
  - verified-directory Kronos import with origin containment and shadow rejection
  - child-side revalidation before model load
  - capped streaming diagnostics and length-bounded byte Pipe IPC
  - ready handshake after setsid plus terminate/kill descendant reaping
affects: [05-29, 05-39, FORE-01]
tech-stack:
  added: []
  patterns:
    - allowlisted vendored destination digests frozen on ResolvedCheckpoint
    - importlib.spec_from_file_location namespaced package under source_dir
    - ready frame then work deadline over spawn Pipe send_bytes/recv_bytes
    - killpg SIGTERM/SIGKILL with process.terminate/kill fallback
key-files:
  created: []
  modified:
    - backend/app/forecast/catalog.py
    - backend/app/forecast/kronos_adapter.py
    - backend/app/forecast/runner.py
    - backend/tests/forecast/test_catalog.py
    - backend/tests/forecast/test_kronos_adapter.py
    - backend/tests/forecast/test_runner.py
key-decisions:
  - "Executable Kronos identity is destination SHA-256 map + config/weight digests, not UPSTREAM revision alone."
  - "Modules load via unique _athena_kronos_* package names from source_dir; preloaded app.vendor.kronos outside source is rejected."
  - "IPC is length-capped JSON frames over a one-way Pipe; no Queue pickle path."
  - "Cleanup always terminate then kill process and process group until descendants are gone."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "Every allowlisted vendored destination and config/weight digest is verified and frozen on the resolved checkpoint."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "tests/forecast/test_catalog.py -k 'vendored_byte_manifest or config_digest or source_tamper'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Kronos loads only from verified source_dir; import shadows and post-resolve byte tampers fail closed."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "tests/forecast/test_kronos_adapter.py -k 'verified_source_directory or import_shadow_rejected or child_revalidates_bytes'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Worker stdout/manifest are capped before IPC allocation; ready handshake and timeout/lease cleanup reap descendants."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "tests/forecast/test_runner.py -k 'output_cap_before_allocation or byte_ipc or child_ready_handshake or startup_race or terminate_kill_fallback or lease_loss'"
        status: pass
    human_judgment: false
duration: 45min
completed: 2026-07-25
status: complete
---

# Phase 05 Plan 27: Runtime Byte Binding And Bounded Worker IPC Summary

**Catalog re-verifies every UPSTREAM destination and config/weight digest, Kronos imports only from the verified source directory with origin containment, and the spawn runner uses capped byte Pipe IPC with a ready handshake plus terminate/kill descendant cleanup.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-25T14:52:39Z
- **Completed:** 2026-07-25T15:40:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Extended `_verify_source` to hash every allowlisted destination file, reject path escapes/extra files, and freeze `source_manifest_sha256` + `source_file_digests` on `ResolvedCheckpoint`.
- Adapter loads Kronos via controlled `importlib` specs under `checkpoint.source_dir`, revalidates digests before load, and rejects preloaded same-name modules whose `__file__` escapes the source tree.
- Runner replaced Queue pickles with length-bounded `send_bytes`/`recv_bytes` frames, capped streaming diagnostics, ready-after-setsid startup deadline, and `_reap` terminate/kill fallback until the process group is gone.

## Task Commits

1. **Task 1: Verify every executed byte and bind imports** - `4da0c07` (feat)
2. **Task 2: Cap output before IPC and race-free cleanup** - `70cd8cd` (feat)

## Files Created/Modified

- `backend/app/forecast/catalog.py` - full source byte map + dual config digests + `verify_resolved_checkpoint`
- `backend/app/forecast/kronos_adapter.py` - verified-directory package load + shadow rejection + child revalidation
- `backend/app/forecast/runner.py` - `_CappedTextSink`, Pipe frames, ready handshake, terminate/kill reap
- `backend/tests/forecast/test_catalog.py` - vendored manifest / config digest / source tamper contracts
- `backend/tests/forecast/test_kronos_adapter.py` - verified source, import shadow, child revalidate tests
- `backend/tests/forecast/test_runner.py` - hostile output, byte IPC, ready, startup race, descendant, lease tests

## Decisions Made

- Freeze sorted `(destination, vendored_sha256)` tuples so child revalidation can detect digest-map drift, not only manifest file hash.
- Use unique `_athena_kronos_<hash>` package names so process-global `app.vendor.kronos` is never treated as proof of origin.
- Prefer Pipe `recv_bytes(maxlength=…)` over Queue so the parent never unpickles an unbounded object.
- After `killpg(SIGTERM)`, always `process.terminate()`, then SIGKILL/`process.kill()`, then poll until group absence.

## Deviations from Plan

None - plan executed exactly as written for both tasks. Tests use plan-aligned selectors with small naming adaptations (`test_catalog_*`, `test_adapter_*`, `test_runner_*`).

## Issues Encountered

- Spawn cannot pickle nested test child targets; startup-race test uses a module-level `_silent_child_no_ready`.
- Ready-handshake evidence is exercised in-process via monkeypatched setsid/limits because parent-process monkeypatches do not affect spawn children.

## User Setup Required

None - no external service configuration required. Real model assets remain operator-provisioned and local-only.

## Next Phase Readiness

- FORE-01 runtime byte binding and IPC cleanup contracts are green under local tests with no network.
- Remaining incomplete plans `05-29` / `05-39` can consume this verified import and runner surface.

## Self-Check: PASSED

- SUMMARY present at `.planning/phases/05-optional-enhancements/05-27-SUMMARY.md`
- Commits `4da0c07` and `70cd8cd` exist on `gsd/v1.0-milestone`
- Plan verification selectors all passed (catalog 4, adapter 3, runner 7 selected; catalog+adapter full 37 passed)

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-25*
