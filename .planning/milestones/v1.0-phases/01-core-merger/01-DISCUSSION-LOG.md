# Phase 1: Core Merger - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-07-10
**Phase:** 1-Core Merger
**Areas discussed:** Portfolio And Account Model, Alerts And Notifications, Main Workspace And Mobile Scope, Docker Compose Verification

---

## Portfolio And Account Model

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Account organization | Multi-account manual management; single-account-first; watchlist-only holdings | Multi-account manual management |
| Holding fields | Full monitoring fields; core profit/loss fields; core fields plus funds | Full monitoring fields |
| Valuation source | Shared real-time quote with freshness; daily close only; manual current price | Shared real-time quote with freshness |
| Inactive records | Disable and retain; delete directly; edit-only | Disable and retain |

**User's choice:** Manage multiple accounts manually with complete holding context, shared tickflow quotes, and recoverable inactive records.
**Notes:** Broker connectivity, transaction imports, and tax-lot accounting are deferred.

---

## Alerts And Notifications

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Management entry | Unified Monitor center; separate Portfolio alerts page; both | Unified Monitor center |
| Required channels | Feishu and Telegram; Feishu only; all PanWatch channels | Feishu and Telegram |
| Noise control | Rule cooldown and active time; cooldown only; global quiet time | Rule cooldown and active time |
| Delivery failure | Nonblocking recorded outcome; retry; rule failure | Nonblocking recorded outcome |

**User's choice:** Extend the existing monitoring flow for holding-aware rules and keep external delivery observable but nonblocking.
**Notes:** High-severity rules may bypass quiet periods; all hits remain in history.

---

## Main Workspace And Mobile Scope

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Portfolio entry | First-class Portfolio page; Dashboard module; Watchlist extension | First-class Portfolio page |
| Holdings display | Desktop table and mobile cards; cards everywhere; table everywhere | Desktop table and mobile cards |
| Mobile commitment | Responsive Portfolio and Monitor; full PWA; desktop-only | Responsive Portfolio and Monitor |
| Edit flow | Page-level dialogs; inline table editing; dedicated edit pages | Page-level dialogs |

**User's choice:** Keep a dense desktop workspace while making the Portfolio and Monitor workflows usable in a mobile browser.
**Notes:** Full PWA installation and offline behavior are deferred.

---

## Docker Compose Verification

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Test data | Offline deterministic fixtures; real market data; pure API mocks | Offline deterministic fixtures |
| Notification verification | Local test receiver; internal records only; real test channel | Local test receiver |
| Acceptance layers | API, SSE, and key browser pages; backend only; strict visual regression | API, SSE, and key browser pages |
| Isolation | Dedicated test Compose configuration; reuse daily Compose; CI-only | Dedicated test Compose configuration |

**User's choice:** Require an offline, isolated end-to-end verification path that never relies on live credentials or mutates a developer's normal data volume.
**Notes:** Browser checks cover behavior on desktop and mobile; screenshot-golden maintenance is not required.

---

## the agent's Discretion

- Choose implementation details for schema migrations, service boundaries, fixture format, visual micro-details, and adapter mapping while preserving the recorded constraints.

## Deferred Ideas

- Broker connectivity, transaction imports, realized-gain and tax-lot accounting.
- Full PWA installation and offline support.
- Notification channels beyond Feishu and Telegram.
- Strict visual screenshot regression.
