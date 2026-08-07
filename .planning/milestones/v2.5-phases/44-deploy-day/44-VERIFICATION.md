---
phase: 44-deploy-day
verified: 2026-08-07
status: passed
score: 4/4 DEP requirements — DEP-01/02/03/04 verified (0 blockers; 部署日真实事件 = human-verify 记录, 7 human_items 全为部署日/交易日观测面, 无代码缺陷)
overrides_applied: 0 — 提交集 5747b9a..6897161 未改动 REQUIREMENTS.md/ROADMAP.md 文本; DEP-01 网络负例由 `--network default` 改 `--network none` 为沙箱实测推翻计划假设 (44-01-SUMMARY 诚实边界 §1, 脚本三态语义不受影响)
human_verification: 7 items (部署日 .env 追加两键 + 真实 probe 三态 / --apply 五步 operator 手动执行 / 3018 重建后 200-body 全流程 / D1..D8 观测窗真实交易日逐项 / minute_light 15:30 后真实点亮 / D7 连续 5 交易日周终 / D3 竞价源接入条件项)
---

# Phase 44 Verification — DEP 部署日执行面 (DEP-01..04)

**Verifier:** VerifierP44 · **Date:** 2026-08-07 · **Scope:** `.planning/REQUIREMENTS.md` DEP-01..DEP-04 (Phase 44), 提交集 `5747b9a..6897161` (5 commits: 44-01 `5747b9a`, 44-02 `73f082d`+`9965087`, 44-03 `d52418a`, RESEARCH landing `6897161`).
**Method:** 逐需求脚本/文档全文审查 + 独立 live 核验 (HEAD md5 4/4、陈旧 3018 容器只读 md5 4/4 DIFFER、pytest 14 绿、bash -n ×3 + py_compile、--help/--dry-run 实测、runbook 只读 dry-run 实跑、凭证守卫 grep、diff 集完整性) + 沙箱证据采信 (44-01/02/03-SUMMARY, 本 verifier 只读核验不重复起容器)。**NEVER read `frontend/src/pages/Watchlist.tsx`** (仅经 git log/diff/status 核验零触碰)。3018 容器只读 (docker exec 仅 md5sum, 无写无重启无 rm)。

## Verdict: **PASSED**

DEP-01 凭证/连通性前置 (三态 probe + md5 对齐 + 401 门 + 网关探测) / DEP-02 200-body 验证脚本 (401 先验 3/3 → login → 3 端点键形状 → job 轮询 W-5, fail-closed 零上游) / DEP-03 D1..D8 runbook (三态判定 + 分钟点亮门 + JSON 台账 + BLOCKER exit 2) / DEP-04 3018 rebuild 配方 (preflight build→boot→md5 4/4→零残留 + --apply 五步文档化 + chown 流程)。零新依赖 (diff 集 10 文件, 0 依赖文件), Watchlist 零触碰 (44 commits 不含, 工作树未暂存为用户既有改动), 3018 容器全程只读 (Up 3 days 未动), :3020 零残留 (无监听/无 preflight 容器/无 tmp 副本), 凭证守卫 0 明文。所有部署日真实事件如实标注 human-verify, 绝不冒充沙箱已证。

---

## 1. 守卫核验 (guard rails)

| 守卫 | 命令 (本 verifier 亲自跑) | 结果 |
|---|---|---|
| 零新增依赖 | `git diff --name-only 0283a9f..HEAD \| grep -cE "(requirements\|pyproject\|Pipfile\|poetry\|package.json)"` + deploy_verify_endpoints.py imports 审查 | **0** — diff 集 10 文件 (.env.example + 4 脚本 + docs + RESEARCH + 3 SUMMARY) 零依赖文件; verify 脚本 imports 全 stdlib (urllib.request/http.cookiejar/json/argparse/time/os/sys/re/datetime/pathlib) |
| Watchlist 零触碰 | `git log --oneline --all -- frontend/src/pages/Watchlist.tsx` + `git status --short` + `git diff --name-only 0283a9f..HEAD` | 最近 commit = c9f01ba (44 期之前); 44 提交集 0 匹配; 工作树唯一未暂存 ` M Watchlist.tsx` = 用户既有改动, 本 verifier 未读取该文件 |
| 3018 容器未触碰 | `docker ps -a` + 只读 `docker exec athenaquant md5sum …` | `athenaquant Up 3 days` (与 44-01 哨兵声明逐字一致); 本 verifier 仅 1 次只读 exec; 无 rm/restart/write; preflight 容器 0 |
| :3020 无残留 | `ss -tln \| grep :3020` + `docker ps -a \| grep -c preflight` + `ls -d /tmp/preflight-data*` | 0 监听 / 0 preflight 容器 / 无 tmp 副本目录 (3018 在听, 3020 无) |
| 凭证守卫 | 4 脚本 + .env.example grep 硬编码键模式 `(API_KEY\|PASSWORD)[ =:]['\"]?[A-Za-z0-9]{8,}` | 4 脚本各 **0**; .env.example 键值行 **0** — 凭证 env-only (LOCAL_STOCKDB_API_KEY 缺省 exit 3; DEP_PASSWORD 缺省 exit 3), 输出不回显 key (probe detail 截断 160 字符, 台账无凭证) |
| 提交集完整性 | `git show --stat` 逐 commit | 5 commits 文件清单与 claim 完全一致, 无越界文件 (RESEARCH.md 独立 landing commit) |

## 2. 逐需求证据 (REQ-by-REQ)

### DEP-01 — 凭证/连通性前置 — **PASS**

证据 (.env.example 全文 + deploy_check_connectivity.sh 全文 + bash -n + HEAD/stale md5 live 实测 + 44-01-SUMMARY 沙箱):

- **env 方案落地** (.env.example): `LOCAL_STOCKDB_URL=` 注释逐字定案 — 容器内可达 = 桥接网关 `http://172.18.0.1:8000` (athenaquant_default 网桥网关 = 宿主侧; stockdb 独立桥接网仅宿主发布; 容器内 127.0.0.1:8000 实测 refused; 备选 host.docker.internal 需 compose extra_hosts, operator 决策) + 部署日追加命令 `printf … >> .env`; `LOCAL_STOCKDB_API_KEY=` 注释 = 值取 stockdb 容器 env `STOCKDB_API_KEYS` 成员, 只进 .env (mode 600, git-ignored), 不入 git 不入脚本 — 与 TICKFLOW_API_KEY 同纪律。
- **四模式 + 三态退出码** (脚本全文): `probe` — 容器内单行 python3 urllib, 判据 = 真实 200 + body 可解析 JSON + 含 SH600519 键 (非 TCP 通); verdict ∈ {reachable(200+键), auth_error(401, 不重试), unreachable(refused/timeout/Errno 101), prereq_error(exit 3)} → 退出码 0/1/2/3 逐 case 映射; `--container` 优先 docker exec 否则 `docker run --rm` (退出即删); `--auto-gateway` 动态探网关拼 `http://<gw>:8000` (与 --base-url 互斥 → exit 3); `md5` — 4 运行时文件 (main.py / strategy/engine.py / jobs/daily_pipeline.py / services/preferences.py, 容器路径 `/app/app/…` 注意无 app/engine.py) vs HEAD 逐行 md5, JSON `{aligned, match_count, files[]}`, exit 0 = 检查完成 (对齐与否读 JSON 裁决 — 与 claim「md5 对齐与否读 JSON 裁决」一致); `gate` — /health 200 ∧ validation 无 cookie 401 双通过, 任一不符 exit 1; `detect-gateway` — `docker network inspect` IPAM gateway, 解析失败 exit 1。`die3` 统一 JSON + exit 3 (docker 不可用 / 容器镜像缺失 / 缺 key / 参数冲突)。
- **HEAD md5 基线 live 核实**: 当前 HEAD `6897161` 实测 `32468e1554898be3ed1a09ec7ac42e1b / 4e33c236ef5b0cb6c6ea6c6c03e6c35a / a48c48fab17097fbbe9aab4d022717b9 / b05e01c72a57eaa0a6076d1b6b216561` — 与 claim 短值 32468e15/4e33c236/a48c48fa/b05e01c7 逐字一致, 与 v2.5 文档基线一致。
- **陈旧 3018 对齐 live 核实** (只读 docker exec): `641003ae8faab1c67201e9d2754da766 / 165b95a71850f71356766c0bb7fb974a / 72e17c3c2592570a9ec563ab040b631c / 23122ca0141152875091bdf83c152e46` → 4/4 DIFFER, 与 claim 短值 641003ae/165b95a7/72e17c3c/23122ca0 一致 → 「重建确有必要」成立。
- **沙箱证据** (44-01-SUMMARY, 采信): probe 五连 (正例 200 exit 0 / 错 key 401 exit 1 / `--network none` Errno 101 exit 2 / 前置 4/4 exit 3 / --auto-gateway 拼 172.18.0.1:8000 reachable), detect-gateway = `172.18.0.1`, gate 双通过, md5 preflight 4/4==HEAD ∧ 陈旧 4/4 DIFFER, 预检镜像 9e27032406ba 1.59GB, 14 回归绿, 零写哨兵 (temp 副本 kline_auction 248/`*.tmp` 0 前后一致), 清理后 preflight 容器 0/:3020 0。

### DEP-02 — 200-body 验证脚本 — **PASS**

证据 (deploy_verify_endpoints.py 全文 + py_compile + --help 实测 + 44-02-SUMMARY 沙箱):

- **401 先验 3/3 硬门**: validation GET / backtest GET / backfill POST 无 cookie 均 `expect_401=True` 请求, 任一非 401 → ScriptError(1)「认证门失效」立即中止; 台账 `auth_401` 完整端点路径键 ×3。
- **真实登录**: `DEP_PASSWORD` env 注入 (缺省 exit 3), POST /api/auth/login 单次尝试, 断言 200 + {ok, authenticated} 双 true + `tf_session` cookie 捕获 (http._jar 直查); 401 → ScriptError(2) 即停 (auth.py 5 次/300s 锁不触发); 429 尊重 Retry-After 重试 1 次 (Phase 40 契约), 仍 429 → exit 3。
- **validation 键形状** (沙箱实测契约): 顶层 8 键 (data_gate/empty_reason/generated_at/window/probe/coverage/skipped_ids/strategies) + data_gate ∈ {available, empty} + coverage.symbols 5 键 + coverage.minute_stats 恰 11 键 (len+键集双断言) + caliber == statistical_minute_0930 + window 4 键 {requested_start, requested_end, effective_start, effective_end} (RESEARCH 简写 requested/effective 实测修正, 44-02 偏差 #2 诚实记录) + strategies list (available 时非空)。
- **backtest 键形状**: {runs, count} + count == len(runs) + 每 run 8 键 + run_id `^[0-9a-f]{12}$`; 首条详情 {manifest, stats, sample} + stats 4 键 + sample ≤ 20 + manifest.run_id == run_id; 无 run → `{skipped: "no_runs"}` 诚实空态不伪造。
- **backfill fail-closed + 零上游保证**: 默认体 = 远未来窗 `{"symbols":["600519.SH"],"start":"2099-01-01","end":"2099-01-02"}` → 无上游可查 (no_scope/source_unavailable) — 构造层面零上游消耗; 断言 {status ∈ {started, reused}, job_id `^[0-9a-f]{10}$`} → 2s 轮询至终态 → W-5 8 键 + fail-closed 体强制 reason 键 (9 键); **requested 值如实记录不锁死** (沙箱实测 requested=0 为最强零放大证明, 台账原样落盘); 显式触发 = --symbols/--start/--end 三参数齐全才生效 (格式 `^\d{6}\.(SH|SZ|BJ)$` + 上限 6000 + 日期顺序), 缺任一 → warning + 强制默认 fail-closed 体; 全量 5537 回填 = 运营手动 CLI, 脚本拒绝触发 (36-02 配额纪律 docstring+台账双明示)。
- **退出码 + 台账**: 0 全过 / 1 断言失败 (含缺键明细) / 2 认证失败 / 3 运行错误 — main() 返回路径逐支核实; 台账原子落盘 (tmp + os.replace), body 摘录 _mask_body 无凭证。
- **零新依赖**: imports 全 stdlib (见守卫表)。
- **沙箱证据** (44-02-SUMMARY, 采信): :3020 全流程 exit 0 (401 3/3 → login tf_session → validation 8 键 → backtest {runs,count}+sample → backfill W-5 9 键 reason=source_unavailable requested=0); 错密码 exit 2 且 login 恰 1 次 (docker logs delta=1); refused exit 3; 3 auto-fixed 偏差 (coverage.symbols 断言层级 / window 键契约 / set 序列化) 全部编码面修复后沙箱重跑 exit 0。

### DEP-03 — D1..D8 runbook 脚本化 — **PASS**

证据 (deploy_day_runbook.sh 全文 + bash -n + 只读 dry-run 实跑 + 44-03-SUMMARY 沙箱):

- **三态判定语义** (头注释): pass (证据齐) / degraded (诚实 fail-closed) / BLOCKER (装作有数据/隔离破坏/空断言 → exit 2) + 专用诚实态 (not_before_1530 / empty_lake_fail_closed / conditional_not_configured / skipped / skipped_no_data / pending_human — 均 exit 0)。
- **D1** premarket part.json 键形 (window==pre_open ∧ provisional==true ∧ computed_at/probe/degraded 在场) → pass; ABSENT → degraded 诚实 (部署日 09:26 job 首建); **隔离断言** = strategy_cache.json / screener_results mtime ∈ 当日 09:00-09:35 → BLOCKER (09:26 落盘污染)。
- **D4** alert_events preopen 行 (event_json LIKE preopen/pre_open 或 rule_id LIKE) → 0 行 skipped; event_json change_pct 非 None → BLOCKER (EOD 列禁用破坏); provisional/degraded 键齐全 → pass; DB 缺 → degraded。
- **D2** enriched 分区行数 (polars 读, 不可读 → degraded) + 0 行 → BLOCKER (空断言) + screener snapshot_origin=="eod" → pass。
- **D6** enriched 手动均值 (当日 vs 前一交易日 close 环比) vs 复盘归档 Block 3 avg_change_pct 差 ≤0.1% → pass, >0.1% → BLOCKER (R13 mismatch); 归档无/不可解析 → degraded + pending_human。
- **D5** 复盘归档当日条目 + 面板三块源在场检查 (kline_auction / enriched / premarket) → 3/3 pass, 缺块 degraded 带注记; 引用切片外数字 → pending_human 明示不可程序判定。
- **D7** drift.jsonl 双 kind (gn_ths/hy_ths) 当日行 + ext_history 双分区 + manifest → pass; **零副作用断言** = ext_data 当日写入数 ≠ 0 → BLOCKER; 未运行 → degraded 诚实。
- **D8** 三闸门: 09:26 采集 (tick_staging 分区 + manifest completeness.ok=true → pass / 缺 → reason 透传 degraded) / 09:40 对账 (NOW_MIN≥580, closed 断言 ok==requested≠0 → pass; skipped=no_data → skipped_no_data 零告警; reason → degraded) / 15:40 提审 (NOW_MIN≥940, kline_auction 当日分区 → pass); 合并判定 BLOCKER > skipped_no_data > degraded > pass 优先级; <09:40 只报采集。
- **分钟点亮门** (独立 item): 墙钟 <930min (15:30) → `not_before_1530` 拒绝态 (防盘中误判); 分区缺/0 行 → empty_lake_fail_closed 诚实通过态; 分区在场 → **扫描引擎运行结果** backtest_results manifest/part.parquet 中 auction_intraday_confirm 命中行非空 → lit; 在场无命中且无 minute_note 注记 → BLOCKER; 有注记 → degraded。**报告层 minute_confirm 不参与** (auction_validation.py:535 恒 not_applied, 代码审查确认扫描对象为引擎结果) — 判据与 REQUIREMENTS「15:30 后分区存在 ∧ auction_intraday_confirm 非空, 非盘中误判」逐字对齐。
- **D3** 条件项: kline_auction 分区缺 → conditional_not_configured 通过态; 真列 (auction_unmatched_volume/virtual_price) 在场 → conditional_available。
- **台账 + 退出码**: JSON `{item, date, verdict, evidence, ts}` 键集 (dry-run 实测逐条输出); BLOCKER_COUNT>0 → exit 2, 否则 exit 0; --out 原子写 (tmp.$$ + mv + chmod 600); --now 仅供测试 (部署日绝不使用, 时钟用 Asia/Shanghai zoneinfo); 只读纪律 = 唯一写面 --out。
- **只读 dry-run 实跑** (本 verifier, 真实 data 目录, 无 --out): exit 0, 9 项全部诚实态 (d1 degraded / d4 skipped / d2 degraded / d6 degraded / d5 degraded / d7 degraded / d8 degraded / minute_light not_before_1530 / d3 conditional_not_configured), 0 BLOCKER, 零写面 — 脚本真实可执行且诚实。
- **沙箱证据** (44-03-SUMMARY, 采信): fixture 三态全项 (D1 pass/BLOCKER 隔离、D2 5293 行 pass/0 行 BLOCKER、D4 pass/skipped/degraded、D5/D6 degraded+手动均值 0.005313、D7 pass/BLOCKER 零副作用、D8 三闸门 pass/skipped_no_data/degraded、minute_light lit/not_before_1530/empty_lake_fail_closed/BLOCKER、D3 双态), BLOCKER 汇总 exit 2, 台账键集齐全, 零写入哨兵 (kline_auction 248→248, *.tmp 0→0)。

### DEP-04 — 3018 rebuild 对齐 — **PASS**

证据 (deploy_rebuild.sh 全文 + bash -n + --preflight --dry-run / --apply --dry-run 实测 + docs/deploy-verification.md v2.5 节 grep + 44-03-SUMMARY 沙箱):

- **preflight 模式** (零触碰 3018 陈旧容器): ① baseline — HEAD 实测 + 端口面 (3018 陈旧哨兵允许在位, 预检端口必须空闲 → 被占 exit 1) + stale-name guard (docker rm -f athenaquant-preflight 清理上次残留, 非 3018 容器) + 零写哨兵基线 (真实 data 目录 kline_auction 分区数 / *.tmp 计数, root-owned 目录 find `|| true` 防 pipefail 误杀 — 44-03 偏差 #2 修复面) → ② temp 副本 (宿主 cp 优先; root-owned 0700 阻挡 → root 容器法 `docker run --rm -v 源:/src:ro` cp + `chown -R 999:995`) → ③ build (计时 + 镜像 ID) → ④ boot (`docker run -d -p 3020:3018 -v temp:/app/data -v tiers.yaml:ro` + /health poll ≤120s) → ⑤ md5 parity 4/4 (容器路径注意 app/strategy/engine.py) → ⑥ 清理 (rm 容器 + rm -rf temp) + JSON 台账 {mode,head,build_s,boot_s,health,md5,residue,zero_write,image_id,ts} → 全绿门 (MATCH==TOTAL ∧ HEALTH==200 ∧ ZERO_WRITE==ok, 否则 exit 1)。
- **--apply 模式** (部署日 operator human-check, 绝不静默替换): 打印五步 — step1 preflight 全绿为前提 / step2 `docker compose up -d` (bind 卷 ./data:/app/data + tiers.yaml 保留, 数据天然保留零迁移) / step3 root 容器 `chown -R 999:995 /dst` (root-owned 卷修复, sudo 无 tty fallback, 39-01 W4 同因) / step4 md5 parity 对齐确认 / step5 /health 200 + deploy_verify_endpoints.py --base-url :3018。
- **--preflight --dry-run 实测**: exit 0, 打印 build/run/exec/cleanup 4 条命令; **--apply --dry-run 实测**: `docker compose up -d` + `chown -R 999:995` grep == 2 (与 44-03 claim 一致)。
- **docs/deploy-verification.md v2.5 节** (grep 核实): `### v2.5 部署日执行面` 锚点 1; HEAD md5 4 值 = live 实测 (32468e15…/4e33c236…/a48c48fa…/b05e01c7…); 陈旧 4 值 (641003ae…/165b95a7…/72e17c3c…/23122ca0…) 仅「陈旧 3018 实测」语境; 连通性定案 172.18.0.1 + 凭证链 (stockdb STOCKDB_API_KEYS 成员 testkey123 仅文档语境 — 非脚本硬编码); 200-body 沙箱实测段; 脚本清单 4 项 (grep 各 2-3 次引用); D1..D8 判定一行语义 + 分钟点亮门逐字判据; root-owned 卷清单 (forecast-* 700 / ext_data+kline_daily_enriched 755 / user_data/ai_*.json 644) + chown 流程; 执行顺序 ①..⑤; 诚实标注 (部署日真实事件绝不混标沙箱已证)。
- **沙箱证据** (44-03-SUMMARY, 采信): run 2 全绿 (build warm 1s / boot 17s / /health 200 / md5 4/4==HEAD / residue {0,0,0} / zero_write ok / exit 0); 3018 陈旧哨兵零触碰; 宿主 cp 被 root-owned 0700 阻挡 → root 容器法 fallback 实测触发; 清理后 preflight 0 / :3020 0。

## 3. 独立测试跑 (本 verifier)

```
$ cd backend && .venv/bin/pytest tests/test_auction_backfill_full_universe.py -q
14 passed in 1.56s
```

| 核验项 | 命令 | 结果 |
|---|---|---|
| 回归套件 | pytest tests/test_auction_backfill_full_universe.py -q | **14 passed** (与 44-01/02/03 各 wave 声明一致) |
| 脚本语法 | bash -n ×3 (connectivity/runbook/rebuild) + python3 -m py_compile verify_endpoints | **4/4 OK** |
| 脚本可用性 | connectivity help / rebuild --preflight --dry-run / rebuild --apply --dry-run / verify_endpoints --help | 全 exit 0, 输出与用法契约一致 |
| runbook 只读 dry-run | `deploy_day_runbook.sh --item ALL` (真实 data 目录, 无 --out) | exit 0, 9 项诚实态, 台账键集 {item,date,verdict,evidence,ts} 逐条输出 |
| HEAD md5 | md5sum 4 文件 @ HEAD 6897161 | 32468e15/4e33c236/a48c48fa/b05e01c7 — 与 claim + v2.5 文档一致 |
| 陈旧容器 md5 | docker exec athenaquant (只读) | 641003ae/165b95a7/72e17c3c/23122ca0 — 4/4 DIFFER 与 claim 一致 |
| 容器/端口状态 | docker ps -a / ss -tln | athenaquant Up 3 days (哨兵未动); :3020 无监听; preflight 容器 0; /tmp/preflight-data* 无 |
| 凭证守卫 | grep 硬编码键模式 (4 脚本 + .env.example) | 0/0/0/0 + 0 |
| 依赖守卫 | git diff --name-only 0283a9f..HEAD grep 依赖文件 | 0 |

沙箱重跑说明: 按只读核验纪律 (可跑 pytest + dry 检查, 不实际起容器), probe 五连/gate/detect-gateway/200-body 全流程/rebuild run 2/runbook fixture 三态等 live 容器证据采信 44-01/02/03-SUMMARY (同一会话 Executor 实跑记录, 与本 verifier 的 md5 实测交叉印证 — 陈旧容器 md5 值逐字节一致, HEAD 基线逐字节一致)。

## 4. 诚实性专项核验

| 专项 | 证据 | 结果 |
|---|---|---|
| 部署日真实事件 = human-verify, 不冒充已证 | 44-01-SUMMARY 诚实边界 §2 (部署日 operator 追加 .env 两键后的真实 probe/md5 属真实部署事件, usage docstring 逐字列步骤) / 44-02 coverage `D-DEP02-deployday` human_judgment:true (data_gate/coverage 真实值如实记录, 绝不回填假值) / 44-03-SUMMARY 诚实边界 (部署日真实事件 = 真实交易日/部署动作观测) / v2.5 诚实标注 (沙箱证脚本逻辑与 DTO 形状, 绝不混标) | **通过** |
| backfill requested=0 零上游诚实 | 默认体 = 2099 远未来窗 (构造零上游); 脚本不锁 requested 值, 台账原样落盘 (沙箱实测 source_unavailable/requested=0 如实记录); 全量 5537 = 手动 CLI 拒绝触发 (36-02 配额纪律) | **通过** |
| 分钟点亮门不误判 | 墙钟 <15:30 → not_before_1530 拒绝态; 判定对象 = 引擎运行结果 (backtest_results manifest/part.parquet 中 auction_intraday_confirm 命中), 报告层 minute_confirm (恒 not_applied) 明示不参与; 空湖 = empty_lake_fail_closed 诚实通过态非 BLOCKER; 在场无命中无注记才 BLOCKER | **通过** |
| 网络负例偏差如实 | PLAN 假设 `--network default` → unreachable 被 live 实测推翻 (默认桥可达宿主网关 172.18.0.1:8000), 负例改 `--network none` (Errno 101) — 三态语义 (网络形态问题 ≠ 凭证问题) 不变, 44-01-SUMMARY §1 显式记录 | **通过** |
| 契约修正诚实 | window 键 RESEARCH 简写 requested/effective → 脚本实测契约 requested_start/requested_end/effective_start/effective_end (44-02 偏差 #2); coverage.symbols 断言层级缺陷 (44-02 偏差 #1) — 均沙箱捕获即修 + SUMMARY 显式记录 | **通过** |
| 凭证链诚实 | 文档提及 testkey123 仅为 RESEARCH live 实测语境 (沙箱 key), 生产 key = operator 从 STOCKDB_API_KEYS 取成员入 .env; 脚本零硬编码 (守卫表 0) | **通过** |

## 5. ROADMAP/需求逐句对照

| 需求句 | 证据 | 结果 |
|---|---|---|
| DEP-01: 凭证/连通性前置 — stockdb key 配置 + 容器内连通性验证 (127.0.0.1:8000 loopback 不通 → host 网络或网关方案, 实测判定) | .env.example 网关定案注释 (172.18.0.1, 实测 127.0.0.1 refused) + deploy_check_connectivity.sh probe 三态 (判据 = 200+SH600519 键, 非 TCP 通) + --auto-gateway/detect-gateway 网关漂移兜底 | PASS |
| DEP-01: 3018 容器对齐检查 (4 运行时文件 md5 vs HEAD) | md5 模式 4 文件容器内 vs HEAD 逐行 JSON 对齐表; live 核实 preflight 4/4==HEAD ∧ 陈旧 3018 4/4 DIFFER (641003ae/165b95a7/72e17c3c/23122ca0) → 重建确有必要 | PASS |
| DEP-02: 新端点 200-body 验证脚本 — 3 新端点 (backfill/validation/backtest) auth-gated 200-body 脚本化 (login cookie → 请求 → body 形状断言, 不再只验 401 门) | deploy_verify_endpoints.py — 401 先验 3/3 → 单次 login (DEP_PASSWORD env, tf_session cookie) → validation 8 顶层键 / backtest {runs,count}+详情 / backfill {status,job_id}+W-5 9 键; 沙箱 :3020 exit 0 | PASS |
| DEP-03: D1..D8 runbook 脚本化 — 观测窗口每项可执行 (09:26 premarket / 15:30 EOD+池持久化 / 15:40 recap / D7 探针周终 / 分钟点亮门 = 15:30 后分区存在 ∧ auction_intraday_confirm 非空, 非盘中误判) | deploy_day_runbook.sh 全项三态 + 台账 + BLOCKER exit 2; minute_light 墙钟门 (<930min → not_before_1530) + 引擎命中扫描 (minute_confirm 不参与); 沙箱全项三态 + 本 verifier 只读 dry-run 9 项诚实态 | PASS |
| DEP-04: 3018 rebuild 对齐 — 重建配方落地 (预检验证 build 66s + boot 18s) + 数据卷/权限检查 (root-owned 修复) + 旧容器替换流程文档化 | deploy_rebuild.sh preflight (build→temp 副本→:3020 boot→md5 4/4→零残留→台账) + --apply 五步 (compose up -d / chown 999:995 root 容器法 / md5 确认 / 44-02 回归) + v2.5 节 root-owned 卷清单 + chown 流程 + 执行顺序; 沙箱 run 2 全绿 (build 1s/boot 17s — 沙箱 warm 实测, 部署机真实时长属 human 记录) | PASS |

## 6. PLAN-CHECK 对照 (0 blocker, 4 warnings — 消化情况)

- **W1 (D1..D8 判定路径 RESEARCH 表为准)**: runbook 逐项与 44-RESEARCH「D1..D8 判定路径表」/ 39-03-OBSERVATION-WINDOW 对齐 (头注释声明 + v2.5 一行语义引用)。**无残留**。
- **W2 (沙箱负例网络选择)**: live 实测推翻 `--network default` 假设 → `--network none` (44-01-SUMMARY §1); 判据不受影响。**无残留**。
- **W3 (D6/D5 复盘归档 LLM 默认关)**: 沙箱无归档 → 诚实 degraded + pending_human 注记, 绝不伪造 pass; 手动均值路径 (0.005313) 独立验证。**无残留**。
- **W4 (runbook temp 副本路径互不踩踏)**: 44-03 用 `/tmp/preflight-data-4403` (44-01 自建自清 `/tmp/preflight-data`), 已协调; 实测无残留。**无残留**。

## 7. Human items (部署日/交易日真实事件 — sandbox 无法断言 / 待 operator 与用户)

1. **部署日 .env 追加两键 + 真实 probe 三态 (DEP-01)**: operator 执行 `printf 'LOCAL_STOCKDB_URL=http://172.18.0.1:8000\n' >> .env` + `printf 'LOCAL_STOCKDB_API_KEY=<STOCKDB_API_KEYS 成员>\n' >> .env && chmod 600 .env` → `set -a; . ./.env; set +a` → `deploy_check_connectivity.sh probe` — 用**生产 key** (沙箱 testkey123 不适用) 记录三态裁决; 生产 stockdb 若在别网段/别名 → unreachable 时走 detect-gateway / host.docker.internal 备选 (compose extra_hosts, operator 决策)。sandbox 已证脚本逻辑, 真实 key + 真实网络形态只能部署日实测。
2. **3018 重建替换 --apply 五步 (DEP-04)**: operator 逐条手动执行 — step1 preflight 全绿 (真实 build/boot 时长记录, 沙箱 1s/17s 为 warm 实测不可照抄) → step2 `docker compose up -d` → step3 root 容器 `chown -R 999:995` (root-owned 卷修复) → step4 md5 parity 4/4 == HEAD 确认 → step5 /health 200 + 44-02 脚本回归; 每步 human-check 记录; 脚本只打印绝不代执行。
3. **重建后 3018 200-body 全流程 (DEP-02)**: `DEP_PASSWORD=$(sed -n 's/^AUTH_PASSWORD=//p' .env) python3 backend/scripts/deploy_verify_endpoints.py --base-url http://127.0.0.1:3018 --out deploy-day-verify.json` — 记录真实 data_gate (可能翻转 available) / coverage 真实行数 / backfill requested 值, 绝不回填假值; login 401 → 注入正确密码单次重试 (RESEARCH A2 提示生产密码可能即 Command_123, 若已改则 exit 2 属预期)。
4. **D1..D8 观测窗真实交易日逐项 (DEP-03)**: 按 39-03 日历 (D1 09:26 → D4 09:26 后 → D2+D6 15:30-15:40 → D5 15:40 → D7 每交易日 → D3 条件) 在部署日 `deploy_day_runbook.sh --out ledger.json` 逐项三态记录 — premarket_results/tick_staging 落盘、sidecar 点亮、EOD 分区、复盘归档均真实交易日观测; BLOCKER (隔离破坏/空断言/零副作用破坏) → exit 2 报回开发。
5. **分钟点亮门真实点亮 (DEP-03 D8)**: 15:30 EOD 或手动同步后 `kline_minute/date={T}/part.parquet` 存在 + 引擎 `auction_intraday_confirm` 命中行非空 → lit; 当前湖 0 分区, 真点亮 = 首次真实同步日观测; 盘中运行 → not_before_1530 拒绝态属预期。
6. **D7 探针周终 (连续 ≥5 交易日)**: 每交易日运行 probe_concept_drift.py, 第 5 交易日收盘后出周终报告 (去重哈希清单 + 逐日概念增删样本 + effective_date 与上游发布时间差); 零副作用断言 (ext_data 无当日写入) 每日本脚本自动核。
7. **D3 竞价真列条件项**: 外部实时竞价源接入后 (配置自定义源 + auction_sync_enabled 偏好) 才点亮 conditional_available; 未接入 → conditional_not_configured 通过态, 无需 action; BT-07 复评 (湖 ≥20 交易日) 为后续决策项。

## 8. Honesty notes

- 本 verifier 亲自观察的 PASS 证据: 自己的 pytest (14 passed), 自己的 bash -n / py_compile / --help / --dry-run / runbook 只读 dry-run (9 项诚实态 exit 0), 自己的 md5 两路实测 (HEAD 4/4 与 claim 一致; 陈旧 3018 4/4 DIFFER 与 claim 一致), 自己的 docker ps / ss / 凭证 grep / diff 集守卫。
- 沙箱容器证据 (probe 五连 / gate / 200-body 全流程 / rebuild run 2 / runbook fixture 三态) 采信 44-01/02/03-SUMMARY — 同一会话 Executor 实跑记录, 且与本 verifier 的独立 md5 实测交叉印证 (陈旧容器 md5 逐字节一致、HEAD 基线逐字节一致); 按只读核验纪律未重复起容器。
- 未采信 SUMMARY 文本处: md5 两路值、退出码映射、脚本键集/判据、--apply dry-run 行数 (grep == 2)、v2.5 文档锚点与数值均独立重核实; 测试数 14 独立重跑一致。
- 诚实性纪律三面确认: (a) 部署日真实事件 (D1..D8 观测 / 3018 替换 / 真实登录) 全部 human-verify 标注, 沙箱证脚本逻辑与 DTO 形状绝不冒充; (b) backfill requested=0 零上游 — 构造层面 (远未来窗) + 台账如实记录不锁值; (c) 陈旧 3018 4/4 DIFFER 如实记录为「重建确有必要」, 不粉饰。
- `frontend/src/pages/Watchlist.tsx` 全程未读取, 仅经 git log/diff/status 核验: 提交内零触碰, 工作树未暂存改动为用户既有。
- 全量 backend 套件按分工由 orchestrator 收口, 本 verifier 只跑 44 相关回归文件 + 脚本干检, 不虚报全量。
- 两个 [非阻塞] 微观察: (1) deploy_rebuild.sh preflight 的 residue_container 记账为装饰性 (`docker rm -f … && RESIDUE_CONTAINER=0 || true` — rm 失败时计数仍 0), 实际残留由外部 `docker ps` 独立核实为 0, 不影响判定; (2) deploy_day_runbook.sh D8 合并判定在 09:40-15:40 窗 render `提审=` 空串进 degraded evidence (15:40 未到已由 <09:40 分支覆盖), 语义诚实仅文案略糙。
