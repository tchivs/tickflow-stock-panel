---
phase: 05-optional-enhancements
plan: "26"
subsystem: kronos-provisioning
tags: [forecast, supply-chain, provisioner, config-digest, cas, torch-cpu]
requires:
  - phase: 05-optional-enhancements
    provides: 05-01 pinned package/source/weight identities; personal-project exception removing 05-40 paperwork gate
provides:
  - config.json SHA-256 identities alongside weight digests for mini/small/base pairs
  - inter-process catalog publication lock with merge-safe dual-entry provisioning
  - staging-only cleanup that never deletes shared final assets
  - exact Forecast torch==2.13.0 pin on official pytorch-cpu index with base-extra isolation
affects: [05-27, 05-39, 05-29, FORE-01]
tech-stack:
  added: []
  patterns: [dual-file config+weight verify, flock catalog publication, no planning-approval-record dependency]
key-files:
  created: []
  modified:
    - backend/app/forecast/checkpoints.example.json
    - backend/scripts/provision_kronos.py
    - backend/tests/test_kronos_provisioner.py
    - backend/tests/test_phase5_optional_dependencies.py
    - backend/pyproject.toml
    - backend/uv.lock
key-decisions:
  - "Personal project: 05-26 no longer requires approval: approved from 05-40; 05-28/05-40 remain immutable rejected history only."
  - "Executable identity authority is CheckpointSpec + 05-01 weight revisions plus catalog-bound config SHA-256 values."
  - "Catalog publication uses exclusive flock around reload/merge/promote/atomic write; rollback cleans only invocation staging."
requirements-completed: []
coverage:
  - id: D11
    description: "Pinned local config/weight/Torch identities with concurrency-safe provisioning."
    requirement: FORE-01
    verification:
      - kind: automated
        ref: "tests/test_kronos_provisioner.py + tests/test_phase5_optional_dependencies.py + uv lock --check"
        status: pass
status: complete
completed: 2026-07-24
---

# Phase 05 Plan 26: Config Digests And Concurrency-Safe Provisioning Summary

**Pinned Kronos catalog identities now bind `config.json` and `model.safetensors` digests; provisioning serializes publication with flock and never deletes shared finals. Forecast extra pins exact CPU torch from the official pytorch-cpu index. Planning approval paperwork is not a runtime precondition for this personal project.**

## Performance

- **Tasks:** 2
- **Primary suites:** `test_kronos_provisioner` 19 passed; `test_phase5_optional_dependencies` 7 passed; `uv lock --check` clean

## Accomplishments

- Extended `CheckpointSpec` / example catalog / provisioner verify path with full lowercase config SHA-256 for model and tokenizer.
- `_catalog_lock` wraps the entire publication critical section; dual concurrent provisions of different catalog IDs both survive.
- Same-ID parallel provision remains idempotent; mismatched existing finals fail closed without overwrite.
- Staging directories are the only recursive cleanup target after promotion.
- Forecast extra: `torch==2.13.0` via `pytorch-cpu` index; base install remains Torch-free.
- Tests assert no dependency on planning approval records for provision mutation.

## Verification

| Check | Result |
|-------|--------|
| `python3 -m pytest tests/test_kronos_provisioner.py -q` | 19 passed |
| `python3 -m pytest tests/test_phase5_optional_dependencies.py -q` | 7 passed |
| `uv lock --check` | clean |
| Dual-entry parallel merge | `test_parallel_different_catalog_merge_preserves_both_entries` |
| Same-entry parallel | `test_parallel_same_catalog_provisioning_preserves_one_valid_entry` |
| Config digest reject | parametrized verify mutation |
| No planning-approval gate | `test_provisioning_does_not_depend_on_a_planning_approval_record` |

## Decisions Made

- Keep 05-28 / 05-40 as historical rejected decision records only; do not rewrite them as approvals.
- Use 05-01 weight revisions plus embedded catalog config digests as the executable pin surface.
- Prefer flock serialization over pure CAS for local deployment tooling simplicity with equivalent no-lost-entry semantics under re-read merge.

## Deviations from Plan

- Original Task 1 required consuming `05-40-SUMMARY.md` with `approval: approved`. Owner personal-project exception removed that paperwork gate; implementation pins identities in code/catalog and tests reject missing/mismatched digests instead of requiring a planning approval file.

## Issues Encountered

None blocking. Real Hugging Face downloads remain operator-only and are not exercised by unit tests.

## Next Phase Readiness

- 05-27 may bind runtime imports/bytes and worker IPC against these dual digests and lock semantics.
- FORE-01 still needs 05-27 / 05-39 / 05-29 for full production closure.

## Self-Check: PASSED

- SUMMARY present; provisioner and dependency suites green; lock check clean.
- No network in unit tests; no overwrite of mismatched finals; staging-only cleanup.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-24*
