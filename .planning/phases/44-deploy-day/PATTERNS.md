# Phase 44: 部署日执行面 (Deploy-Day Execution) — Pattern Map

**Mapped:** 2026-08-07 · **Files:** 3 新增脚本 / 2 修改 (.env.example, docs/deploy-verification.md) · **Analogs:** 全 exact — 本阶段零新语言面, 全部镜像既有配方/惯例

## File Classification

| File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/scripts/deploy_check_connectivity.sh` (新) | 部署预检 | host → docker exec/run → 容器内 urllib → :8000 | RESEARCH 网关 live probe (urllib X-API-Key 实测) + `RUN-EVIDENCE-39-01.md` exec 模式 (只读 exec md5/探针) | exact |
| `backend/scripts/deploy_verify_endpoints.py` (新) | 200-body 验证 | python3 stdlib → app login → cookie → 3 端点 | `verify_auction_backfill.py` (只读 + 终态 JSON + 退出码) + `auction_backfill.py` (argparse + env 注入) + RESEARCH 200-body 沙箱流程 | exact |
| `backend/scripts/deploy_day_runbook.sh` (新) | D1..D8 三态判定 | bash+jq+python3 → data 目录/DB 只读 | `verify_auction_backfill.py` 三态裁决 (PASS/PARTIAL/FAIL + exit) + `deploy-verification.md` 判定表 | exact |
| `backend/scripts/deploy_rebuild.sh` (新) | 3018 rebuild 配方 | host → docker build/run/compose | `RUN-EVIDENCE-39-01.md` 全流程 (build 66s/boot 18s/md5 4/4/trap 清理) | exact |
| `.env.example` (改) | 凭证注入面文档 | — | `.env:3` UPPER_SNAKE 注释占位风格 (TICKFLOW_API_KEY=) | exact |
| `docs/deploy-verification.md` (改) | 部署文档 v2.5 节 | — | 同文件 `:217` v2.4 实测事实节 (镜像格式) | exact |

## 镜像面 1 — 39-01 RUN-EVIDENCE 预检配方 (deploy_rebuild.sh / 44-01 md5+gate 的同一配方)

`RUN-EVIDENCE-39-01.md` 是 44 期全部「预检类」脚本的母配方, 六个步骤逐字镜像 (脚本 = 配方可执行化):

1. **Baseline**: `git rev-parse --short HEAD` + `docker version` + `ss -tln` 端口面 (3018 陈旧容器持有 / **3020 必须空闲**) + stale-name guard (`docker rm -f athenaquant-preflight 2>/dev/null || true`)。
2. **Temp data copy (root 容器法)**: 宿主 `cp -r data` 不可用 (root-owned 0700 forecast-* 目录) + `sudo` 无 tty 不可用 → `docker run --rm -v data:/src:ro -v /tmp/preflight-data:/dst IMAGE sh -c 'cp -a /src/. /dst/ && chown -R 999:995 /dst'` — **源只读挂载, 零风险**; 副本 186M / 宿主可见 du 155M (root 目录宿主不可见, W4)。
3. **Build**: `docker build -t athenaquant-app:preflight .` — 冷 ~66s / warm 2.3s (39-01 / 44-RESEARCH 实测), exit 0, 记录 time + 镜像 ID。
4. **Boot**: `docker run -d --name athenaquant-preflight -p 3020:3018 -v /tmp/preflight-data:/app/data -v tiers.yaml:/app/tiers.yaml:ro` → /health 200 poll (≤120s, 实测 18-20s); 日志干净无 traceback。
5. **md5 parity**: `docker exec athenaquant-preflight sh -c 'md5sum /app/app/main.py /app/app/strategy/engine.py /app/app/jobs/daily_pipeline.py /app/app/services/preferences.py'` vs 宿主 `md5sum backend/app/...` — 4/4 表 (容器路径注意 `app/strategy/engine.py`, 不存在 `app/engine.py`)。
6. **零写哨兵 + 清理**: kline_auction 分区数 / `*.tmp` 计数不变 → `docker rm -f athenaquant-preflight` + `rm -rf /tmp/preflight-data` + `ss` 3020 释放; 镜像可留 (配方参照) 可清 (Pitfall 6)。

**诚实纪律 (母配方内置)**: 3018 陈旧容器 = 哨兵 — 只读 `docker exec` (md5/ls/probe GET) 允许, 写/重启/rm 禁止; 沙箱证的是脚本逻辑与 DTO 形状, 「部署日真实行为」绝不冒充沙箱已证。

## 镜像面 2 — deploy-verification.md 文档惯例 (v2.5 节)

- **章节标题**: `### v2.5 部署日执行面 (2026-08-07)` — 镜像 `:217` `### v2.4 实测事实 (2026-08-07)` 的位置与格式 (紧随上一节, 同层级)。
- **内容纪律**: ① 每项带来源标注 (沙箱/研究实测 vs 真实交易日观察 — 两分列, 绝不混标); ② 判据引用不复制 (D1..D8 判定表在正文, 新节只引用 + 一行语义); ③ md5 基线表用「当前 HEAD 实测值」, 不抄 39-01 过期值 (1be3288b/901d11a9 已废, 43 期改动); ④ 三态纪律 (pass/degraded/BLOCKER) 全文一致。
- **runbook 引用**: 39-03-OBSERVATION-WINDOW.md 与 deploy-verification.md 双向对齐 (执行顺序 1 D1 → 2 D4 → 3 D2+D6 → 4 D5 → 5 D7 → 6 D7 周终 → 7 D3 → 8 D8)。

## 镜像面 3 — 验证脚本语言惯例 (backend/scripts/*)

**python3 stdlib 脚本** (镜像 `verify_auction_backfill.py` + `auction_backfill.py`):
- 头 docstring: 用途 + 只读声明 + 退出码语义 + 用法 + env 覆盖 (DATA_DIR / DEP_PASSWORD / LOCAL_STOCKDB_API_KEY — **凭证从 env 读, 绝不硬编码**; auth.py 登录限流 5 次/300s → 单次尝试)。
- 骨架: `from __future__ import annotations` → argparse (`--base-url` / `--out` / `--timeout` 等) → 主流程 → **终态 JSON 台账** (stdout 或 `--out` 原子落盘) → 人类可读摘要 → `exit 0/1/2…` 语义。
- HTTP: `urllib.request` + `http.cookiejar.CookieJar` (login 的 `tf_session` HttpOnly cookie 由 jar 保存) — 零新依赖, 部署机无 pip 也可跑。
- 只读纪律: 验证脚本对数据湖零写入; backfill 触发只走 API POST 且默认 fail-closed 小范围 (全量回填绝不由验证脚本触发, 36-02 配额纪律)。

**bash 脚本** (镜像 `dev.sh`): `#!/usr/bin/env bash` + `set -euo pipefail` + `ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` + env 默认值 (`${VAR:-default}`) + 彩色 log helper (info/ok/warn/err) + `trap 'cleanup' EXIT` (预检容器/临时目录失败路径必清理, Pitfall 6)。

**容器内探测**: 单行 python3 urllib (docker exec / docker run --rm --network <net>), 判据 = **真实 200 + body 键在场** (非 TCP 通, Pitfall 1); 401 = 凭证错不重试 (StockDBAuthError 语义, 40 期契约), refused/timeout = 不可达, 三态 JSON + 退出码区分。

## 守护模式

- **3018 哨兵守卫**: 一切预检脚本默认 preflight-only (build 新镜像 + :3020 + 临时数据副本), 真实替换 (`docker compose up -d` + chown) 只在 `--apply` 显式模式并打印逐步骤供 operator 执行 — 脚本不静默替换运行中容器。
- **grep 凭证守卫**: 脚本不得含明文 key/密码 (grep -v '^#' | grep -c 'API_KEY=…8 位以上字面量' == 0); `.env` mode 600 + git-ignored (TICKFLOW_API_KEY 同纪律)。
- **分钟点亮门守卫**: 墙钟 ≥15:30 Asia/Shanghai 先验 (python3 ZoneInfo) — 盘中 09:45 判定是 [HIGH] 误判面 (Pitfall 3); 报告层 `minute_confirm` 恒 not_applied (auction_validation.py:535) **不参与** 判定, 用引擎运行结果 (auction_intraday_confirm 命中行)。
- **三态裁决**: pass / degraded (诚实 fail-closed) / BLOCKER (数据不可用但系统装作有数据 → exit 非零) — 镜像 verify_auction_backfill.py PASS/PARTIAL/FAIL。

## 关键差异点 (vs 既有面)

| 维度 | 44 期脚本 | verify_auction_backfill.py | 39-01 手工配方 |
|---|---|---|---|
| 运行面 | 部署机 + 容器内 (exec/run) | 宿主 python3 (backend venv) | 部署机手工 bash |
| 目标 | 部署日三态判定 / 连通 / 200-body | 湖六项事实 | 预检一次性 |
| 触发面 | API POST (backfill 默认 fail-closed) | 零网络 | 零 API |
| 密码面 | DEP_PASSWORD env 注入单次尝试 | N/A | N/A |

## 命名与放置惯例

- 脚本名: `deploy_<面>.{sh,py}` — `deploy_check_connectivity.sh` / `deploy_verify_endpoints.py` / `deploy_day_runbook.sh` / `deploy_rebuild.sh` (RESEARCH Wave 0 清单定稿), 全部在 `backend/scripts/` (既有脚本同目录)。
- 部署日参数: env 注入 (`DEP_PASSWORD` / `LOCAL_STOCKDB_API_KEY` / `DEP_TRADE_DATE`) + `--base-url` / `--data-dir` / `--now` (测试用时间注入) — 全部可从环境覆盖, 容忍 key/密码/网关漂移 (A1-A3)。

## Metadata

**Scope:** `backend/scripts/deploy_*.{sh,py}` · `.env.example` · `docs/deploy-verification.md` · **Patterns source:** RUN-EVIDENCE-39-01.md (全读) · deploy-verification.md (全读, v2.4 节 :217-238) · 39-03-OBSERVATION-WINDOW.md · backend/scripts/{auction_backfill,verify_auction_backfill}.py 头 · dev.sh 头 · 44-RESEARCH.md (429 行) · **Valid until:** 2026-09-06 (与 RESEARCH 同窗)
