# Phase 3: AI Analysis - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 03-ai-analysis
**Areas discussed:** Signal lifecycle governance, Default paths in existing workspaces

---

## Signal Lifecycle Governance

| Question | Options | Selected |
|---|---|---|
| Who may initiate a lifecycle transition? | System proposes, human confirms; deterministic rules automatically change state; human changes state only | System proposes, human confirms |
| What evidence threshold is required? | State-specific thresholds; uniform two-source threshold; low-threshold proposals | State-specific thresholds |
| How should outcomes and benchmarks be recorded? | Immutable auditable observation plan; globally standardized observation; continuously adjustable observation | Immutable auditable observation plan |
| What survives a rejected proposal? | Retain every review outcome; retain confirmed events only; retain anonymized rejection summary | Retain every review outcome |

**User's choice:** System-generated evidence proposals require human confirmation. Proposal thresholds differ by status; confirmation fixes an immutable 20/60/120-trading-day observation plan with its benchmark and metric. Every review outcome remains auditable, but rejected proposals never change official lifecycle state.

**Notes:** Falsification requires a pre-recorded invalidation condition or independently cross-checked contradictory evidence. Priced-in proposals require explicit price and event context.

---

## Default Paths In Existing Workspaces

| Question | Options | Selected |
|---|---|---|
| What is the default AI research entry? | Current investment object; portfolio overview; report history | Current investment object |
| What is prioritized in the first view? | Conclusion and evidence state; full report; signal history | Conclusion and evidence state |
| How are multiple reports selected? | Latest default, history can be pinned; choose history first; always follow latest | Latest default, history can be pinned |
| How do portfolio and holding analysis relate? | Explicit portfolio-to-holding drill-down; aggregate portfolio only; holding analysis only | Explicit portfolio-to-holding drill-down |

**User's choice:** Start from the active stock, account, or aggregate portfolio. Lead with conclusion plus evidence status, open the newest completed reviewable report by default while preserving selected history, and keep portfolio scope explicit before drilling into holdings.

**Notes:** Report history must not displace the active object context or silently replace a selected historical report during refresh. Account and aggregate portfolio data must never be silently mixed.

---

## Claude's Discretion

- Source admission/independence algorithms, persistence schema, graph implementation, report API shape, and component composition within the approved AI/UI contracts.

## Deferred Ideas

None.
