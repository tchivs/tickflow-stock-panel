# Phase 44 Plan Check — 部署日执行面 (Deploy-Day Execution)

**Checked:** 2026-08-07 · **Plans:** 44-01 / 44-02 / 44-03 · **Method:** goal-backward (gsd-plan-checker 惯例), 只读评审, 零代码修改
**参照物:** REQUIREMENTS.md DEP-01..04 · ROADMAP Phase 44 (4 success criteria) · 44-RESEARCH.md (429 行全读, confidence HIGH) · PATTERNS.md · orchestrator CONTEXT (3 任务 + 诚实边界, 无 CONTEXT.md 文件) · RUN-EVIDENCE-39-01.md · deploy-verification.md · 39-03-OBSERVATION-WINDOW.md · 源码锚点逐条核实 (config.py:86-93 / main.py:766-850 / pipeline_jobs.py:125 / auction_backfill.py:55-67,:355-363 / minute_loader.py:34 / auction_validation.py:535 / daily_pipeline.py:565-581)

---

## Verdict: **EXECUTABLE**

0 blockers · 4 warnings · 4 info。三 plan 覆盖 DEP-01..04 全需求: 连通性/凭证 (脚本+文档), 200-body 键形状断言 (沙箱可跑), D1..D8 三态 runbook + 分钟点亮门防误判, rebuild 配方 (预检脚本化 + --apply operator 显式替换)。诚实边界全程遵守: 3018 哨兵零触碰 (只读 exec 仅 md5/probe), 部署日真实事件 = human-check 观测记录, Watchlist.tsx 零触碰, 零新增运行时依赖。

## D0 — Multi-Source Coverage Audit (GOAL / REQ / RESEARCH / CONTEXT)

| Source | Item | 覆盖 Plan/Task | 状态 |
|---|---|---|---|
| GOAL | SC1: 凭证/连通性前置 (loopback 不通 → 网关方案实测判定) + 3018 对齐 (4 文件 md5 vs HEAD) | 44-01 T1 (网关三态探测+env 方案) + T2 (md5 4/4==HEAD / 陈旧 4/4 DIFFER) | ✅ |
| GOAL | SC2: 3 新端点 200-body 脚本化 (login cookie → 请求 → 键形状断言, 不再只验 401) | 44-02 T1 (401 先验→login→validation/backtest 键断言) + T2 (backfill {status,job_id}+W-5) | ✅ |
| GOAL | SC3: D1..D8 runbook 每项可执行 (分钟点亮门 = 15:30 后分区 ∧ auction_intraday_confirm 非空, 非盘中误判) | 44-03 T1 (runbook 三态 + 墙钟先验 + 引擎结果判定) | ✅ |
| GOAL | SC4: 3018 rebuild 对齐 (build 66s+boot 18s 预检 + root-owned 修复 + 替换流程文档化) | 44-03 T2 (deploy_rebuild.sh 预检模式 + --apply 文档化) + T3 (v2.5 节) | ✅ |
| REQ | DEP-01 (凭证/连通性 + md5 对齐) | 44-01 (T1/T2/T3) | ✅ |
| REQ | DEP-02 (200-body 脚本化) | 44-02 (T1/T2/T3) | ✅ |
| REQ | DEP-03 (D1..D8 runbook) | 44-03 T1 | ✅ |
| REQ | DEP-04 (3018 rebuild 对齐) | 44-03 T2/T3 | ✅ |
| RESEARCH | 网络实测定案: 容器内 127.0.0.1 refused / 网关 172.18.0.1:8000 200 → 网关方案 (非 host 网络) | 44-01 T1 (三态探测判据 = 真实 200 + body 键) | ✅ |
| RESEARCH | 凭证注入面: .env (600, git-ignored) → compose env_file → 容器 env; key = STOCKDB_API_KEYS 成员 | 44-01 T1 (.env.example 注释 + usage 部署日步骤) | ✅ |
| RESEARCH | md5 基线: HEAD 8cbce15 (32468e15/4e33c236/a48c48fa/b05e01c7) vs 陈旧 3018 (641003ae/165b95a7/72e17c3c/23122ca0) 4/4 DIFFER; 39-01 旧基线过期 | 44-01 T2 (只读 exec 比对) + 44-03 T3 (文档基线表) | ✅ |
| RESEARCH | 200-body 键表: validation 8 键 / backtest {runs,count}+8 键 / 详情 {manifest,stats,sample} / backfill {status,job_id}+W-5 9 键 | 44-02 T1/T2 (逐键断言 + 值集) | ✅ |
| RESEARCH | backfill 安全: 远未来窗 no_scope fail-closed 零上游; 全量绝不由验证脚本触发 | 44-02 T2 (默认 fail-closed 体 + 显式覆盖 + 双明示) | ✅ |
| RESEARCH | D1..D8 判定路径表 (数据在场 + 键形状 + 三态) | 44-03 T1 (逐项实现, ABSENT 目录诚实三态) | ✅ |
| RESEARCH | 分钟点亮门: 墙钟 ≥15:30 + 分区 + 引擎 auction_intraday_confirm; 报告层 not_applied 不参与 | 44-03 T1 (硬先验 + 引擎结果扫描 + 代码审查确认) | ✅ |
| RESEARCH | rebuild 配方: build 66s/boot 18s/md5 4/4/root 容器法/chown 999:995/trap 清理 | 44-03 T2 (全流程脚本化 + --apply 文档化) | ✅ |
| RESEARCH | root-owned 卷清单 (forecast-* 700 / ext_data+enriched 755 / ai_*.json 644) | 44-03 T2 (清单检测) + T3 (文档) | ✅ |
| CONTEXT | 3 任务: ① PATTERNS (镜像面) ② 3 PLAN (凭证连通性/200-body/D1..D8+rebuild) ③ PLAN-CHECK (verdict + B/W) | 全部交付物 | ✅ |
| CONTEXT | 诚实边界: 3018 不可触碰 (预检只在临时容器/端口); 部署日真实事件 UNKNOWN (Q3) → human-verify; 沙箱已验证 200-body 全流程 → 脚本化交付 | 44-01 (只读 exec 守卫) / 44-02 T3 (human-check 记录面) / 44-03 T2 (--apply operator) | ✅ |

**无未规划项**; 排除项 (非 gap): RESEARCH Open Q1 (专用 key 增强 → 部署后), Q2 (真实小回填 → 显式参数), Q3 (部署日 N 日期 → DEP_TRADE_DATE env + 39-03 模板), Q4 (Watchlist.tsx 本地修改 → 重建前 human 确认, 本阶段零读取零触碰), D3 条件项 (竞价源未配置 → fail-closed 通过态)。

## D1 — Goal-backward: 每 success criterion → 可观测验收 (反向无孤儿)

| ROADMAP Success Criterion | 覆盖 Plan/Task | 可观测验收 | 状态 |
|---|---|---|---|
| SC1: 凭证/连通性前置 + 3018 对齐检查完成 | 44-01 T1/T2/T3 | 容器内 172.18.0.1:8000 带 key → reachable 200 (真实 quotes); 127.0.0.1 refused 不误判; 错 key → auth_error 不重试; md5: 预检镜像 4/4==HEAD + 陈旧 4/4 DIFFER (JSON 表); gate: /health 200 + validation 401 | ✅ |
| SC2: 3 端点 200-body 脚本化 (不再只验 401) | 44-02 T1/T2 | 401 先验 3/3 → login 200+tf_session → validation 8 顶层键+coverage 两子结构 → backtest {runs,count}+count==len → 详情 {manifest,stats,sample}+sample≤20 → backfill {status,job_id}+job 轮询 W-5 9 键; 沙箱 :3020 exit 0 | ✅ |
| SC3: D1..D8 每项可执行; 分钟点亮门非盘中误判 | 44-03 T1 | D1..D8 全项三态沙箱可跑 (ABSENT 目录诚实 degraded; enriched 251 分区 pass); 台账 JSON {item,date,verdict,evidence,ts}; BLOCKER exit 2; --now 09:45 → not_before_1530 | ✅ |
| SC4: 3018 rebuild 对齐 (预检 build+boot + root-owned 修复 + 替换文档化) | 44-03 T2/T3 | preflight 模式沙箱全流程 (build/boot /health 200/md5 4/4/零残留); --apply dry-run 打印 compose up -d + chown -R 999:995; v2.5 节文档落地 | ✅ |

**反向孤儿检查:** 全部 9 任务可回溯到 DEP-01..04 与 SC1..4, 无孤儿任务; 需求覆盖 DEP-01✅ (44-01) / DEP-02✅ (44-02) / DEP-03✅ (44-03 T1) / DEP-04✅ (44-03 T2/T3)。44-02 依赖 44-01 (preflight 镜像/容器产物 + 连通性前置), 44-03 依赖 44-01/44-02 (预检配方复用 + 部署日顺序: 连通 → 200-body → rebuild → 观测窗) — 顺序链正确, 无环。

## D2 — 依赖/顺序

- **wave 1** = 44-01 (`depends_on: []`): env 方案 + 连通性探测 + md5 对齐 + 401 门; 产出 athenaquant-app:preflight 镜像 + temp 数据副本 (44-02/44-03 复用)。
- **wave 2** = 44-02 (`depends_on: [44-01]`): 200-body 脚本 — 沙箱验证复用 44-01 的 preflight 容器/镜像; 部署日顺序 = 连通性预检 green 后 (前置关系真实)。
- **wave 3** = 44-03 (`depends_on: [44-01, 44-02]`): runbook + rebuild 配方 — rebuild 预检复用 44-01 md5/容器产物; 文档引用 44-01/44-02 脚本清单。
- **文件冲突扫描**: 44-01 (.env.example / deploy_check_connectivity.sh) · 44-02 (deploy_verify_endpoints.py) · 44-03 (deploy_day_runbook.sh / deploy_rebuild.sh / docs/deploy-verification.md) — **零 files_modified 重叠**。
- 三 plan `autonomous: true` — 无 blocking checkpoint (human_verify_mode=end-of-phase → 部署日真实事件以 `<verify><human-check>` 记录面呈现, 不阻塞沙箱执行)。

## D3 — 风险覆盖 (RESEARCH 遗留逐项)

| RESEARCH 遗留 | PLAN 处理 | 状态 |
|---|---|---|
| [CRITICAL] Pitfall 1: 127.0.0.1 假象 → 连通误判 | 44-01 T1 判据 = 真实 200 + body 含 SH600519 键; 127.0.0.1 refused → unreachable 不误判 | ✅ |
| [CRITICAL] Pitfall 2: 验证触发全量回填 | 44-02 T2 默认远未来窗 no_scope fail-closed (沙箱实测); 无 symbols → 强制 fail-closed 体; 全量 = 运营 CLI | ✅ |
| [HIGH] Pitfall 3: 分钟点亮门盘中误判 | 44-03 T1 墙钟 ≥15:30 硬先验 (python3 ZoneInfo) + --now 仅测试注入; not_before_1530 拒绝态 | ✅ |
| [HIGH] Pitfall 4: rebuild 后 root-owned 卷未修 | 44-03 T2 --apply step 3 内嵌 chown -R 999:995 (root 容器法) + 清单检测 | ✅ |
| [MEDIUM] Pitfall 5: 密码/key 硬编码 | 44-01 T1/T3 + 44-02 T3 grep 凭证守卫 (env-only) + .env 600 | ✅ |
| [MEDIUM] Pitfall 6: 预检容器残留 | 44-01 T3 + 44-03 T2 trap EXIT 清理 + stale-name guard + 零残留断言 | ✅ |
| [MEDIUM] Pitfall 7: 网关 IP 漂移 | 44-01 T3 detect-gateway 动态探测 + host.docker.internal 备选文档化 | ✅ |
| Open Q1 (专用 key) | 部署后增强 — 部署日复用 STOCKDB_API_KEYS 成员 (44-01 T1), 不阻塞 | ✅ |
| Open Q2 (真实小回填) | 44-02 T2 --symbols/--start/--end 显式覆盖 (运营决策) | ✅ |
| Open Q3 (部署日 N 日期) | DEP_TRADE_DATE env + 39-03 填表模板引用 (44-03 T1) | ✅ |
| Open Q4 (Watchlist.tsx 本地修改) | 重建前 human 确认 (44-03 T2 --apply 前置注记); 本阶段零读取零触碰 | ✅ |
| A1 (网关稳定) | detect-gateway 兜底 (44-01 T3) | ✅ |
| A2 (登录密码) | DEP_PASSWORD env 注入; 沙箱 Command_123 (RESEARCH 实测) 单次尝试 | ✅ |
| A3 (key 未轮换) | 连通性预检先行 (44-01 步骤 0) — key 轮换 → 401 分类信号 | ✅ |
| A5 (首个交易日分钟分区) | 空湖 fail-closed 诚实通过态, 非 BLOCKER (44-03 T1) | ✅ |
| A6 (冷构建时长) | 预检阶段先 build (非替换窗口); 44-01 T2 记录时长 | ✅ |

## D4 — 可执行性 (行号核对证据表)

| 计划引用 | 源码实测 | 判定 |
|---|---|---|
| config.py:86-93 local_stockdb_url (缺省 127.0.0.1:8000) + local_stockdb_api_key (env LOCAL_STOCKDB_API_KEY) | :86-93 逐字 — env 键名与 .env.example 占位一致 | ✅ 一致 |
| main.py:766-850 auth 白名单 (3 新端点不在白名单 → 401) | :770-775 `_AUTH_WHITELIST_PREFIX/_EXACT` + :776-785 guest GET 集 — backfill/validation/backtest 均不在 → 401 成立 | ✅ 一致 |
| pipeline_jobs.py:125 job_id = uuid4().hex[:10] | RESEARCH 逐字 — 10 hex 断言成立 | ✅ 一致 |
| auction_backfill.py:55-67/:355-363 W-5 result 键集 (9 键含 reason) | RESEARCH 逐字 — 键集断言成立 | ✅ 一致 |
| minute_loader.py:34 只读 kline_minute/date={as_of}/part.parquet | RESEARCH 逐字 — 点亮门分区路径成立 | ✅ 一致 |
| auction_validation.py:535 minute_confirm 恒 not_applied | RESEARCH 逐字 — 报告层不参与判定的依据 | ✅ 一致 |
| daily_pipeline.py:565-581 分钟同步在 EOD/手动 | RESEARCH 逐字 — 盘中无当日分区是正常态 (墙钟先验依据) | ✅ 一致 |
| RUN-EVIDENCE-39-01.md 预检配方 (build 66s/boot 18s/md5 4/4/root 容器法/trap) | 全文件核实 — deploy_rebuild.sh 母配方 | ✅ 一致 |
| docker-compose.yml env_file .env + DATA_DIR=/app/data 强制 | :13-20 逐字 — 凭证注入链成立 | ✅ 一致 |
| .env.example:7-8 两键占位已存在 | 逐字 — 44-01 T1 只更新注释不新增键 | ✅ 一致 |
| 沙箱 Command_123 密码 (A2) | RESEARCH live 实测 (p44preflight login 成功) — temp 副本 auth.json 6042B (RUN-EVIDENCE §Baseline) | ✅ 一致 |
| 陈旧 3018 md5 4 值 (641003ae/165b95a7/72e17c3c/23122ca0) | RUN-EVIDENCE §Baseline md5 实测 — 44-01 T2/44-03 T3 引用 | ✅ 一致 |

## D5 — 决策覆盖 (orchestrator CONTEXT 决策 → 计划落地)

| 决策 | 计划落地 | 状态 |
|---|---|---|
| 网络定案: 容器内 127.0.0.1 refused → 网关 172.18.0.1:8000 (实测 200) | 44-01 T1 (判据三态 + env 方案 LOCAL_STOCKDB_URL=http://172.18.0.1:8000) | ✅ |
| 凭证: .env 追加两键 + key = STOCKDB_API_KEYS 成员 (mode 600) | 44-01 T1 (文档化 + usage 部署日步骤; 真实 .env 编辑 = 部署日 operator) | ✅ |
| 3 端点 200-body 沙箱已验证 → 脚本化交付 (不再只验 401) | 44-02 T1/T2 (键形状断言 + 值集, 沙箱 :3020 全流程) | ✅ |
| D1..D8 分钟点亮门 = 15:30 后分区 ∧ auction_intraday_confirm 非空, 非盘中误判 | 44-03 T1 (墙钟先验 + 引擎结果扫描 + 报告层不参与) | ✅ |
| rebuild: compose up -d 替换 (卷保留) + 一次性 root 容器 chown -R 999:995 | 44-03 T2 (--apply 文档化, operator 执行) + T3 (文档) | ✅ |
| md5 4/4 preflight==HEAD (daily_pipeline/preferences 因 43 期改动异于 39-01) | 44-01 T2 + 44-03 T3 (HEAD 8cbce15 实测基线, 旧值标注过期) | ✅ |
| 诚实边界: 3018 不可触碰 (预检只在临时容器/端口) | 44-01 T1/T2 (只读 exec 仅 md5/probe; preflight 独立名 :3020 + temp 副本) + 44-03 T2 (默认 preflight-only) | ✅ |
| 诚实边界: 部署日真实事件 UNKNOWN (Q3) → human-verify | 44-02 T3 + 44-03 T2/T3 (human-check 记录面; 三态记录纪律, 绝不混标沙箱) | ✅ |
| 零新增依赖 / Watchlist.tsx 零触碰 | 全 plan 威胁模型 SC 行 + D7 gate (git diff 守卫) | ✅ |

## D6 — B/W 清单

### Blockers (0)
无。

### Warnings (4)

- **W1 (44-03 T1)**: 分钟点亮门「引擎运行结果 auction_intraday_confirm 命中行非空」的具体存储形态 (EOD backtest_results vs strategy_cache) 未在 RESEARCH 单一定稿 — 计划已给双路径只读扫描 + BLOCKER 判据 (分区在但无命中且无注记); 执行时以实际存储为准, 但必须**代码审查确认不读取报告层 minute_confirm 字段** (auction_validation.py:535 恒 not_applied — W 若误读会恒灭灯)。
- **W2 (44-01 T2)**: md5 模式退出码语义 — 设计为 0 = 检查完成 (裁决读 JSON aligned 字段), 1 = 无法完成; 与 RESEARCH「BLOCKER exit 非零」的 runbook 语义不同 (对齐 DIFFER 不是脚本失败)。执行时勿混用: runbook (44-03 T1) BLOCKER → exit 2; md5 检查 (44-01 T2) DIFFER → exit 0 + aligned=false。verify 命令已按此写 (`jq -e '.aligned == false'` 为正例)。
- **W3 (44-02 T2)**: job 轮询终态在沙箱实测为 failed + reason source_unavailable (fail-closed 诚实终态) — 断言写 `succeeded or failed` (不锁死 succeeded), 否则部署日空窗期必红。部署日若真实小回填成功 → succeeded, 键集断言不变。
- **W4 (44-03 T2)**: `--apply` 的 chown 目标 `-R 999:995` 覆盖整个 data 根 — 与 39-01 实测同款 (宿主 orca 属主), 但部署日数据在重建窗口可能新增 root 文件 (RESEARCH Runtime State 明示「容器停止后以新容器复核」) — 计划已让 --apply step 3 前先跑 root-owned 清单检测再 chown; operator 确认清单后执行。

### Info (4)

- **I1**: 44-02 沙箱登录用 Command_123 (RESEARCH A2 实测) — temp 副本 auth.json 6042B 含其 hash; 部署日用 .env AUTH_PASSWORD 注入, 若用户已改密码 → login 401 → exit 2 单次尝试 (限流不锁死), 属 A2 缓解路径已覆盖。
- **I2**: 44-03 T2 preflight 模式可 `--no-build` 复用 44-01 构建的 athenaquant-app:preflight (md5 4/4 == HEAD 校验后才复用) — 三 wave 顺序执行下避免重复 66s 冷构建。
- **I3**: 3018 容器不可触碰原则下, 陈旧 3018 的「真实 200-body」不在本 phase 任何沙箱任务内 (哨兵零写) — 部署日重建后由 44-02 human-check 完成, 与 RUN-EVIDENCE-39-01「200-body 留部署日」立场一致。
- **I4**: 部署日执行顺序 (44-01 连通预检 → 44-03 --apply 重建 → 44-02 :3018 200-body → 44-03 runbook 观测窗) 与 ROADMAP 需求序 (DEP-01..04) 及 39-03 OBSERVATION-WINDOW 日历一致; runbook 的 D8 rebuild 项由 deploy_rebuild.sh 承接。

## D7 — 执行顺序建议

```
Wave 1:  44-01 (env 方案 + 连通性探测三态 + md5 对齐 + 401 门)   ← 无上游; 产出 preflight 镜像/temp 副本
Wave 2:  44-02 (deploy_verify_endpoints.py 200-body 键断言)      ← 依赖 44-01 预检产物 + 连通性前置
Wave 3:  44-03 (runbook 三态 + rebuild 配方 + v2.5 文档节)       ← 依赖 44-01/44-02 (配方复用 + 脚本清单)
```

**Phase gate:** wave 3 合并后 — runbook 全项三态 + rebuild preflight 全流程 + v2.5 节 grep 对齐三连绿 + `docker ps | grep -c preflight` == 0 + `ss -tln | grep -c :3020` == 0 + `git diff --stat frontend/src/pages/Watchlist.tsx` 零改动 → `/gsd-verify-work`。部署日 human-check: --apply 替换 → :3018 200-body 全流程 → D1..D8 观测窗逐日三态 (39-03 日历)。
