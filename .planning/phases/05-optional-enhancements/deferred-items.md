# Deferred Items

## Pre-existing Shadow evidence ordering flake

- **Observed during:** Plan 05-11 focused cleanup verification
- **Command:** `cd backend && uv run pytest tests/shadow -x`
- **Symptom:** `test_evidence_set_preserves_partial_fills_duplicate_groups_and_row_identity` intermittently received partial-fill quantities in `[60.0, 40.0]` rather than source order `[40.0, 60.0]`.
- **Evidence:** The complete Shadow suite had already passed 31/31 unchanged; a later run failed in Plan 05-08 code because `create_evidence_set` sorts generated UUID trade IDs before assigning evidence ordinals.
- **Scope decision:** Not modified in Plan 05-11 because the ordering behavior predates this plan and is unrelated to chronological candidate evaluation, retention, projections, or API authority.
