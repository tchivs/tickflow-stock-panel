# 44-01-SUMMARY — DEP-01 凭证/连通性前置 (wave 1, 44-deploy-day)

**Phase**: 44 部署日执行面 (DEP 部署日执行面)
**Executed**: 2026-08-07 (ExecutorP4401, wave 1)
**Plan**: `.planning/phases/44-deploy-day/44-01-PLAN.md` (T1 env+probe / T2 md5+gate / T3 detect-gateway+健壮性)
**HEAD 基线**: `0283a9f` (提交时实测; 4 运行时文件 md5 = 32468e15/4e33c236/a48c48fa/b05e01c7, 与 RESEARCH 记录的 8cbce15 基线内容一致 — docs commit 不影响 backend 内容)
**Verdict**: **DEP-01 MET** — 连通性脚本化 (三态 JSON + 退出码 0/1/2/3), env 方案落地 (.env.example 网关+key 来源注释), 对齐检查 (预检镜像 4/4 == HEAD ∧ 陈旧 3018 4/4 DIFFER 如实记录), 401 门双通过, 3018 哨兵零触碰, 零残留, 零新增依赖, Watchlist.tsx 零触碰。

## 交付物

| 文件 | 内容 |
|---|---|
| `.env.example` (改) | `LOCAL_STOCKDB_URL=` 注释: 容器内可达地址 = 桥接网关 `http://172.18.0.1:8000` (athenaquant_default 网桥网关 = 宿主侧; stockdb 在独立桥接网仅宿主发布; 容器内 127.0.0.1:8000 实测 refused; 备选 host.docker.internal 需 compose extra_hosts, operator 决策) + 部署日追加命令逐字。`LOCAL_STOCKDB_API_KEY=` 注释: 值 = stockdb 容器 env `STOCKDB_API_KEYS` 成员, 只进 .env (mode 600, git-ignored), 不入 git 不入脚本 — 与 TICKFLOW_API_KEY 同纪律 |
| `backend/scripts/deploy_check_connectivity.sh` (新) | 四模式 bash (镜像面 3 惯例: `set -euo pipefail` + trap EXIT 清理): `probe` (容器内 urllib 三态: reachable 200+SH600519 键 / auth_error 401 不重试 / unreachable refused·timeout·网络; `--container` 优先 docker exec, 否则 `docker run --rm` 临时容器; `--auto-gateway` 动态探网关) / `md5` (4 运行时文件容器内 vs HEAD 对齐 JSON 表; 容器路径 `/app/app/strategy/engine.py` 注意 — 无 `app/engine.py`) / `gate` (/health 200 ∧ validation 无 cookie 401 双通过) / `detect-gateway` (Pitfall 7 网关漂移兜底)。凭证 env-only (LOCAL_STOCKDB_API_KEY 缺省退出 3), 输出不回显 key, grep 守卫 0 明文 |

## 沙箱验证证据 (全部 live 实测)

| 项 | 期望 | 实测 | 结果 |
|---|---|---|---|
| build `athenaquant-app:preflight` (HEAD) | exit 0 | warm **2.05s** exit 0, image `9e27032406ba` (1.59GB) | PASS |
| probe 正例 (image+network, 真 key) | reachable exit 0 | `{"verdict":"reachable","code":200,"detail":"ok"}` exit 0 | PASS |
| probe 正例 (`--container athenaquant`, 3018 只读 GET) | reachable exit 0 | reachable 200 exit 0 | PASS |
| probe 反例 (错 key) | auth_error exit 1 | `{"verdict":"auth_error","code":401,"detail":"{...invalid api key...}"}` exit 1 | PASS |
| probe 反例 (`--network none` 无路由) | unreachable exit 2 | `URLError: ... [Errno 101] Network is unreachable` exit 2 | PASS |
| probe 前置错误 (缺 key / 容器不存在 / 镜像不存在 / 参数冲突) | exit 3 | 4/4 prereq_error exit 3 | PASS |
| `--auto-gateway` | 动态网关探测 | 拼 `http://172.18.0.1:8000` → reachable exit 0 | PASS |
| detect-gateway | gateway == 172.18.0.1 | `{"network":"athenaquant_default","gateway":"172.18.0.1"}` exit 0 | PASS |
| md5 `--image preflight` | aligned 4/4 | `aligned:true, match_count:4` (32468e15/4e33c236/a48c48fa/b05e01c7) exit 0 | PASS |
| md5 `--container athenaquant` (陈旧 3018) | 4/4 DIFFER 如实 | `aligned:false, match_count:0` (641003ae/165b95a7/72e17c3c/23122ca0 — **live 实测值**, 非 39-01 过期记录) exit 0 | PASS |
| gate (:3020 预检, temp 数据副本含 auth.json) | 双通过 | `{"health":"200","gate_401":"401","verdict":"pass"}` exit 0 | PASS |
| 后端回归 (既有) | 全绿 | `test_auction_backfill_full_universe.py -x`: **14 passed** | PASS |
| 凭证守卫 | 0 明文 key | `grep -v '^#' | grep -c 'API_KEY=.*[a-z0-9]\{8,\}'` == **0** | PASS |

### 零写哨兵 + 零残留

- 预检 boot: temp 数据副本 186M (`cp -a` root 容器法, 源只读挂载 + chown 999:995), `:3020` ready ~21s `/health` 200。
- 零写: temp 副本 kline_auction 248 / `*.tmp` 0 (启动前后一致 — app 对副本零写入); 真实 `data/` 哨兵 kline_auction 248 / `*.tmp` 0 不变。
- 清理后: `docker ps -a | grep -c preflight` == 0, `ss -tln | grep -c :3020` == 0, `/tmp/preflight-data` 不存在。
- 3018 哨兵: `athenaquant Up 3 days` 全程只读 exec (md5/probe GET), 无写无重启无 rm。
- 预检镜像 `athenaquant-app:preflight` 留用 (44-02/44-03 复用, 配方参照)。

## 诚实边界 / 偏差

1. **计划 verify 的负例网络选择被 live 实测推翻**: PLAN T3 verify 假设 `--network default` (默认桥) → unreachable; live 实测容器在默认桥可经宿主路由到网桥网关 `172.18.0.1:8000` (真 key → 200 reachable, 错 key → 401 auth_error) — Docker ISOLATION 不拦「到宿主自身网关 IP」的包。**unreachable 负例改用 `--network none`** (无路由 → Errno 101, 三态语义不变: 网络形态问题 ≠ 凭证问题)。脚本判据 (真实 200 + SH600519 键) 不受影响, 五连一次跑通 (reachable / auth_error / unreachable / md5 4/4 / gate pass)。
2. **部署日真实事件 = human-verify**: 脚本交付 + 沙箱验证证的是脚本逻辑与三态裁决; 部署日 operator 追加 .env 两键后的真实 probe/md5 结果属真实部署事件, 不在此冒充已证 (usage docstring 逐字列部署日步骤: printf 两行 + chmod 600 + `set -a; . ./.env; set +a` + probe 三态读法)。
3. **HEAD 基线**: 提交时 HEAD = `0283a9f` (44 期 planning docs commit); 4 文件 md5 与 RESEARCH 记录的 8cbce15 值逐字一致, md5 模式以执行时 `git rev-parse --short HEAD` 实测为准。

## 提交

```
<commit> feat(phase-44-01): DEP-01 凭证/连通性前置 — .env.example 网关定案注释 + deploy_check_connectivity.sh (probe/md5/gate/detect-gateway 四模式, 只读, 三态 JSON+退出码) + 沙箱验证 (三态五连 + md5 4/4 preflight==HEAD ∧ 陈旧 4/4 DIFFER + gate 双通过 + 零残留) + 44-01-SUMMARY
```

文件集: `.env.example` / `backend/scripts/deploy_check_connectivity.sh` / `.planning/phases/44-deploy-day/44-01-SUMMARY.md`。`frontend/src/pages/Watchlist.tsx` 未读未触 (唯一未暂存变更), `RESEARCH.md` (researcher 产物) 不入本提交。
