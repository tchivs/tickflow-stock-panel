# Phase 49 UAT — Research-Only Promotion Ticket

**Phase:** 49 · **Requirements:** AF-REQ-15, AF-REQ-17 · **Date:** 2026-08-09
**Verifier:** `.planning/phases/49-promotion-ticket/49-VERIFICATION.md` — **passed** (0 blocking human_items)

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | Compare proposal → create Promotion Ticket bound to full evidence triple | ✅ | AF-REQ-15 SC1: PromotionTicket frozen VO (candidate identity + frozen fingerprints + admission verdict + selection_oos + reviewer + expiry + idempotency_key); issue from frozen/append-only facts |
| UAT-2 | Approval refreshes evidence; stale/modified → expire/conflict; concurrent → at most one revision | ✅ | AF-REQ-15 SC2: refresh = re-read+re-verify NOT re-compute (R2); expire (re-issueable) vs conflict (hard reject) taxonomy (R1); PARTIAL UNIQUE INDEX WHERE status='consumed' + BEGIN IMMEDIATE atomic (concurrent at-most-one proven by ThreadPoolExecutor test) |
| UAT-3 | Only explicitly reviewed exact-bound ticket → immutable FactorRevision + catalog; unreviewed absent | ✅ | AF-REQ-15 SC3: consume_promotion_ticket_atomic mints NEW factor_id + revision_number=1 + alpha_promoted provenance; list_current excludes alpha_exploratory; prior runs unchanged (INSERT only) |
| UAT-4 | Action surface visibly research-only; no broker/order/portfolio/monitor/live | ✅ | AF-REQ-17 SC4: API issue/inspect/register; test_phase49_guard.py (AST import allowlist + runtime raising-fake doubles); DROP 'promotion' token only, KEEP full execution set |
| UAT-5 | Watchlist untouched; zero new deps | ✅ | git status Watchlist.tsx unmodified; zero dep file changes |

## Verdict

**UAT passed** — all 5 criteria satisfied. 848 tests passed (full research+migrations+API+guard), 0 failures, 0 blocking human_items. Foundation ready for Phase 50 (Replay Workbench & Release Hardening).
