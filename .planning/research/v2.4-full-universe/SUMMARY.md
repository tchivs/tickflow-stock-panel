# v2.4 全量数据解锁 — Milestone Summary (Scope Decision)

**Synthesized:** 2026-08-07
**Research basis:** `.planning/research/v2.4-full-universe/` (AUCTION-FULL-BACKFILL.md / REAL-COLUMN-BACKTEST.md / DEPLOY-MINUTE-LEGACY.md — 全部 FEASIBLE, 实测驱动, 2026-08-07)

## 范围裁决 (Scope Ruling)

三域研究全部 **FEASIBLE** → 4 域全 IN, 4 phases, 18 需求 (13 P1 + 5 P2)。

| Phase | 域 | 需求 | 研究裁决 (实测锚点) |
|---|---|---|---|
| 36 全量竞价回填 | R1 长作业 | FA-01..06 | 5537 宇宙 (SZ 2894/SH 2310/BJ 333), pilot mean 0.96s/请求 0×429, 写 1.15s/标的, 全湖 ~13 MB, **3.5-5.5h**; BJ 333 上游恒空 → 覆盖上限 **94.0%** |
| 37 全量真列回测重跑 | R2 回测 | RC-01..04 | 全市场 9 策略 compute **2.3s** (381,690 行实测); 指纹缺口实测: 回填后同命令重跑 reused=True 静默保留旧数据 → 必须修 |
| 38 分钟确认接线 BT-10 | R3 分钟 | MN-01..04 | seam 完整 (engine.py:154,373-392), 双构造点未接线 (main.py:562-565 + governed_runner.py:63-66), 空湖行为保持 = 纯代码增量 |
| 39 部署验证与残留 | R3 部署 | DV-01..04 | D1/D2/D4/D5/D8 沙箱 CLOSED (真实交易日); D3/D6/D7 PARTIAL; **D8 容器实测 stale** (image 08-04 vs HEAD 08-07, 4 文件 md5 DIFFER) → 沙箱可做 build+boot 预检 |

## 关键决策 (Decisions D1..D7)

- **D1**: 全量回填载体 = **沙箱 detached CLI 主跑** (网络实测可达、零 POST/reap/单飞干扰、日志落盘);API POST 备选 (超时豁免 FA-01 落地后)。
- **D2**: 长作业解阻必修 — `STALE_JOB_TIMEOUT_S=600` + 轮询端 reap_stale 联动 → API 回填 ~10 分钟自杀 (pipeline_jobs.py:29, pipeline.py:45,132,173; 合作式取消 auction_backfill.py:215-219)。修复 = per-job `timeout_s` (backfill API 21600)。
- **D3**: BJ 333 (920xxx) 上游恒空 (5 替代格式实测失败) → **覆盖上限 94.0%**, 诚实台账 (empty_response), 既有测试锚定, 绝不声称 100%。
- **D4**: `_compute_run_id` 指纹必须纳入**湖覆盖摘要** (auction_backtest.py:614-640) — 否则回填后同命令重跑 reused=True 静默保留旧数据 (实测)。先例注释 :624-628 已声明同一理由。
- **D5**: BT-10 分钟接线 = 沙箱可落地纯代码增量 (factory + 双接线 + hermetic 测试), 空湖行为字节保持;实盘点亮 (live 日湖写) deploy-gated, 诚实注记。
- **D6**: D8 = 运行中 root 陈旧容器 (共享 data/ 湖), 重建对齐属部署动作不可触碰;沙箱预检 = `docker build` HEAD + 独立端口/临时 data boot smoke (DV-01)。
- **D7**: 依赖编排 — 37 依赖 36 (湖覆盖);38/39 独立;Phase 36 代码落地后**立即 detached 启动全量回填**, 与 36-02/03 (CLI/docs/测试) 并行推进, 验证期回收结果。

## 风险与诚实约束

- 上游 3-5h 持续限速 UNKNOWN (短窗零 429) → 退避 + resume + 分批续跑兜底;宕机 → 逐 symbol 台账继续, 湖不损坏。
- 跨进程并发写无锁 (read-modify-write last-rename-wins) → 调度纪律: 回填避开 EOD run_all 窗口。
- 覆盖 0.04% → ≤94.0% 诚实翻转 (BJ 缺席明示, 不 claim 100%);intraday_confirm 52,591 行 branch=real 但 filter 不消费竞价列 — 摘要注记 (BT-10), 不静默改语义。
- 全程: 零新增运行时依赖 · 诚实 provenance (origin/empty_response/rows_present<expected) · POOL-03 零执行权 · Watchlist.tsx 零触碰。

## 里程碑形态

- 命名: v2.4 全量数据解锁 (Full-Universe Data Unlock)。
- 验收锚点: kline_auction 248 分区 × ~5204 行 (1.29M 行);backtest_results 全市场真列 run (coverage ≥0.94, EOD 329,087 不变);minute loader 接线空湖行为保持;D8 预检 build+boot 报告;后端 + 前端回归全绿。
- 部署动作 (不属本里程碑): D1/D2/D4/D5 真实交易日观察、D7 周终报告、premarket_results 生成、3018 容器重建对齐 (DV-01 仅沙箱预检配方)。
