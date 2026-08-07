# Phase 43 UAT — T-day 竞价采集 sidecar (T-Day Auction Capture)

**Phase:** 43 · **Requirements:** SDC-01..03 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/43-tday-auction-sidecar/43-VERIFICATION.md` — **PASSED** (3/3, behavior_unverified=5)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | 盘中竞价窗口采集 + 对账闭合 | ✅ passed | fetch-on-miss GET /v1/ticks 全窗口 + 完整性校验 (归属日/09:25 行/窗口阈值);staging tick_staging/date={T} 10 列 + manifest;三重对账 **22,639,818 闭合** (173×100×1308.66, 锚点重导);池 ≤200 白名单默认自选池 |
| UAT-2 | T-day 累积 + 真实列映射 | ✅ passed | promote_to_canonical 仅撮合行升湖 (555..565 谓词 + excludes_virtual 测试);逐日累积 promote_trading_day + 幂等重跑 + manifest promoted;virtual_price==kline_daily.open **1e-6 交叉验证**;unmatched 诚实缺列绝不猜 |
| UAT-3 | 诚实门 + 调度 | ✅ passed | 台账 JSONL (W-5 键集, capture_missing/reconcile_fail 告警);三 job 09:26/09:40/15:40 CronTrigger mon-fri Asia/Shanghai + _run_tracked 单飞;交易日判定 (非交易日静默) |
| UAT-4 | canonical 湖零污染 | ✅ passed | 快照行 (num_trades=0 虚拟) 绝不入 canonical;撮合行 num_trades=120 语义实锤 |
| UAT-5 | 回归面 | ✅ passed | 125 passed/1 skipped (独立核验);零新依赖;Watchlist 零触碰 |

## 诚实标注

- **live 交易日采集 deploy-gated** (Phase 44 DEP-03 D8 观测项) — 机制全落地,真实首日采集未发生。
- 「逐秒快照」按源原生 **3s 粒度**如实实施 (A1,需求文本未改,记录于 RESEARCH/VERIFICATION)。
- cross_validate_virtual_price 未接 job (工具函数,手动作业);交易日数据在场判定待首个节假日确认;num_trades 语义锚点单日单标的样本。

## Verdict

**UAT passed** — SDC-01..03 全通过,5 项验收全绿;真实竞价列 (price/vol/amount + num_trades 元数据) 自首个交易日起逐日可累积,canonical 湖零污染。
