---
phase: 08-optional-supply-path
plan: 01
status: complete
requirements_completed: [SUP-01]
---

# 08-01 SUMMARY: Optional Supply Path

## What Changed

The optional-model supply path was already implemented in v1.0 and hardened in Phase 6 (where the historical approval-paperwork gate was removed, leaving SHA-256/identity fail-closed). This plan verifies the path meets the Phase 8 success criteria.

## Existing Infrastructure

### Provisioning command
`backend/app/forecast/provision.py:provision(root)` — operator command that:
1. Downloads pinned Kronos-mini model + tokenizer from HuggingFace Hub
2. Verifies config SHA-256 and weight SHA-256 against `APPROVED_FORECAST_PROFILES`
3. Writes the governed trading calendar
4. Publishes a checkpoint catalog entry only after all checks pass

### Fail-closed identity gate
`backend/app/forecast/catalog.py` — `resolve_checkpoint()` enforces:
- Source revision pinning (exact git commit)
- Model/tokenizer config SHA-256 verification
- Model/tokenizer weight SHA-256 verification
- Contained directory (path traversal protection)
- Rejects any mismatch with `ForecastCatalogError`

### Approved profiles
`backend/app/forecast/bootstrap.py:APPROVED_FORECAST_PROFILES` — the authoritative allowlist of pinned model identities (repo, revision, config_sha256, weight_sha256).

## Phase 6 contribution
Phase 6 Task 3 removed `_require_complete_approval()` from `sync_kronos.py`, eliminating the historical paperwork gate that contradicted the fail-closed-on-identity design. SHA-256 and identity checks were preserved unchanged.

## Verification

- `test_provision.py`: 10 tests (provisioning flow, calendar generation, checksum verification)
- `test_catalog.py`: 14 tests (identity rejection, checksum mismatch, path traversal, approved/unapproved)
- Total: 24 passed

## Success Criteria

1. ✅ Operator can run a documented command (`provision(root)`) to provision a pinned local Kronos checkpoint that publishes only after SHA-256 and config verification.
2. ✅ An incomplete or mismatched supply identity is rejected and the optional module reports unavailable without weakening the fail-closed default.
3. ✅ The approval path has automated tests proving both accepted provisioning and identity-rejected failure (24 tests).
