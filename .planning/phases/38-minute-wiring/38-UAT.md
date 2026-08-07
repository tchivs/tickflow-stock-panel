# Phase 38 UAT — 分钟确认接线 BT-10 (Minute Confirm Wiring)

**Phase:** 38 · **Requirements:** MN-01..04 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/38-minute-wiring/38-VERIFICATION.md` — **passed** (4/4, 42 passed 复现 + anchor 16 字节一致)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | factory — canonical 列读取 + 候选过滤 + 排序 + 缺/坏分区 fail-closed | ✅ passed | minute_loader.py (CANONICAL_MINUTE_COLS kline_sync.py:535-538, is_in, sort, 损坏→logger.warning+空帧); 8 tests incl. 结构门零写面 |
| UAT-2 | 双构造点接线 — 空湖行为字节保持 | ✅ passed | main.py:551/567 + governed_runner.py:55/72 (局部 import);byte-identical 测试 (wired vs None: required 空池/optional 保留池 × 空湖/缺分区);anchor 5 命令 16 passed 与 38-01-BASELINE 逐命令一致 |
| UAT-3 | hermetic 测试 — 截断 T-21-01 + 只读 + 报告 not_applied 不变 | ✅ passed | 真实 auction_intraday_confirm + 单点截断 ≤09:45 (600303 仅 09:50/10:00 → 落选 total==2);直接喂未截断帧 AssertionError 证明门禁有效;sha256/mtime 快照逐字节一致;not_applied anchors 5 处原样绿 |
| UAT-4 | 文档同步 — 一行状态,诚实 post-sync 语义 | ✅ passed | features.md BT-10 行内 +1「绝非盘中 09:45 即时」;deploy-verification.md D8 +1 观察项;header-drift 0 |
| UAT-5 | 全量回归 | ✅ passed | **1797 passed + 4 skipped** (10m20s, 38-02 全量跑) |

## 诚实标注

- 实盘点亮 (live 日湖写 → auction_intraday_confirm 非空) deploy-gated — 沙箱只锁空湖 fail-closed 路径 (behavior_unverified=1)。
- probe_phase13.py:59-62 第三构造点刻意不接线 (MN-02 命名范围) — 行为与接线前一致。
- 分钟历史 CLOSED (BT-10 长存) — 本 phase 交付接线机械 + 诚实注记,非分钟实现。

## Verdict

**UAT passed** — 4/4 需求通过,5 项验收标准全绿 (实盘点亮 deploy-gated 明示)。
