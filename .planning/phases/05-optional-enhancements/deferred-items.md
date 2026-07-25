# Deferred Items

## Pre-existing Shadow evidence ordering flake

- **Observed during:** Plan 05-11 focused cleanup verification
- **Command:** `cd backend && uv run pytest tests/shadow -x`
- **Symptom:** `test_evidence_set_preserves_partial_fills_duplicate_groups_and_row_identity` intermittently received partial-fill quantities in `[60.0, 40.0]` rather than source order `[40.0, 60.0]`.
- **Evidence:** The complete Shadow suite had already passed 31/31 unchanged; a later run failed in Plan 05-08 code because `create_evidence_set` sorts generated UUID trade IDs before assigning evidence ordinals.
- **Scope decision:** Not modified in Plan 05-11 because the ordering behavior predates this plan and is unrelated to chronological candidate evaluation, retention, projections, or API authority.

## Owner-accepted Kronos supply identity hold (personal project)

- **Recorded:** 2026-07-22
- **Context:** Plans 05-28 and 05-40 remain immutable `approval: rejected` / `gate_status: blocked` history. Owner indicated the six-row human supply form is disproportionate for solo/personal use.
- **Decision:** Do **not** invent, fetch, hash, or self-approve Kronos `config.json` or PyTorch CPU wheel identities. Leave production supply mutation fail-closed.
- **Update 2026-07-24:** 05-26 completed under personal-project exception (no 05-40 paperwork; identities pinned in code/catalog).
- **Remaining:** 05-27, 05-39, 05-29.
- **Unblocked / complete independent code gaps:** 05-33, 05-34, 05-35, 05-36, 05-37, 05-38, 05-40 (decision record), 05-41.
- **FORE-01:** Remains incomplete for real approved-asset Kronos inference; fixture / non-supply Forecast paths already closed by independent gap plans.
- **Resume path if wanted later:** Owner supplies complete six-row table (5 config + 1 torch CPU) → append new approved supply record (do not edit 05-28/05-40) → execute 05-26→05-27→05-39→05-29 → re-verify Phase 05.
- **Scope decision:** No catalog, lock, provisioner, vendored source, or model-byte mutation until that resume path runs.

