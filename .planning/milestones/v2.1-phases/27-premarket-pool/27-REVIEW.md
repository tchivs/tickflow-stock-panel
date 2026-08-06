# Phase 27 计划检查 round 1

**检查对象:** `.planning/phases/27-premarket-pool/27-01-PLAN.md` + `27-02-PLAN.md`
**依据:** `27-RESEARCH.md` / `27-PATTERNS.md` / `.planning/REQUIREMENTS.md`(PM-01..04) + 真实代码逐符号核验(file:line 见各条目)
**日期:** 2026-08-06
**判定:** 27-01 NOT EXECUTABLE / 27-02 NOT EXECUTABLE(共享阶段级 blocker;27-02 自身内容干净)

---

## 核验摘要(通过项,file:line 已逐行对照)

| 维度 | 结论 | 证据 |
|---|---|---|
| 需求覆盖 | PM-01/02/03 → 27-01,PM-04 → 27-02;无遗漏、无越界(tier-2 在 REQUIREMENTS Out of Scope) | 27-01 `requirements: [PM-01,PM-02,PM-03]`;27-02 `requirements: [PM-04]`;REQUIREMENTS.md PM-01..04 |
| 文件路径 | 新增文件确实不存在(premarket_snapshot.py/premarket_pool.py/test_premarket_pool.py/premarket-pool.spec.ts 均未创建);既有文件全部存在 | `ls` 核验 |
| 符号真实性(后端) | `_pool_eod_persist` daily_pipeline.py:966-1008、`_run_tracked` :722-770、`_POOL_EOD_JOB_ID` :962、`_get_app_state` :1166、`_noop` :48、EOD cron 注册 :1081-1089、`run_all_with_hits(engine=kwarg)` screener.py:723、`latest_date` :704、`_load_enriched_for_date` :245、`AuctionProbeVerdict.to_dict` auction_probe.py:51-58、`resolve_auction_probe(*,source_resolver,fetcher)` :139-181、`_last_trade_date` :71-84、`attach_auction_columns` 双闸门 auction_columns.py:89-150(probe :107 / 分区 :112)、`compute_enriched_today` pipeline.py:1250、Pass 4 open_gap :499-507、`ENRICHED_STORAGE_COLS` :57(open_gap @ :66)、`_project_hub(results,resolved_as_of,updated_at,concept,name_for,data_dir)` pool_hub.py:83、`build_pool_hub` :189、`build_pool_hub_snapshot` :225、`mask_guest_hub` guest_masking.py:23-54(pop auction_columns :53)、`strategy_cache.write_cache` strategy_cache.py:103、`cn_today`/`cn_now` market_time.py:21/26、`_GUEST_READ_GET_PATHS` main.py:779-785、`pool.router` 注册 main.py:852、repo 四方法 repository.py:920/1059/937/1118、`strategy_fingerprint(engine)` pool_snapshot.py:166 | 逐行 grep/read |
| PM-01 设计 | 独立 root `premarket_results/date={T}/part.json`(物理分离 `_SNAPSHOT_ROOT="screener_results"` pool_snapshot.py:31);绝不 write_cache(镜像 pool_backfill.py:1-11 铁律);诚实 skip 三态(镜像 `_pool_eod_persist` 966-975);`_run_tracked` 单飞;`misfire_grace_time=1800` | pool_backfill.py:1-11;daily_pipeline.py:722-770,966-1008 |
| PM-02 设计 | 补算公式与 Pass 4 逐字一致(`pl.when(prev_close>0).then(open/prev_close-1).otherwise(None)`),守卫幂等;插点位于 prev_close 复权对齐后(pipeline.py:1301-1310);vol_ratio 盘前行为(:1410-1418)零改动;除权日 fixture 锁口径 | pipeline.py:499-507,1301-1323,1410-1418 |
| PM-03 设计 | probe_resolver 注入点消费 `resolve_auction_probe`(签名零改动,auction_probe.py 不进 files_modified → test_auction_probe 回归面不受扰);degraded = status≠available;real==[] 诚实缺列;tier-2(D6)明确不实现 | 27-01 必须项 + REQUIREMENTS Out of Scope |
| PM-04 设计 | 端点只读(挂 pool.router,main.py:852);guest 白名单扩 `_GUEST_READ_GET_PATHS`(main.py:779-785);DateNavigator 零改动(dates 白名单仍 = `/api/pool/dates` pool.py:36-58,盘前日不入);`AuctionColumnStatusBadge` 盘前 secondary 行既有(StockListTable.tsx:145-150),badge 挂载点 PoolHubPage.tsx:283-285;`usePremarketPool`/`QK.poolPremarket` 当前不存在(新符号,已 grep) | 前端逐文件核验 |
| 验证命令 | 后端 `cd backend && .venv/bin/python -m pytest tests/test_premarket_pool.py ...` 路径正确;前端 `npm run build` + `npx playwright test e2e/premarket-pool.spec.ts`;回归面文件名全部存在 | test_*.py 全存在 |
| 文件重叠/依赖 | 27-01(全后端+后端测试) vs 27-02(全前端+docs)零重叠;27-02 `depends_on:["27-01"]` wave 2,前置 `<precondition>` grep 门指向 27-01 端点契约 | 两计划 frontmatter |
| 诚实性 | 空态 200 available:false 非 404/非零池伪装(镜像 pool.py:88,100-107);strategy_cache 不污染;EOD 语义不动;Watchlist.tsx 两计划均排除(git status `M` 用户改动) | git status;pool_hub.py:243-250 |
| 既有测试影响 | 新增 GET `/premarket` 保持 pool.py 路由集合 {get}(test_pool_hub.py POOL-03 `test_pool_api_is_get_only` 仍绿);新 import 不命中执行族 token;open_gap 补算不触 Pass 4(`compute_enriched` 零改动);auction_probe.py 未列入 files_modified | test_pool_hub.py:866-905 |

---

## 27-01: NOT EXECUTABLE

**原因:** 阶段级 Nyquist blocker(缺 `27-VALIDATION.md`,见 B-1)+ 3 个计划内文级不一致(W-1..W-3)。计划设计本身与既有 seam 完全对齐,修复均为小改,不涉及架构返工。

## 27-02: NOT EXECUTABLE

**原因:** 与 27-01 共享阶段级 blocker B-1(VALIDATION.md 属阶段产物,两计划同受影响);且 27-02 依赖 27-01,27-01 需修订后再执行。27-02 自身内容干净(零内文 blocker/warning 级设计问题)。

---

## Blockers(每个:B / 计划 / 证据 / 修复建议)

**B-1 缺失 `27-VALIDATION.md`(Nyquist 8e 门)**
- 计划: 27-01 与 27-02(阶段级)
- 证据: `ls .planning/phases/27-premarket-pool/` 只有 `27-01-PLAN.md` / `27-02-PLAN.md` / `27-PATTERNS.md` / `27-RESEARCH.md`,无 `*-VALIDATION.md`;而 Phase 24/25/26 目录均含 `*-VALIDATION.md`;`.planning/config.json` `workflow.nyquist_validation: true`。按 Nyquist Check 8e 门规:「VALIDATION.md not found for phase 27」。
- 修复: 重新运行 `/gsd-plan-phase 27 --research` 以再生 `27-VALIDATION.md`;或补写与 24/25/26 同构的 VALIDATION.md(把 27-RESEARCH.md §5 Validation Architecture 的 req→测试映射 / 回归面 / Wave 0 缺口落成独立文件)。注:计划内每个 `<task>` 均已带 `<automated>` verify(Nyquist 8a/8c 实质满足),此为产物缺口而非设计缺口,但门规为 BLOCKING FAIL。

---

## Warnings(每个:W / 计划 / 证据 / 修复建议)

**W-1 27-01 Task 3 `pool.py` import/调用文本与文件布局矛盾**
- 计划: 27-01 Task 3
- 证据: Task 3 action step 1 称「追加 `load_premarket_snapshot` 到该 import 行」——所指为 pool.py:17 的 `from app.services.pool_snapshot import list_backfill_gaps, list_snapshot_dates`;但 `load_premarket_snapshot` 由本计划 Task 1 建在**新模块** `premarket_snapshot.py`,不在 `pool_snapshot.py`。step 2 代码又写成 `pool_snapshot.load_premarket_snapshot(...)`(qualified call),而 pool.py 目前并无 `import pool_snapshot` 模块别名(只有 from-import)。照字执行 → `ImportError`,pool router 整体 import 失败,Task 3 首轮 pytest 全挂。同理 step 1 追加 `_project_hub` 到 `from app.services.pool_hub import build_pool_hub, build_pool_hub_snapshot`(pool.py:16),step 2 却调用 `pool_hub._project_hub(...)`(无 `pool_hub` 模块别名)。
- 修复: 统一为一种形式——推荐 `from app.services.premarket_snapshot import load_premarket_snapshot` 并直接调用 `load_premarket_snapshot(...)`;`_project_hub` 用 by-name import 后直接调用 `_project_hub(...)`(或 `from app.services import pool_hub` + `pool_hub._project_hub(...)`)。计划 must_haves key_link 已正确指向 `premarket_snapshot.load_premarket_snapshot`,以 key_link 为准修正 action 文本。

**W-2 27-01 Task 1 注册形锁死测试与常量注册矛盾(`hour=9, minute=26` 永不出现)**
- 计划: 27-01 Task 1
- 证据: step 9 定义 `_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26`;step 11 注册写成 `CronTrigger(day_of_week="mon-fri", hour=_PREMARKET_HOUR, minute=_PREMARKET_MINUTE, timezone="Asia/Shanghai")`。而 Test 13 `test_premarket_job_registered_in_scheduler` 断言源码含字面量 `'hour=9, minute=26'`;must_haves truth 亦写 `hour=9, minute=26`。按 step 11 用常量后,`hour=9, minute=26` 字面量不会出现在 daily_pipeline.py → 测试失败 → Task 1 `<verify>` 的 `pytest -k "premarket ..."` 失败。对照:既有 EOD 注册测试只断言 `CronTrigger(day_of_week="mon-fri"` + `timezone="Asia/Shanghai"`,不锁字面 hour/min(test_pool_eod_job.py:172-184)。
- 修复: 二选一且保持自洽——(a) 注册直接写字面 `hour=9, minute=26`(与 must_haves truth 一致),或(b) 保留常量但把测试改成断言 `_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26` 与 `hour=_PREMARKET_HOUR, minute=_PREMARKET_MINUTE` 两 token。建议 (b),与 EOD job 用 `pool_hour`/`pool_minute` 变量的注册形一致。

**W-3 27-01 Task 2 结构 grep 可能假失败(0 匹配)**
- 计划: 27-01 Task 2
- 证据: `<verify>` 末段 `grep -n "open_gap" app/indicators/pipeline.py | grep -c "1250\|today\|compute_enriched_today"`。Task 2 插入代码的注释只含「compute_enriched L499-507」,不含 `today`/`1250`/`compute_enriched_today`;既有 open_gap 行(L66/95/170/310/324/499-507)同样不含这些 token;`grep -n` 行号前缀为 ~1320,不含 "1250"。→ 计数 0 → `grep -c` 退出 1 → `&&` 链失败,即使实现正确。
- 修复: 结构门改为可命中的断言,如 `grep -n "open_gap" app/indicators/pipeline.py | grep -c "compute_enriched"`(注释含该词),或 `awk '/open_gap/{n++} END{print n}' app/indicators/pipeline.py` 并断言 > 既有行数;真正的验收以 `pytest -k "open_gap"` 为准。

---

## Infos

- **I-1** 文档行号轻微漂移(RESEARCH/PATTERNS vs 真实代码):`_ERROR_DETAIL_MAX` 实为 auction_probe.py:30(RESEARCH 写 24-25);`trading_minutes_elapsed` 实为 market_time.py:50(写 31-48);vol_ratio 块实为 pipeline.py:1410-1418(PATTERNS 写 1423-1429);`AuctionColumnStatusBadge` 盘前分支实为 StockListTable.tsx:145-150(写 134-137)。符号均存在,不影响执行,建议 RESEARCH 刷新。
- **I-2** RESEARCH「### 开放问题 OQ-1..5」未用规范 `## Open Questions (RESOLVED)` 标题,但每条都有「现状+建议」且计划已落实(OQ-2→provisional:true+全策略跑;OQ-4→不并入 today_ever;OQ-5→不做保留期)。不阻塞。
- **I-3** 两计划 estimate 66000/56000 tokens、confidence:low(<3 个已完成 phase 提供实际值,未校准)。任务数/文件数均在目标区(3 tasks、7-8 files/plan),scope 合理,按规范把 estimate 作 advisory 处理。本环境 gsd-tools 无 `estimate-check` 子命令,无法跑校准检查。
- **I-4** 27-02 Task 1 `hasTodayEod` 的 today 串 helper 提供两个选项(DatePicker.tsx:22-25 镜像 / format.ts:31-40 `fmtDate`),`fmtDate(new Date())` 产本地 YYYY-MM-DD,可行。
- **I-5** 27-01 Task 3 空态骨架实际含 `as_of`/`mode`/`auction_columns` 三键,must_haves truth 只列 8 键;27-02 `premarketEmptyPayload` fixture 与 27-02 `PremarketPoolResponse extends PoolHubResponse` 均兼容多键。建议 truth 补全三键以精确化契约。
- **I-6** 27-02 e2e 复制 installShell 而非 import(独立 spec),且 `**/api/**` unhandled 兜底保留——新增 `/api/pool/premarket` 默认 mock 若漏注册会大声失败,计划 Task 2 step 3 已覆盖。

---

## 结论

- **27-01: NOT EXECUTABLE**(B-1 阶段级 Nyquist blocker + W-1..W-3 内文不一致,需修订后重检)
- **27-02: NOT EXECUTABLE**(与 27-01 共享 B-1;依赖待修订的 27-01;自身内容干净)
- 修复量级:1 个产物再生(VALIDATION.md)+ 3 处计划文本对齐(W-1/W-2/W-3),均为小改,不涉架构返工。建议一轮修订后 round 2 复查。
