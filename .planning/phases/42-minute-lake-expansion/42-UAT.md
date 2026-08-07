# Phase 42 UAT — 分钟湖扩湖 (Minute Lake Expansion)

**Phase:** 42 · **Requirements:** MIN-01..03 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/42-minute-lake-expansion/42-VERIFICATION.md` — **PASSED** (3/3, behavior_unverified=2)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | 分钟回填机制可用且幂等 | ✅ passed | backfill_minute_history 逐 symbol 幂等跳过 + merge-upsert 原子写 + 增量窗口 + fail-closed + 动态 universe;CLI `scripts/backfill_minute_driver.py`(argparse/进度 stdout/终态 dict/退出码);12 新测试含 sha256 字节级幂等;零源依赖夹具全测 |
| UAT-2 | 统计口径双口径报告 | ✅ passed | build_report coverage 双口径并列 (canonical vs minute_stats, caliber=statistical_minute_0930 绝不相加);09:30-only 过滤;amount OHLC 全等派生 (521×1328.36×100≈69,207,556 闭合)/非全等 UNKNOWN;verify [6] 并列行 |
| UAT-3 | 诚实标注 + 源 seam | ✅ passed | _MINUTE_NOTE 扩湖诚实更新 (旧 CLOSED 表述物理消失);MINUTE_SOURCE_PROFILES 4 profile (tdx has_0930_bar=False 锁死);source_label 透传 + digest source 缺省 unknown;canonical 排除 09:30 回归锁 |
| UAT-4 | 覆盖绝不高报 | ✅ passed | live verify [6]: canonical 44/5538=0.008 PARTIAL + minute_stats 0/5538=0.000 PARTIAL — 双口径如实,无 0.94 假解锁,无 100% |
| UAT-5 | 回归面 | ✅ passed | T-21-01 截断 2 passed;test_0930_excluded 1 passed;probe 15 passed/1 skipped;orchestrator 独立 54 passed (6 files);零新依赖 |

## 诚实标注

- **MIN-01 source-gated**:真实覆盖 = 源插件深度;当前 Tushare token stk_mins 1 次/小时 (两次 40203 实测) → 全量不可达。**checkpoint:human-verify 三选一待用户**: (a) 升级 token ≥200/min → 46min 量级可达成 / (b) 部署机 3018 重探源深度 (本环境海外实测不可外推) / (c) 保持机制态。机制全交付,覆盖 0.008/0/5538 如实呈现。
- 统计口径 ≠ 逐笔: 报告/DTO 层标注明确,09:30 bar 独立 caliber 绝不相加 canonical。

## Verdict

**UAT passed** — MIN-01..03 全通过,5 项验收全绿;机制就绪 + 覆盖诚实,源决策门呈现待用户。
