# Phase 37 UAT — 全量真列回测重跑 (Full Real-Column Backtest Rerun)

**Phase:** 37 · **Requirements:** RC-01..04 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/37-auction-backtest-rerun/37-VERIFICATION.md` — **passed** (4/4, 20/20 tests, 独立复验)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | 指纹含湖覆盖 — 同输入+湖变 → 新 run_id;同湖 → 幂等 reused | ✅ passed | digest (37,248) == coverage 报告 (零 view/scan 漂移);rerun `298d743e8083` wrote=true;重跑同命令 → reused=True, part.parquet mtime+size 字节不变;12-hex 契约完好 |
| UAT-2 | 全市场真列重跑 — coverage 诚实翻转 + gated 策略增长 + EOD/intraday 不变 + ≤10s | ✅ passed | coverage 0.036% → **0.67% (37/5537)**, rows_present 8,951/1,373,176 诚实部分态;gated-4 hits **12 → 720** (214/336/31/139);EOD 329,087 ==;intraday 52,591 ==;实测 5.2s (≤10s 通过) |
| UAT-3 | 诚实覆盖报告 — rows_present<expected 部分态 + intraday 注记 + BT-04 9dp | ✅ passed | manifest/CLI minute_note (branch=real 仅消费 open_gap,不随湖覆盖增长);verifier 独立重算 36/36 零偏差 (<1e-9);n_missing 2,969 flagged 0 违规,永不填 |
| UAT-4 | 持久化与只读面 — run_id 目录 + API 全规模 + --force + E3 | ✅ passed | GET list 7 run_ids / detail 382,398 行 0.05s / pushdown 31 行 / 422+400 契约不变;--force CLI-only + rewritten_at 仅 force 分支;E3 守卫 7 tests 绿;零新 import |
| UAT-5 | ≥0.94 全量重跑 | ✅ **deferred (source-gated)** | 上游 403 policy-block → 诚实 0.67% 当前湖态交付;post-recovery 单命令 `scripts/auction_backtest.py --range 248` (5-10s, 零新代码) 已入 docs + runbook |

## 诚实标注

- RC-02 全量接受口径 (≥0.94) 与 FA-04 同源 (上游 403) — 同 BT-10 先例 defer;机械 (指纹 → 新 run_id → 诚实部分态报告) 全验。
- intraday_confirm 52,591 行 branch=real 但 filter 不消费竞价列 — 设计使然 (open_gap-only),注记明示,不静默改语义。
- rerun 证据含 TestClient wall-clock (只读路径,代表性)。

## Verdict

**UAT passed** — 4/4 需求通过 (RC-02 以诚实当前湖态形态交付,≥0.94 外部源 gate defer),5 项验收标准 4 通过 + 1 诚实 defer。
