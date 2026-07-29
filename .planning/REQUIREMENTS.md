# Requirements: AthenaQuant

**Milestone:** v1.1 Operational Hardening
**Defined:** 2026-07-29
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

v1.1 hardens the shipped v1.0 MVP without adding new user-facing capabilities or weakening any fail-closed safety boundary. The four requirements below are the operator-facing outcome of the hardening work; each maps to exactly one phase (Phase 6–9).

## v1.1 Requirements

### Release Reproducibility

- [ ] **REL-01**: Operator can regenerate the complete release evidence bundle (backend JUnit, Playwright reports, and provenance-bound final gate) from a clean Windows or Linux checkout without relying on historical attestations or CI-only artifacts.

### Validation Hygiene

- [ ] **VAL-01**: The full backend, data-stack, and frontend validation suites run to completion with no avoidable deprecation warnings and no Polars sortedness warnings.

### Optional Supply Path

- [ ] **SUP-01**: Operator can approve and provision pinned optional local-model artifacts through a documented, testable command, while every unauthorized or identity-incomplete supply remains fail-closed and unavailable.

### Visual Regression

- [ ] **VIS-01**: Critical desktop and 375px responsive investor workflows are protected by durable screenshot-based visual regression evidence that fails on unintended UI drift.

## Future Requirements

None deferred. v1.1 scope is intentionally tight; any enhancement beyond hardening stays out until a later milestone.

## Out of Scope

| Feature | Reason |
|---------|--------|
| New user-facing product capabilities | v1.1 is operational hardening of the shipped v1.0 surface, not feature expansion. |
| Weakening any v1.0 fail-closed boundary (Kronos supply, sandbox, authority) | Hardening must preserve, never relax, the locked safety seams. |
| Replacing the `app.tickflow` core data stack or `tickflow_*` config keys | Upstream-synchronization path and backward compatibility are v1.0 architecture constraints; rename is not hardening. |
| Live broker order execution | Unchanged from v1.0: research, decision-planning, and monitoring only. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REL-01 | Phase 6 | Pending |
| VAL-01 | Phase 7 | Pending |
| SUP-01 | Phase 8 | Pending |
| VIS-01 | Phase 9 | Pending |

**Coverage:**

- v1.1 requirements: 4 total
- Mapped to phases: 4
- Unmapped: 0

---
*Last updated: 2026-07-29 during milestone v1.1 requirements definition*
