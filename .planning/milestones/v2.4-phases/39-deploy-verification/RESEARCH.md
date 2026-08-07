# Phase 39 研究 — 部署验证与残留 (Deploy Verification & Residue)

**Researched:** 2026-08-07
**Source:** `.planning/research/v2.4-full-universe/DEPLOY-MINUTE-LEGACY.md` §3.8/§4 (ResearcherV24C, confidence HIGH, 容器 md5 实测)
**Implementation-ready:** YES — D8 预检配方可行 (Dockerfile + compose 在仓库根, image 2.59GB 本地)

## Verdict

**FEASIBLE (沙箱可执行子集)** — {D1, D2, D4, D5, D8} 沙箱 CLOSED (真实交易日/部署动作); {D3, D6, D7} PARTIAL (语义已锁, 实盘观察 deploy-gated); **D8 容器对齐 = 部署动作不可触碰, 但 build+boot 预检可沙箱执行** (DV-01)。BT-10 分钟接线已由 Phase 38 交付 (MN-01..04)。

## 关键代码事实 (R3 §3.8 实测)

- **D8 stale 实证**: 容器 `athenaquant` (cb9800570dde), image `athenaquant-app:latest` **built 2026-08-04T10:59:12+04:00** vs HEAD (2026-08-07); `app/main.py`/`engine.py`/`daily_pipeline.py`/`preferences.py` **4 文件 md5 全 DIFFER** (Phase 32-34 运行时提交 08-06 晚间晚于镜像); bind 挂载共享 data/ 湖; Config.User 空 = root → **不可触碰**。
- **沙箱预检配方**: Dockerfile + docker-compose.yml 在仓库根; image 本地 2.59GB; 可 `docker build` HEAD + 独立端口 (如 3020) + 临时 data 目录起新容器做 boot smoke — 验证部署重建配方 (不能替代 D1/D2/D4/D5/D7 真实日观察)。
- **D 矩阵 (R3 §4)**: D1 09:26 premarket cron (CLOSED, 双门禁: 部署 + live 09:15-09:25; test_premarket_pool.py 690 行锁注册/隔离/诚实 skip/probe 三态); D2 15:30 EOD (CLOSED 调度观察; 机械已证 Phase 33 8日/13s; R13 锁 test_daily_pipeline_refresh.py); D3 tier-2 真列 (PARTIAL: 湖流/probe 沙箱已证; 真列被上游缺列 gate — CHART-04 stance); D4 09:26 payload (CLOSED, 双 fail-closed 锁); D5 15:40 recap+LLM (CLOSED, AI key 默认关 preferences.py:441, skip daily_pipeline.py:779-781); D6 R13 (PARTIAL, 语义锁死, ±0.1% 实盘对比 deploy-gated); D7 OQ-3 周报 (PARTIAL, ≥5 交易日); D8 容器 (CLOSED, 预检可做)。
- **premarket 双门禁**: `data/premarket_results` 沙箱不存在 (ls 实测) → 部署 + 实时数据双 gate, 诚实记录。

## 最小增量 (DV-01..04)

1. **DV-01 D8 预检**: `docker build -t athenaquant-app:preflight .` (仓库根) → 独立端口 3020 + 临时 data (cp -r data /tmp/preflight-data) 起新容器 → boot smoke: 新端点响应 (竞价回填/回测只读/验证 available) + md5 parity 报告 vs 3018 stale。**不改动运行中 3018 容器**。注意: 容器内 cwd=/app, data bind 到 /app/data — 临时 data 目录需完整 (kline_daily 248 分区 + kline_auction + 配置)。
2. **DV-02 清单刷新**: docs/deploy-verification.md 补 v2.4 实测事实 (pilot 延迟、全量回填实测配额窗口、覆盖 40/5537、容器 diff 证据、分钟接线状态); research↔docs parity 保持 (无 `## ` header 漂移, 内容保留)。
3. **DV-03 诚实缺口汇总**: premarket 双门禁 / BJ 上游缺口 / 分钟 live-day gate / AI-key 默认关 — 证据 + owner + 触发条件。
4. **DV-04 观测窗口计划**: D1..D8 post-deploy 日历 (D4 after D1, D5 after D2, D7 ≥5 交易日, D8 rebuild 时)。

## 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| docker build 在沙箱不可用/无权限 | MEDIUM | 先 `docker version`/`docker images` 验证 (image 2.59GB 已本地); 不可用 → 预检降级为配方文档 + md5 比对报告 (诚实记录) |
| 临时 data 目录不完整导致 boot 失败 | MEDIUM | cp -r 完整 data/ (134M+); boot smoke 失败 → 记录原因, 不伪造通过 |
| 3020 端口冲突 | LOW | 先检查; 用 3021/3022 备选 |
| 共享湖写风险 | LOW | 预检容器只读观察 (不跑 EOD job); 只跑 GET 端点 + boot 日志 |
| 真实交易日项 | 预期 | 全部标注 deploy-gated, 观测窗口计划成册 |
