# Phase 39 模式映射 (Patterns)

**Mapped:** 2026-08-07 (orchestrator, from R3 doc + repo reads)

| # | 需求对象 | 现有模式 (file:line) | 复用方式 |
|---|---|---|---|
| 1 | D8 预检 (DV-01) | Dockerfile + docker-compose.yml (仓库根); image `athenaquant-app:latest` 2.59GB 本地 (R3 §3.8 实测); 3018 容器 `athenaquant` root-owned | `docker build -t athenaquant-app:preflight .` → 独立端口 3020 + `/tmp/preflight-data` (cp -r data/) → boot smoke (GET /health 或新端点) + 4 文件 md5 比对报告 |
| 2 | 新端点验证 (DV-01) | POST /api/kline/auction/backfill (FA-01); GET /api/research/backtest/{run_id} (RC-04); GET /api/research/auction/validation (BT-08) | 预检容器内 curl 探测 (只读 GET; backfill 端点仅探测路由存在 — 不触发真实回填) |
| 3 | 清单刷新 (DV-02) | docs/deploy-verification.md (Phase 35 成册, D1..D8 + fail-closed 总则 + 批准横幅, 无 `## ` 行) | 追加 v2.4 实测小节 (配额/覆盖/容器 diff/分钟接线); header-drift gate `grep '^[+-]## '` (W1 38-03 教训) |
| 4 | parity 检查 (DV-02) | `.planning/research/v2.4-full-universe/DEPLOY-MINUTE-LEGACY.md` ↔ docs/deploy-verification.md (Phase 35 逐字节一致先例) | diff 从 `## ` 起 = 0 行; 内容保留 |
| 5 | 缺口汇总 (DV-03) | FA-05-BJ-STANCE.md (BJ 5 格式); features.md AQ-11/premarket gap 段 (Phase 33 PB-04); _MINUTE_NOTE (BT-10) | 新汇总文档 (docs/ 或 .planning) 引用既有证据, 不重复造轮子 |
| 6 | 观测窗口 (DV-04) | D 清单 sequencing (Phase 35: D4 after D1, D5 after D2, D7 ≥5 交易日) | 日历表 (交易日 N, N+1, ...) + owner + 触发条件 |
| 7 | 测试惯例 | 沙箱 docker 命令无 pytest; 清单 gate 用 grep; 诚实记录 | 预检报告 JSON/MD 落 .planning/phases/39-*/RUN-EVIDENCE |
| 8 | 契约 | 3018 容器绝不触碰; 预检容器零写共享湖 (只读 GET) | boot smoke 仅 GET + 日志; 不注册调度器/不跑 job |

## 契约

- 预检容器: `docker run -d --name athenaquant-preflight -p 3020:3018 -v /tmp/preflight-data:/app/data -v /home/orca/source/AthenaQuant/tiers.yaml:/app/tiers.yaml athenaquant-app:preflight` (镜像 EXPOSE 端口以 Dockerfile 为准 — 按实际调整)。
- md5 比对: 预检容器内 4 文件 vs HEAD — 相等 = 配方有效; 不等 → 记录 (不伪造通过)。
- 零共享湖写: 预检容器用 /tmp/preflight-data 独立拷贝; 不触碰 data/ 原目录。
- DV-03/DV-04 文档放 docs/ 或 .planning — 按 plan 裁决, 与 DV-02 无文件冲突。
