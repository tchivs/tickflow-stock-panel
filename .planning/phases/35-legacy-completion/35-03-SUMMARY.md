# Phase 35-03 Summary — LG-02 CHART-04 stance + LG-03 deploy checklist docs

**Plan:** `.planning/phases/35-legacy-completion/35-03-PLAN.md` (Task 1 tracer + Task 2 + Task 3)
**Executor:** ExecutorP3503 · **Date:** 2026-08-06 · **Commit:** `3b59da0`

## Delivered

| Artifact | Change |
|---|---|
| `docs/features.md` | New `### 🧮 竞价列与派生列（Auction Columns & Derived Estimates）` section after 竞价复盘 (L247): 3 bullets — (1) 估算标注常态 standing stance anchored to verified UI/API labels, (2) CHART-04 defer of 实时虚拟成交列 (BT-05 branch mutual exclusion), (3) tier-2 re-eval gate (`auction_unmatched_volume` + `auction_virtual_price` → D3). Added cross-ref line at end of 竞价复盘 section (L245) + intro link (L3). |
| `docs/deploy-verification.md` | NEW — verbatim copy of `.planning/research/v2.3-data-depth/DEPLOY-CHECKLIST.md` (D1..D8 + timing table + runbook + Fail-closed 总则, zero deletions) with orchestrator-approval header: 批准 2026-08-06 (v2.1/v2.2 audit open items + Phase 27/30/31 UAT), owner 部署运维, **D3 conditional annotation** (external auction-source gate, currently unconfigured → fail-closed pass state, does not affect D1/D2/D4-D7), provenance line. |
| `docs/deployment.md` | Header cross-link: 部署验证清单见 [deploy-verification.md](./deploy-verification.md). |

## Verification (all gates green)

- `diff <(sed -n '/^## /,$p' .planning/.../DEPLOY-CHECKLIST.md) <(sed -n '/^## /,$p' docs/deploy-verification.md)` → **0 lines** (body verbatim, W-9 respected: approval header uses `>` blockquotes, no `## ` lines).
- `grep -c '^## D[1-8]' docs/deploy-verification.md` = **8**; `Fail-closed 总则` = 1; `source: .planning/research/v2.3-data-depth/DEPLOY-CHECKLIST` = 1; `D3` = 7.
- features.md: `竞价列与派生列` = 2 (cross-ref L245 + header L247), `auction_unmatched_volume` ≥1, `auction_virtual_price` ≥1, `AQ-06` = 1 (pre-existing), `PB-04` = 1 (pre-existing), `deploy-verification` = 2 (intro L3 + gate bullet L253).
- deployment.md: `deploy-verification` = 1; relative links resolve to existing file.
- ARCHITECTURE.md / backend / frontend code / .planning source: zero edits.

## Deviations

- **W-10 (plan anchor correction, T-35-03-01 integrity)**: plan cited server-side precedent `backend/app/api/pipeline.py:178`「估算, 非真实成交」 — **grep proves that file has zero matches**. Real verified anchors used instead: `backend/app/indicators/pipeline.py:160` + `backend/app/api/data.py:776` (ENRICHED_COLUMNS registry「派生未匹配金额 (估算, 非真实成交…)」) and `auction_columns.py:43`「派生估算列, 非真实成交」. 诚实缺列 gate anchored to actual `auction_columns.py:110-118` (probe×分区双闸门) + `:134-139` (keep-list 裁剪), not plan's :123-124. All anchors live-read this session.
- W-9 applied: approval header avoids `## `-prefixed lines (diff gate clean).

## Watchlist proof

`git status --short` at commit time (sibling 35-01/35-02 files present, untouched by me):

```
M docs/deployment.md
M docs/features.md
M frontend/src/components/pool-hub/StockListTable.tsx   (sibling 35-02)
M frontend/src/pages/PoolHubPage.tsx                    (sibling 35-02)
M frontend/src/pages/Watchlist.tsx                      (pre-existing, ONLY unstaged at my end)
?? backend/tests/test_daily_pipeline_refresh.py         (sibling 35-01)
?? docs/deploy-verification.md
```

`frontend/src/pages/Watchlist.tsx` was never read, touched, or committed by this executor; it remains the only unstaged change attributable to the pre-existing milestone guard.
