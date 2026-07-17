---
phase: 05-optional-enhancements
plan: "28"
subsystem: optional-dependency-supply-chain
tags: [supply-chain, kronos, pytorch, human-gate, rejection]
requires:
  - phase: 05-optional-enhancements
    provides: Plan 05-01 approved model/tokenizer revisions and weight digests plus the D-11 local-only trust boundary
provides:
  - auditable itemized human rejection for the incomplete Kronos-mini config identity and incomplete PyTorch CPU artifact identity
  - explicit fail-closed precondition that leaves Plan 05-26 unable to mutate catalog, dependency, lock, or provisioner state
affects: [05-26, FORE-01, kronos-provisioning]
tech-stack:
  added: []
  patterns: [blocking-human supply-chain rejection, fail-closed downstream precondition]
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-28-SUMMARY.md
  modified: []
key-decisions:
  - "rejected: Kronos-mini config provenance is incomplete because the required immutable URL, retrieval time, byte length, and full digest were not independently supplied"
  - "incomplete: no exact independently reviewed PyTorch CPU artifact identity or dependency-isolation attestation was supplied"
  - "Plan 05-26 remains blocked from every catalog, dependency, lock, checkpoint, and provisioner mutation"
patterns-established:
  - "A rejected or incomplete blocking-human supply identity is recorded without executor-derived substitutes and cannot be interpreted as approval."
requirements-completed: []
coverage:
  - id: D1
    description: "The complete itemized human rejection is recorded verbatim and keeps downstream provisioning blocked."
    verification:
      - kind: manual_procedural
        ref: "05-28 rejection-path printf checks plus exact-string and prohibited-mutation checks"
        status: pass
    human_judgment: true
    rationale: "The blocking-human disposition is the user's independent trust decision and cannot be inferred or auto-approved by an executor."
metrics:
  duration: 1m 41s
  completed: 2026-07-17
status: complete
approval: rejected
gate_status: blocked
recorded_at: 2026-07-17T09:30:08Z
---

# Phase 05 Plan 28: Kronos And PyTorch Supply-Chain Rejection Summary

**The independent reviewer rejected the incomplete Kronos-mini config provenance and marked the PyTorch CPU artifact identity incomplete; no new supply identity is approved, so Plan 05-26 remains fail-closed.**

## Performance

- **Duration:** 1m 41s
- **Started:** 2026-07-17T09:28:27Z
- **Completed:** 2026-07-17T09:30:08Z
- **Tasks:** 1
- **Files modified:** 1

## Overall Decision

- **Result:** `rejected`
- **Gate:** remains blocked
- **Approval granted by this record:** none
- **Downstream effect:** Plan 05-26 cannot consume any config digest or PyTorch CPU artifact identity from this record and cannot mutate `backend/app/forecast/checkpoints.example.json`, `backend/pyproject.toml`, `backend/uv.lock`, the checkpoint catalog, dependency metadata, or the provisioner.

This is a complete auditable rejection outcome under Plan 05-28's acceptance criterion. It completes the decision-record task but does **not** complete `FORE-01` and does **not** satisfy Plan 05-26's complete-approval precondition.

## Human Response Recorded Verbatim

- Config row: `Kronos-mini`
- Disposition: `rejected/incomplete`
- Reason: provenance incomplete — required immutable URL, retrieval time, byte length, and full digest were not independently supplied.
- PyTorch CPU artifact row disposition: `incomplete`
- Reason: exact version/build, wheel filename, Python/ABI/platform tags, byte length, full digest, license/source evidence, and dependency-isolation attestation were not supplied.

## Config Review Worksheet

Identity cells below deliberately contain no executor-selected values. The four rows not itemized by the human response have no reviewer disposition and therefore remain unapproved; they are shown only to preserve Plan 05-28's exactly-five-row worksheet shape.

| Config row | Official immutable URL | Immutable revision | Retrieval UTC timestamp | Byte length | Lowercase SHA-256 | Independent reviewer disposition | Notes / reason |
|---|---|---|---|---:|---|---|---|
| Kronos-mini | not independently supplied | not independently supplied for `config.json` | not independently supplied | not independently supplied | not independently supplied | `rejected/incomplete` | provenance incomplete — required immutable URL, retrieval time, byte length, and full digest were not independently supplied. |
| Kronos-small | not independently supplied | not independently supplied for `config.json` | not independently supplied | not independently supplied | not independently supplied | — | No human disposition was supplied for this row in the checkpoint response; it is not approved. |
| Kronos-base | not independently supplied | not independently supplied for `config.json` | not independently supplied | not independently supplied | not independently supplied | — | No human disposition was supplied for this row in the checkpoint response; it is not approved. |
| Tokenizer-2k | not independently supplied | not independently supplied for `config.json` | not independently supplied | not independently supplied | not independently supplied | — | No human disposition was supplied for this row in the checkpoint response; it is not approved. |
| Tokenizer-base | not independently supplied | not independently supplied for `config.json` | not independently supplied | not independently supplied | not independently supplied | — | No human disposition was supplied for this row in the checkpoint response; it is not approved. |

The previously approved model/tokenizer pairings, immutable revisions, and `model.safetensors` weight digests in `05-01-SUMMARY.md` are unchanged. They are not config approvals and are not copied into this rejection record as substitutes.

## PyTorch CPU Artifact Review Worksheet

| Package | Exact version/build | Official CPU index URL | Wheel filename | Python tag | ABI tag | Platform tag | Byte length | Full wheel SHA-256 | License/source evidence | Base-extra isolation attestation | Independent reviewer disposition | Reason |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|
| PyTorch CPU | not supplied | not supplied | not supplied | not supplied | not supplied | not supplied | not supplied | not supplied | not supplied | not supplied | `incomplete` | exact version/build, wheel filename, Python/ABI/platform tags, byte length, full digest, license/source evidence, and dependency-isolation attestation were not supplied. |

No existing open-ended Torch constraint or lock entry is implicitly approved by this row.

## Accomplishments

- Recorded the human's itemized Kronos-mini and PyTorch dispositions and reasons exactly.
- Preserved the absence of independently supplied identities rather than inventing URLs, timestamps, lengths, hashes, versions, tags, evidence, or attestations.
- Sealed the downstream fail-closed state without changing dependencies, locks, catalogs, checkpoint entries, provisioning code, vendored source, or model assets.

## Task Commits

Task 1 has no separate production-code commit because the plan authorizes only this rejection record. The rejection record and plan summary are committed together as one atomic documentation outcome.

## Files Created/Modified

- `.planning/phases/05-optional-enhancements/05-28-SUMMARY.md` — auditable blocking-human rejection record and downstream fail-closed decision.

## Decisions Made

- Treated the user's itemized response as rejection, never as approval.
- Left non-itemized config rows without a reviewer disposition; absence is not approval.
- Kept Plan 05-26 blocked because its Task 1 explicitly requires complete human approval for all five config rows and the exact PyTorch CPU artifact before any mutation.

## Deviations from Plan

None - the plan explicitly permits an itemized `rejected` outcome and prohibits all project mutation at this gate.

## Issues Encountered

None. Missing identity data is the reviewed rejection reason, not an executor error to repair or fill.

## Authentication Gates

None.

## Known Stubs

None. The `not independently supplied` cells are intentional rejection evidence and must remain empty of identity values; they are not implementation placeholders.

## Verification

PASS — Task 1 rejection path:

```text
BLOCKING HUMAN GATE — 05-26 must reject any missing, partial, inferred, or non-approved 05-28 supply identity record
```

PASS — plan-level rejection path:

```text
BLOCKING HUMAN GATE — downstream catalog, lock, and provisioner mutation remains forbidden until complete approval
```

PASS — exact-string checks found both itemized dispositions and both reasons verbatim in this record.

PASS — scope check found no approved config identity, exact PyTorch artifact identity, dependency change, lock change, checkpoint catalog mutation, or provisioner change authored by Plan 05-28.

## Next Phase Readiness

- Plan 05-28 is complete as an auditable rejection decision record.
- Plan 05-26 remains blocked and must not provision or mutate supply-chain state from this summary.
- Unblocking requires a future blocking-human response that independently supplies and approves every required identity field; executor-derived values remain inadmissible.

## Self-Check: PASSED

- The sole authorized artifact exists at `.planning/phases/05-optional-enhancements/05-28-SUMMARY.md`.
- The record contains exactly five config worksheet rows and one PyTorch CPU row.
- The itemized dispositions and reasons are recorded verbatim.
- No separate 05-28 task commit or prior `05-28-SUMMARY.md` existed before this record.
- No shared `STATE.md` or `ROADMAP.md` update is part of this plan close-out.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
