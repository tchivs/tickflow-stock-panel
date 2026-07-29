# Roadmap: AthenaQuant

## Milestones

### v1.0 MVP — shipped 2026-07-27

Five phases delivered the governed data and portfolio loop, deterministic decision safety, reproducible factor and strategy research, evidence-grounded AI analysis, controlled advanced workflows, and independently activatable Shadow, Thesis, and Forecast modules.

- Requirements: 23/23 verified
- Phases: 5/5 complete and Nyquist-compliant
- Integration: 23/23 wired
- End-to-end flows: 10/10 complete
- Final gate: 653/653 checks passed against frozen release source

Archive:

- [v1.0 roadmap](./milestones/v1.0-ROADMAP.md)
- [v1.0 requirements](./milestones/v1.0-REQUIREMENTS.md)
- [v1.0 milestone audit](./milestones/v1.0-MILESTONE-AUDIT.md)
- [v1.0 phase artifacts](./milestones/v1.0-phases/)

---

## v1.1 Operational Hardening — active

v1.1 hardens the shipped v1.0 MVP without adding new user-facing capabilities or weakening any fail-closed safety boundary. It makes release evidence routinely reproducible across supported hosts, removes avoidable validation warnings, formalizes the operator-controlled optional-model supply path, and adds durable visual-regression evidence. Phase numbering continues from v1.0 (Phase 6–9).

## Phases

**Phase Numbering:**

- Integer phases are planned delivery work.
- Decimal phases are reserved for urgent inserted work.

- [ ] **Phase 6: Release Reproducibility** - Let operators regenerate the full release evidence bundle from a clean Windows or Linux checkout without historical attestations.
- [ ] **Phase 7: Validation Hygiene** - Make the full backend, data-stack, and frontend validation suites run clean with no avoidable warnings.
- [ ] **Phase 8: Optional Supply Path** - Formalize a documented, testable operator approval and provisioning path for pinned local-model artifacts while incomplete identity stays fail-closed.
- [ ] **Phase 9: Visual Regression** - Protect critical desktop and 375px responsive investor workflows with durable screenshot-based regression evidence.

## Phase Details

### Phase 6: Release Reproducibility

**Goal**: Operators can regenerate the complete release evidence bundle from a clean checkout on either supported host, with no dependency on historical attestations or CI-only artifacts.
**Depends on**: Nothing (first hardening phase; establishes the reproducible evidence harness the later phases rely on)
**Requirements**: REL-01
**Success Criteria** (what must be TRUE):

  1. Operator can run a single documented command on a clean Windows checkout to produce the backend JUnit report, both Playwright reports, and the final-gate evidence bundle matching the frozen source.
  2. Operator can run the same command on a clean Linux checkout and produce the same bundle shape without requiring access to historical CI runs.
  3. The final-gate verifier passes against freshly regenerated reports without referencing cached attestations or CI-only artifacts.

**Plans**: 0/N plans complete
**UI hint**: no

### Phase 7: Validation Hygiene

**Goal**: The full validation suite runs to completion with no avoidable deprecation or sortedness warnings.
**Depends on**: Phase 6 (reproducible evidence harness makes clean validation routinely observable)
**Requirements**: VAL-01
**Success Criteria** (what must be TRUE):

  1. The backend pytest suite completes with no avoidable Polars deprecation warnings and no sortedness warnings.
  2. The frontend build and type-check complete with no avoidable deprecation warnings.
  3. The data-stack validation (DuckDB/Parquet contract and schema-drift checks) completes without sortedness or avoidable warnings.

**Plans**: 0/N plans complete
**UI hint**: no

### Phase 8: Optional Supply Path

**Goal**: Operators can approve and provision pinned optional local-model artifacts through a documented, testable command, while every unauthorized or identity-incomplete supply remains fail-closed and unavailable.
**Depends on**: Nothing (independent of the other hardening phases; the v1.0 fail-closed boundary is preserved, not relaxed)
**Requirements**: SUP-01
**Success Criteria** (what must be TRUE):

  1. Operator can run a documented command to provision a pinned local Kronos checkpoint that publishes only after SHA-256 and config verification.
  2. An incomplete or mismatched supply identity is rejected and the optional module reports unavailable without weakening the fail-closed default.
  3. The approval path has an automated test proving both accepted provisioning and identity-rejected failure.

**Plans**: 0/N plans complete
**UI hint**: no

### Phase 9: Visual Regression

**Goal**: Critical desktop and 375px responsive investor workflows are protected by durable screenshot-based visual regression evidence that fails on unintended UI drift.
**Depends on**: Phase 6 (visual regression is captured and asserted inside the reproducible evidence harness)
**Requirements**: VIS-01
**Success Criteria** (what must be TRUE):

  1. Critical desktop investor workflows have baseline screenshots captured and committed.
  2. Critical 375px responsive workflows have baseline screenshots captured and committed.
  3. A regression run fails when an unintended UI drift is detected against the committed baselines.

**Plans**: 0/N plans complete
**UI hint**: yes

## Coverage

| # | Phase | Requirements | Status | Target |
|---|-------|--------------|--------|--------|
| 6 | Release Reproducibility | REL-01 | Pending | — |
| 7 | Validation Hygiene | VAL-01 | Pending | — |
| 8 | Optional Supply Path | SUP-01 | Pending | — |
| 9 | Visual Regression | VIS-01 | Pending | — |

**Requirement coverage:** 4/4 mapped (100%)

---
*Last updated: 2026-07-29 during milestone v1.1 roadmap generation*
