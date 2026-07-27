---
phase: 05-optional-enhancements
plan: "07"
subsystem: optional-dependency-supply-chain
tags: [uv, scikit-learn, pytorch, kronos, huggingface, safetensors, offline-provisioning]
requires:
  - phase: 05-optional-enhancements
    provides: explicit package, source, checkpoint, digest, and local-only approval from Plan 05-01
  - phase: 05-optional-enhancements
    provides: Forecast catalog and local-only security contracts from Plan 05-04
provides:
  - independently selectable Shadow and Forecast optional dependency extras with a reproducible lock
  - reviewed Kronos inference-only source pinned to commit 67b630e67f6a18c9e9be918d9b4337c960db1e9a
  - explicit immutable mini, small, and base checkpoint provisioning with local-only verification
  - deployment catalog example with exact revisions, full digests, approved pairings, and relative paths
affects: [05-10, 05-13, 05-14, SHDW-01, FORE-01, optional runtime images]
tech-stack:
  added: [scikit-learn 1.8.0, torch 2.x CPU, einops 0.8.1, huggingface-hub 0.33.1, safetensors 0.6.2]
  patterns:
    - optional extras preserve a dependency-light base runtime
    - reviewed vendor bytes carry immutable upstream and final digests
    - operator-only checkpoint acquisition stages, verifies, and atomically promotes safetensors
key-files:
  created:
    - backend/app/vendor/kronos/__init__.py
    - backend/app/vendor/kronos/kronos.py
    - backend/app/vendor/kronos/module.py
    - backend/app/vendor/kronos/LICENSE
    - backend/app/vendor/kronos/UPSTREAM.json
    - backend/scripts/sync_kronos.py
    - backend/scripts/provision_kronos.py
    - backend/app/forecast/checkpoints.example.json
    - backend/tests/test_kronos_vendor_sync.py
    - backend/tests/test_kronos_provisioner.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/tests/test_phase5_optional_dependencies.py
key-decisions:
  - "Kronos-base revision 2b554741eca47781b64468546e77fef3e85130e6 is cataloged only with Tokenizer-base and remains explicit-provisioning-only."
  - "Provisioning downloads only config.json and model.safetensors at immutable revisions into a temporary namespace, then verifies full SHA-256 before promotion."
  - "Verify-only and routine runtime paths never import Hugging Face or contact the network; absent assets remain an optional capability concern."
patterns-established:
  - "Supply-chain precondition: every lock, vendor, or checkpoint mutation revalidates the complete approved 05-01 record."
  - "No in-place checkpoint overwrite: existing assets must already match the approved digest and allowlist or the operation fails closed."
requirements-completed: [SHDW-01, FORE-01]
coverage:
  - id: D1
    description: "Shadow and Forecast dependencies are independently selectable approved extras while the base installation remains free of their heavy packages."
    requirement: SHDW-01
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest tests/test_phase5_optional_dependencies.py -x"
        status: pass
      - kind: other
        ref: "cd backend && uv lock --check"
        status: pass
    human_judgment: false
  - id: D2
    description: "The vendored Kronos inference subset, MIT license, upstream commit, source blobs, approved import diff, and final bytes verify exactly without runtime fetches."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_kronos_vendor_sync.py -x"
        status: pass
      - kind: other
        ref: "cd backend && uv run python scripts/sync_kronos.py --verify-local"
        status: pass
    human_judgment: false
  - id: D3
    description: "Explicit mini, small, and base checkpoint provisioning enforces immutable pairings, safetensors-only files, root containment, full digests, offline verification, and atomic catalog publication."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_kronos_provisioner.py -x"
        status: pass
    human_judgment: false
metrics:
  duration: 12m 30s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 07: Approved Optional Dependencies And Kronos Provisioning Summary

**Approved Shadow/Forecast extras, byte-pinned Kronos inference source, and operator-only immutable safetensors provisioning now form a reproducible optional boundary without adding runtime downloads or heavy base dependencies.**

## Performance

- **Duration:** 12m 30s
- **Started:** 2026-07-16T05:34:03Z
- **Completed:** 2026-07-16T05:46:33Z
- **Tasks:** 3/3
- **Files created/modified:** 13

## Accomplishments

- Added `shadow` and `forecast` extras with only the human-approved dependency identities and a checked `uv.lock`; base, backtest, desktop, and legacy groups retain their existing meaning.
- Vendored only the reviewed Kronos inference boundary and MIT license from commit `67b630e67f6a18c9e9be918d9b4337c960db1e9a`, with source blob identities, vendored SHA-256 values, approved import-only modifications, and a review-only verifier/synchronizer.
- Added an explicit operator provisioner for approved `mini:2k`, `small:base`, and `base:base` pairs. The separately approved Kronos-base revision `2b554741eca47781b64468546e77fef3e85130e6` and digest `abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83` are paired only with Tokenizer-base and marked explicit-provisioning-only.
- Enforced fixed 40-hex revisions, exact JSON/safetensors file allowlists, full weight digests, model-root containment, no symlinks or executable/pickle files, no in-place overwrite, temporary staging, atomic catalog replacement, and sanitized failures.
- Added a host-path-free example catalog and 16 checkpoint tests that use fixture bytes plus injected download functions; no real checkpoint is downloaded during tests.

## Task Commits

Each task was committed atomically; TDD tasks retain separate RED and GREEN commits:

1. **Task 1: Add approved Shadow and Forecast extras without changing the base runtime** — `f1b7a7cd820d4aac6309f1f2c2d4684cc3df8a18` (`feat`)
2. **Task 2 RED: Specify pinned vendor synchronization contracts** — `914fda904aecc8652a7949b9430871463f6e385b` (`test`)
3. **Task 2 GREEN: Vendor the pinned inference subset and review-only synchronization** — `dcb917e8fa54765f03ffb25e6b7901338492c758` (`feat`)
4. **Task 3 RED: Specify immutable checkpoint provisioning contracts** — `b9725a004f51b052a70427a5b1efd42ff69169ec` (`test`)
5. **Task 3 GREEN: Add immutable checkpoint provisioning and catalog example** — `03abad01b000765cd8a643e5c5f0a99d293f4277` (`feat`)

## Files Created/Modified

- `backend/pyproject.toml` — Approved independent `shadow` and `forecast` extras plus the official CPU-only PyTorch source.
- `backend/uv.lock` — Reproducible resolution and hashes for the approved optional packages.
- `backend/tests/test_phase5_optional_dependencies.py` — Approval precondition, exact dependency identity, lock, and base-independence contracts.
- `backend/app/vendor/kronos/__init__.py` — Restricted reviewed exports for `Kronos` and `KronosTokenizer` only.
- `backend/app/vendor/kronos/kronos.py` — Pinned upstream inference implementation with the recorded package-relative import adjustment.
- `backend/app/vendor/kronos/module.py` — Byte-identical pinned upstream inference primitives.
- `backend/app/vendor/kronos/LICENSE` — Exact upstream MIT license.
- `backend/app/vendor/kronos/UPSTREAM.json` — Repository, commit, blob SHA-1, source/final SHA-256, license, and approved diff rationale.
- `backend/scripts/sync_kronos.py` — Fixed-commit local verifier and explicit temporary review staging path that never executes downloaded Python.
- `backend/tests/test_kronos_vendor_sync.py` — Pinned commit, file allowlist, license, blob, digest, diff, replacement, and offline-runtime contracts.
- `backend/scripts/provision_kronos.py` — Immutable checkpoint specifications, approval guard, fixed-file Hugging Face acquisition, local verification, atomic promotion/catalog update, and CLI.
- `backend/app/forecast/checkpoints.example.json` — Complete relative-path mini/small/base deployment catalog example plus the reviewed Kronos-large opt-out reason.
- `backend/tests/test_kronos_provisioner.py` — Offline-fixture coverage for identities, moving refs, pairings, unsafe files, digests, roots, partial state, overwrite prevention, atomicity, and runtime isolation.

## Decisions Made

- The approved mapping is exposed through an immutable mapping of frozen `CheckpointSpec` values so operator selection cannot introduce an arbitrary repository, moving revision, or pairing.
- The provisioner requests only `config.json` and `model.safetensors` with exact Hugging Face commit revisions. Returned cache files are copied into a new model-root-contained staging directory, preventing Hub cache metadata or unrelated repository files from entering deployed assets.
- `verify_checkpoint()` performs no Hugging Face import and no network operation. `--offline` additionally forces provisioning downloads to use the local Hub cache only.
- A valid existing shared Tokenizer-base directory may be reused by small/base, but any mismatch is rejected before download or catalog mutation and is never overwritten.
- The production catalog is deployment-owned and atomically replaced only after both pair members pass file-type, config, digest, and approved-identity verification.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The resumed isolated worktree began on detached `HEAD`; it was attached to the dedicated `worktree-agent-Resume05-07Worktree` branch before any new commit, preserving executor branch safety and all prior Task 1–2 commits.
- The fresh isolated environment initially lacked the development extra, so the first RED invocation could not spawn pytest. `uv run --extra dev pytest ...` initialized the already-locked test tooling; the complete Plan 05-07 command then ran successfully in the normal environment.

## Verification

```text
cd backend && uv run pytest tests/test_phase5_optional_dependencies.py tests/test_kronos_vendor_sync.py tests/test_kronos_provisioner.py -x
35 passed in 1.59s

cd backend && uv lock --check
Resolved 153 packages in 1ms

cd backend && uv run python scripts/sync_kronos.py --verify-local
Pinned Kronos vendor verification passed.
```

The checkpoint suite used only local fixture bytes and injected downloader callables. No real Hugging Face checkpoint download occurred.

## TDD Gate Compliance

- Task 2 RED commit `914fda904aecc8652a7949b9430871463f6e385b` preceded GREEN commit `dcb917e8fa54765f03ffb25e6b7901338492c758`.
- Task 3 RED commit `b9725a004f51b052a70427a5b1efd42ff69169ec` failed on the absent `scripts.provision_kronos` module before GREEN commit `03abad01b000765cd8a643e5c5f0a99d293f4277` made all 16 provisioner contracts pass.

## Known Stubs

None. Empty lists and dictionaries found by the stub scan are bounded accumulators or test fixture containers; no placeholder or empty data source flows to runtime/UI output.

## User Setup Required

None for routine application operation or verification. Checkpoint acquisition remains an explicit deployment operator action using `backend/scripts/provision_kronos.py`; application startup, requests, workers, and tests do not invoke it.

## Next Phase Readiness

- Plan 05-10 can consume the exact approved catalog schema and local directories without adding network or remote-code fallback.
- Plans 05-13 and 05-14 can freeze the verified source/model/tokenizer provenance into runner and forecast records.
- No blocker remains for subsequent Forecast implementation; deployments without an explicitly provisioned approved pair remain safely unavailable rather than affecting the completed v1 loop.

## Self-Check: PASSED

- All 13 implementation/test artifacts and this summary exist in the resumed worktree.
- Task commits `f1b7a7c`, `914fda9`, `dcb917e`, `b9725a0`, and `03abad0` resolve as commits.
- The complete 35-test Plan 05-07 suite, lock check, and local vendor verifier passed after the final implementation.
- No unrelated file was staged or committed.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
