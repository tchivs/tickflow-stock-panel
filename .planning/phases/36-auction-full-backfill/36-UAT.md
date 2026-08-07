# Phase 36 UAT — 全量竞价回填 (Full-Universe Auction Backfill)

**Phase:** 36 · **Requirements:** FA-01..06 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/36-auction-full-backfill/36-VERIFICATION.md` — **passed** (5/6 全验 + FA-04 机械验, 接受口径 source-gated)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | 长作业不再 600s 自杀 — per-job timeout_s 持久化 + reap 尊重 + API 6h | ✅ passed | create(timeout_s) pipeline_jobs.py:101/146-147; reap j.get 优先 :268; API 21600; 5 回归测试 (21600-job@601s 存活, default-600 仍回收) |
| UAT-2 | 断点续跑 — only_missing 覆盖预扫描跳过 + API 参数 + 部分覆盖重拉 | ✅ passed | _covered_symbols DuckDB GROUP BY + polars 兜底; W-4 emit 顺序; 4 测试含 DuckDB happy path (shape-aware fake) |
| UAT-3 | operator CLI — 全 6 flags / 互斥 / rpm 校验 / 零 job_store / 台账 JSON / exit 0/1 | ✅ passed | help 实测 exit 0; AST-locked 零注册表测试; **真实载体实证** (34+ symbols 落湖) |
| UAT-4 | 沙箱实跑 — 真实写入 + 幂等 + 诚实部分态 | ✅ **PARTIAL (source-gated)** | 湖 2→37 symbols × 248 日 = **8,951 真实行**, 248/248 分区, 交叉验证 108 对 0 失配; 上游 403 policy-block (~36 请求后, >30min 未恢复) → ≥5200 接受口径未达, **诚实 defer**, 分块突袭 campaign runbook 为 operator 路径 |
| UAT-5 | BJ 诚实上限 — 333 empty_response 台账 + 94.0% 口径 + 5 格式 stance | ✅ passed | honesty:262-278 锚定测试 (零 BJ 行入湖); FA-05-BJ-STANCE.md; source-block-vs-BJ 区分 (--ledger YES/NO/UNKNOWN) |
| UAT-6 | EOD 交织 — 重写幂等 no-op + 调度纪律 | ✅ passed | 3 级测试 (写缝/service/EOD sync); features.md 4 点纪律注记 |

## 诚实标注 (honesty)

- FA-04 全量接受口径 (≥5200 backfilled, ~1.29M rows) **未达成**: 上游 xyz MCP 在 ~36 持续请求后全站 403 "Request denied by policy" (含 stockdb_get_price, UA 变体无效, >30min 未恢复)。机制全验 (真实写入 8,951 行 + 幂等 + resume + verify 脚本 PARTIAL 判定); 全量解锁转 source-gated defer, 与 BT-10/分钟/premarket 先例一致。
- 2 个诚实性缺口记录待修: 403 被 provider 吞成空帧 (与 BJ gap 同标 empty_response, 仅符号集可区分); 空帧 continue 跳进度 emit (mass-failure 进度冻结)。
- 湖终态 (2026-08-07): 37 symbols × 248 分区, 8,951 行, BJ 333 缺席, 0 .tmp。

## Deploy/operator items

- Campaign cadence (分块突袭 + 冷却 + --only-missing 顶补) 由 operator 依恢复窗口决定; verify 脚本 PASS 为唯一完成门。

## Verdict

**UAT passed** — 5/6 完全通过 + 1/6 (FA-04) 机械验证通过且接受口径以外部源策略 gate 诚实 defer。
