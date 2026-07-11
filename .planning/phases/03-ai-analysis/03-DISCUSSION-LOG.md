# Phase 3: AI Analysis - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 03-AI Analysis
**Areas discussed:** Signal lifecycle governance, Default paths in existing workspaces

---

## Signal Lifecycle Governance

| Question | Options | Selected |
|----------|---------|----------|
| Who may initiate lifecycle transitions? | System proposes, human confirms; rules change automatically; human changes only | System proposes, human confirms |
| What evidence threshold permits a proposal? | State-specific thresholds; uniform two-source threshold; low-threshold proposals | State-specific thresholds |
| How is an outcome plan retained? | Immutable auditable observation plan; globally standardized observation; continuously adjustable observation | Immutable auditable observation plan |
| What remains after rejecting a proposal? | Retain every review outcome; retain confirmed events only; retain anonymized rejection summary | Retain every review outcome |

**User's choice:** AI may propose lifecycle changes from new evidence, but a researcher or investor must confirm the official state. Thresholds vary by state; confirmed transitions create immutable outcome observations; rejected proposals remain auditable.
**Notes:** Strengthened/weakened require attributable evidence; falsified requires an invalidation condition or independently cross-checked contradiction; priced-in requires price/event context. Observation plans use 20, 60, or 120 trading days with benchmark and metric.

---

## Default Paths In Existing Workspaces

| Question | Options | Selected |
|----------|---------|----------|
| Where should a new analysis start? | Object-local entry; unified global entry; stock-first entry | Object-local entry |
| What appears when a report already exists? | Show most recent report; regenerate every time; show history first | Show most recent report |
| What remains while changing report panels? | Preserve object and reading context; preserve object only; always return to summary | Preserve object and reading context |
| How does regeneration coexist with an old report? | Keep prior report during update; replace with loading; automatically compare versions | Keep prior report during update |

**User's choice:** Start from the selected stock or portfolio, show the most recent validated report, preserve the reading context across evidence and lifecycle panels, and leave the prior report readable during regeneration.
**Notes:** The global AI host is for report recovery and review. One generation runs per object at a time; a validated result becomes newest while older reports remain in history.

---

## the agent's Discretion

- Exact implementation choices remain open where they preserve the approved AI/UI contracts, evidence-first behavior, human-confirmed lifecycle governance, and existing application integration patterns.

## Deferred Ideas

- None raised during this discussion.
