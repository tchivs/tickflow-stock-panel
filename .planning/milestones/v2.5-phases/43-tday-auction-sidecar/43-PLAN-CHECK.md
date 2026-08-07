# Phase 43 Plan Check — T-day 竞价采集 sidecar (T-Day Auction Capture)

**Checked:** 2026-08-07 · **Plans:** 43-01 / 43-02 / 43-03 · **Method:** goal-backward (gsd-plan-checker 惯例), 只读评审, 零代码修改
**参照物:** REQUIREMENTS.md SDC-01..03 · ROADMAP Phase 43 (4 success criteria) · 43-RESEARCH.md (515 行全读, confidence HIGH) · PATTERNS.md · 用户 CONTEXT 决策 (A1/A2/DATA-06/staging 契约/诚实门 — inline, 无 CONTEXT.md 文件) · 既有源码/测试逐条核实 (stockdb_provider / auction_sync / premarket_snapshot / alert_store / daily_pipeline / pools / preferences / test_daily_pipeline_refresh / test_minute_backfill_idempotency)

---

## Verdict: **EXECUTABLE**

0 blockers · 6 warnings · 3 info。采集/对账/提审/诚实门全链路 canned 零网络可测; A1 (3s 粒度) / A2 (池 ≤200 白名单默认自选池) / DATA-06 (unmatched 诚实缺列) 按研究建议落地并逐条记录; 计划未触碰 `frontend/src/pages/Watchlist.tsx`; 零新增运行时依赖。

## D0 — Multi-Source Coverage Audit (GOAL / REQ / RESEARCH / CONTEXT)

| Source | Item | 覆盖 Plan/Task | 状态 |
|---|---|---|---|
| GOAL | SC1: 09:15-09:25 逐秒快照 + 09:25 撮合行定时采集落 staging; canonical 零污染 | 43-01 T1/T2 (capture+完整性+staging) + 43-03 T3 (cron 09:26) + 43-02 T1 (虚拟行过滤) | ✅ (3s 粒度按 A1 重述) |
| GOAL | SC2: live 对账闭合 09:25 price×vol == 09:30 bar amt (22,639,818) | 43-01 T3 (三重对账) | ✅ |
| GOAL | SC3: T-day 逐日累积真实竞价列 + DATA-06 派生输入 probe 确认后映射 | 43-02 T1/T2 (累积+映射) + T3 (DATA-06) | ✅ |
| GOAL | SC4: 诚实门 fail-closed + 台账/告警 09:26 后缺失可告 | 43-03 T1/T2 (台账+告警+交易日) | ✅ |
| REQ | SDC-01 (采集+对账+staging) | 43-01 | ✅ |
| REQ | SDC-02 (T-day 累积 + DATA-06 映射) | 43-02 | ✅ |
| REQ | SDC-03 (诚实门 + 可观测) | 43-03 | ✅ |
| RESEARCH | fetch-on-miss 单次 GET 全窗口 (核心机制) | 43-01 T1 (get_ticks + capture; 轮询显式禁止) | ✅ |
| RESEARCH | staging 契约 10 列 + manifest + _DATE_RE + 原子写 | 43-01 T1 | ✅ |
| RESEARCH | 完整性三重校验 (归属日/09:25 行/窗口阈值) | 43-01 T1 | ✅ |
| RESEARCH | 三重对账 (price 1e-6 / vol 恒等 / amount OHLC 派生) | 43-01 T3 | ✅ |
| RESEARCH | canonical 升湖仅 09:25 num_trades>0 行 + 单位映射 ×100 | 43-02 T1 | ✅ |
| RESEARCH | 提审闸门 = staging 判定非 xyz probe (Pitfall 6) | 43-02 T1 (gate 三拒测试) | ✅ |
| RESEARCH | 诚实门: fail-closed 无分区 + 台账 W-5 + 告警 alert_store + 交易日数据在场 | 43-03 T1/T2 | ✅ |
| RESEARCH | 调度三 job (09:26/09:40/15:40) CronTrigger + _run_tracked | 43-03 T3 | ✅ |
| CONTEXT (D-A1) | 「逐秒」= 源原生 3s 粒度如实, 不伪造 | 43-01 T1 (窗口≥40 阈值验收) + I1 | ✅ |
| CONTEXT (D-A2) | 池构成 = 配置白名单, 默认自选池, ≤200 pool-gated | 43-01 T2 (resolve_sidecar_pool + cap) | ✅ |
| CONTEXT (D-DATA-06) | unmatched_volume 诚实缺列不猜测; virtual_price 映射 + 交叉验证 | 43-02 T1/T3 | ✅ |
| CONTEXT (D-staging) | staging 契约 = tick_staging/date={T} 10 列 + manifest + 三重对账 | 43-01 T1/T3 | ✅ |
| CONTEXT (D-honesty) | fail-closed 无分区 + 台账 + 告警 + 交易日在场判定 | 43-03 T1/T2 | ✅ |

**无未规划项**; 排除项 (非 gap): v2.5 Out of Scope (09:15-09:24 入 canonical / 全量回填宣称 / Watchlist.tsx 触碰) 全程未入计划; Deferred (sidecar 正式化 / DATA-06 真实输入物化升级) 未入本 phase。

## D1 — Goal-backward: 每 success criterion → 可观测验收 (反向无孤儿)

| ROADMAP Success Criterion | 覆盖 Plan/Task | 可观测验收 | 状态 |
|---|---|---|---|
| SC1: 逐秒快照 + 09:25 撮合行定时采集落 staging (canonical 零污染) | 43-01 T1/T2 + 43-03 T3 + 43-02 T1 | get_ticks 单次 GET 全窗口 (fetch-on-miss); staging 10 列 + manifest; 完整性三拒 fail-closed; 三 job cron 注册断言; 虚拟行/回显行永不入湖 (43-02 T1 测试) | ✅ (3s 粒度 A1) |
| SC2: live 对账闭合 price×vol == 09:30 bar amt | 43-01 T3 | 173×100×1308.66 == 22,639,818 (1e-6) 契约闭合; mismatch/pending 语义; end=T+1 锁死 | ✅ |
| SC3: T-day 逐日累积真实竞价列 + DATA-06 映射 (不猜测) | 43-02 T1/T2/T3 | 逐日累积分区 + 幂等重跑; 单位映射 17300 股/22,639,818 元; virtual_price==kline_daily.open 1e-6 交叉验证; unmatched 分区列集断言缺列 | ✅ |
| SC4: 诚实门 fail-closed + 台账/告警 09:26 后缺失可告 | 43-03 T1/T2 | 台账 JSONL 键集; capture_missing (交易日 ∧ 缺失) / reconcile_fail 告警; 非交易日零告警; fail-closed 保持 (43-01/02) | ✅ |

**反向孤儿检查:** 全部 9 任务可回溯到 SDC-01..03 与 SC1..4, 无孤儿任务; 需求覆盖 SDC-01✅ (43-01) / SDC-02✅ (43-02) / SDC-03✅ (43-03)。43-02 依赖 43-01 (staging 契约 + reconciliation gate 输入); 43-03 依赖两者 (调度接线 + 告警判定) — 顺序链正确, 无环。

## D2 — 依赖/顺序

- **wave 1** = 43-01 (`depends_on: []`): provider 扩展 + capture + staging + reconcile + 池 — 无上游。
- **wave 2** = 43-02 (`depends_on: [43-01]`): promote 读 43-01 的 staging 分区/manifest (gate 输入 = completeness/reconciliation 键) — 契约依赖, 必须顺序; 测试独立种子 staging (不依赖 43-01 文件存在, 但 schema 契约须先定稿)。
- **wave 3** = 43-03 (`depends_on: [43-01, 43-02]`): 调度接线调用三 job 函数 (43-01 capture/reconcile + 43-02 promote) + 告警消费 reconcile 输出。
- **文件冲突扫描**: 43-01 (stockdb_provider / auction_capture / auction_reconcile / fixtures/ticks / test_auction_capture / test_auction_reconcile) · 43-02 (auction_promote / test_auction_promote) · 43-03 (auction_sidecar_ledger / daily_pipeline / test_auction_sidecar_ledger / test_daily_pipeline_refresh / docs) — **零 files_modified 重叠**。
- 43-03 `autonomous: true` — 无 checkpoint (无外部源决策; 机制全部 live 实测锚定, canned 可测; A5 重试内置于 reconcile, 不依赖人)。

## D3 — 风险覆盖 (RESEARCH 遗留逐项)

| RESEARCH 遗留 | PLAN 处理 | 状态 |
|---|---|---|
| [CRITICAL] Pitfall 1: 轮询式逐秒采集误解 fetch-on-miss | 43-01 T1 单次 GET + 完整性校验; A1 验收口径「3s 快照级 (窗口≥40)」写入 objective/验收 | ✅ |
| [CRITICAL] Pitfall 2: 虚拟快照行升 canonical | 43-02 T1 num_trades>0 过滤 + 555..565 双保险 + 测试断言虚拟行/回显行绝不出现 | ✅ |
| [HIGH] Pitfall 3: 09:15 前触发 → 昨日数据 | 43-01 T1 请求必带 ?date=T + 归属日==T 校验 (canned 昨日场景测试) | ✅ |
| [HIGH] Pitfall 4: 对账读 AQ 分钟湖恒空误判 | 43-01 T3 对账走 stockdb /v1/minute (end=T+1 内置); 09:40 时点 AQ 湖无当日分区显式禁读 | ✅ |
| [HIGH] Pitfall 5: 完整窗口 vs 部分窗口竞态 | 43-01 T1 完整性校验兜底 (09:25 行 + 窗口≥40) fail-closed | ✅ |
| [MEDIUM] Pitfall 6: probe 闸门与诚实回归适配 | 43-02 T1 gate = staging manifest 判定 (三拒测试); 绝不用 resolve_auction_probe; probe/写湖既有测试零改动 | ✅ |
| [MEDIUM] Pitfall 7: 对账金额单位/派生错配 | 43-01 T3 amount 仅 OHLC 全等派生 + 契约 22,639,818; 43-02 T1 单位映射契约 17300 股 | ✅ |
| Open Q1 (逐秒验收) | A1 决策落地: 3s 快照级逐条捕获 (43-01 objective/验收阈值) | ✅ |
| Open Q2 (采集池构成) | A2 决策落地: 配置白名单默认自选池 ≤200 (43-01 T2) | ✅ |
| Open Q4 (unmatched_volume 最终处置) | 诚实缺列不映射 (43-02 T1/T3); WS depth 派生另立探针任务 (Deferred) | ✅ |
| Open Q5 (升 canonical 时点) | EOD 15:40 提审 (43-03 T3), 与 D3 15:40 recap 槽位对齐; 盘中 provisional staging 读取不做 | ✅ |
| A3 (amount 派生规则) | 43-01 T3 OHLC 全等派生; amount_yuan=None 不直读 | ✅ |
| A4 (部署机 collect_loop 差异) | 完整性校验兜底 (不信任服务端即真); 部署差异登记 Phase 44 D-项 | ✅ |
| A5 (交易日判定) | 数据在场 (09:30 bar) + 重试 1 次 → pending (43-01 T3 / 43-03 T2); trading_days.json 可选增强不依赖 | ✅ |
| RESEARCH 骨架字段名 (volume_hand vs canonical) | 43-01 T3 对账用 provider canonical 列名 (close/volume, Phase 40 契约) — W1 | ✅ |

## D4 — 可执行性 (行号核对证据表)

| 计划引用 | 源码实测 | 判定 |
|---|---|---|
| stockdb_provider.py `_get_json` 唯一请求面 + get_minute 形态 (get_ticks 扩展源) | :128-152 `_get_json` (X-API-Key header-only + typed 分类), :209-235 get_minute (symbols/start/end + 限频); **无 get_ticks 方法** (新增面确认) | ✅ 一致 |
| auction_sync.py write_auction_partitions (555..565 + crop + merge-upsert + 原子写; probe 闸门位置) | :36-93 写函数体**不含** resolve_auction_probe; probe 闸门在 sync_and_persist_auction :151-175 — promote 直调写函数成立 (Pitfall 6 修正依据) | ✅ 一致 |
| premarket_snapshot.py `_DATE_RE` + 独立分区 + temp+os.replace | :22-27 `_DATE_RE = ^\d{4}-\d{2}-\d{2}$` + :43-63 persist 原子写 — staging 守卫/写面镜像成立 | ✅ 一致 |
| alert_store.py JSONL + 滚动清理 (台账镜像) | :1-83 append/append_many/list_recent + MAX_DAYS=7/MAX_RECORDS=5000/PRUNE_EVERY=20/threading.Lock | ✅ 一致 |
| daily_pipeline.py `_run_tracked` 单飞 + CronTrigger 注册 + 09:26 槽位 | :723-750 `_run_tracked(fn, job_label)` (job_store + run-slot 单飞); :969-970 `_PREMARKET_JOB_ID = "premarket_pool_preview"` 09:26; :1140-1174 三 job add_job 模式 (CronTrigger mon-fri Asia/Shanghai + replace_existing + misfire_grace_time) | ✅ 一致 |
| daily_pipeline.py job 函数形态 (capture/reconcile/promote 镜像) | :1016-1080 `_premarket_pool_preview(on_progress=None) -> dict` (`_get_app_state()` → repo → 终态 dict; 无 app state → 诚实 skip) | ✅ 一致 |
| preferences 白名单偏好键先例 | :134-142 `get_auction_sync_symbols`/`set_auction_sync_symbols` + `_normalize_symbol_list` — `auction_sidecar_symbols` 镜像成立 | ✅ 一致 |
| pools.get_pool("watchlist") 自选池 | pools.py :56-58 `get_pool("watchlist")` → `_load_watchlist()` 读 data/user_data/watchlist.parquet | ✅ 一致 |
| provider `_to_prefix`/`_to_suffix` symbol 归一 | :47-59 模块级函数 (SH600519↔600519.SH) — 池归一 + promote 后缀转换复用成立 | ✅ 一致 |
| test_daily_pipeline_refresh.py fake scheduler 注册断言形态 | :1-50 恒 stub run_now + fake AsyncIOScheduler 捕获 add_job + 闭包提取 — 三 job 断言扩展成立 | ✅ 一致 |
| test_minute_backfill_idempotency.py canned fetch 注入 + repo_env | 42-01 交付: `_canned_fetch` + `repo_env(tmp_path, monkeypatch)` — 43-01/02 测试注入面镜像成立 | ✅ 一致 |
| verify_auction_backfill [4] 交叉校验 1e-6 | :191-215 既有断言 (auction_virtual_price == kline_daily.open) — 43-02 T3 cross_validate 同语义 | ✅ 一致 |
| market_time.cn_today / 交易日历缺口 | market_time.py 无日历 (仅周末注释); stockdb trading_calendar 无 HTTP 端点 — 数据在场判定前提成立 (Q6) | ✅ 一致 |
| data.py:772 auction 列单位「单位: 股」 | 逐字核实 — vol_hand×100 映射依据成立 | ✅ 一致 |

## D5 — 决策覆盖 (用户 CONTEXT 决策 → 计划落地)

| 决策 | 计划落地 | 状态 |
|---|---|---|
| A1: 「逐秒」= 源原生 3s 粒度如实, 不伪造 (验收按 3s 快照级) | 43-01 objective/验收 (窗口行数 ≥ 40); 计划全文无「每秒 1 行」表述; I1 记录 | ✅ |
| A2: 池构成 = 配置白名单, 默认自选池, ≤200 pool-gated | 43-01 T2 resolve_sidecar_pool (preferences 白名单优先 → watchlist 回落 + 硬 cap 200 + 截断注记 + 归一失败诚实) | ✅ |
| DATA-06: unmatched_volume 诚实缺列不猜测; virtual_price 映射 + 交叉验证 | 43-02 T1 (分区列集断言无 unmatched) + T3 (cross_validate 1e-6 + 缺 daily 诚实标注) | ✅ |
| staging 契约: tick_staging/date={T} 10 列 + manifest + 三重对账 | 43-01 T1 (10 列 + manifest) + T3 (三重对账) | ✅ |
| 诚实门: fail-closed 无分区 + 台账 + 告警 09:26 缺失可告 + 交易日在场判定 | 43-03 T1 (台账) + T2 (告警 + 交易日) + 43-01 T1 (fail-closed 机制) | ✅ |
| 采集 = 服务端 fetch-on-miss, 不做盘中轮询 | 43-01 T1 (单次 GET + 轮询显式禁止 + 反模式威胁登记) | ✅ |
| 5537 不可行 → 池 ≤200 | 43-01 T2 (cap) + I3 (FA-04 解锁路径记录) | ✅ |
| 零新增依赖 / Watchlist.tsx 零触碰 / 诚实覆盖 | 全 plan 威胁模型 SC 行 + D7 gate (git diff 守卫) | ✅ |
| 调度: sidecar 09:26 cron 窗口 | 43-03 T3 (三 job 注册, 09:26 capture 与盘前同槽位) | ✅ |

## D6 — B/W 清单

### Blockers (0)
无。

### Warnings (6)

- **W1 (43-01 T3)**: RESEARCH Pattern 3 骨架对账字段用 `bar0930["volume_hand"]` — provider.get_minute 返回 canonical 列名 (`close`/`volume`, 元/手, Phase 40 契约 volume 恒等 ×1)。计划已落地为 canonical 列名 (`volume`), 与 RESEARCH 骨架字段名有出入; 执行时以 provider canonical 输出为准, 不得按骨架字段名逐字抄。amount 派生两式均含 ×100, 语义不变。
- **W2 (43-02 T1)**: RESEARCH Code Examples 提审骨架 `.unique(subset=["symbol","time"])` 会保留 09:25:00 与 09:25:04 两行 (不同 time) → canonical 单 symbol 双行, 破坏「一 symbol 一撮合行」不变量 (xyz 路径单行语义)。计划改为 `sort("time")` + `unique(subset=["symbol"], keep="first")` → 单日单行 (09:25:00); 执行时不得按骨架逐字抄。
- **W3 (43-01 T3)**: 09:45 重试 = reconcile 内部 `sleep(300)` — 持 `_run_tracked` run-slot 5 分钟; 该时点 (09:40-09:45) 无重任务 (EOD 15:30+), 可接受; 若部署机新增盘中重任务需复核。A5 边缘 (交易日但 09:30 bar 延迟) 由重试 + pending 覆盖, 不误报 mismatch。
- **W4 (43-03 T2)**: 交易日判定 = 数据在场 (09:30 bar) — 语义上「无 bar ⇒ 非交易日」在 bar 延迟发布时保守 (不告警, 台账 pending); 若用户要求权威日历 → stockdb trading_days.json (host 文件, 无 HTTP 端点) 为可选增强, 依赖 DEP-01 连通性前置, 本阶段不引入 (A5)。
- **W5 (43-01 T2)**: 自选池 symbol 形态 — watchlist.parquet 存后缀形态 (600519.SH); tick 端点要前缀 (SH600519) — 池解析必须 `_to_prefix` 归一; 含非 SH/SZ 形态 (裸码/ETF) 归一失败 → failed reason (不猜); 白名单种子测试需显式覆盖此路径。
- **W6 (43-02 T3)**: cross_validate_virtual_price 依赖 kline_daily 当日分区 — 15:40 提审时点日K 已 EOD 同步 (15:30 管道) → 可用; 若 EOD 失败 → skipped + 诚实标注 (不缺 daily 不猜测); 该函数为验证面, 不阻塞提审写湖 (写湖 gate 是 reconciliation.closed)。

### Info (3)

- **I1**: A1 已记录 — SDC-01「逐秒快照」验收口径 = 「3s 快照级逐条捕获 (窗口行数 ≥ 40)」, 源原生粒度 (TDX L1 3s, 实测 gap 分布 3s 主导); 绝不伪造每秒 1 行; 若用户日后坚持逐秒 → 需换源 (FA-04 结论: live 逐秒同样不可得)。
- **I2**: 提审复用 `write_auction_partitions` 写函数 (555..565 谓词 + merge-upsert + 原子写) — probe 闸门不在写函数内 (D4 核实), promote 以 staging 判定为 gate; 既有 probe/写湖测试零改动, canonical 湖 555..565 排除保持 (test_0930_excluded 绿)。
- **I3**: 全量 5537 盘中采集 descope (A2 pool-gated ≤200); FA-04 真列解锁 = T-day 逐日累积 (连续交易日 P2 验证后升级常驻通道, Deferred); 本 phase 交付机制 + 观测链, 不承诺任何历史覆盖。

## D7 — 执行顺序建议

```
Wave 1:  43-01 (provider get_ticks + capture + staging + 三重对账 + 池 ≤200)
Wave 2:  43-02 (promote 撮合行升湖 + 逐日累积 + DATA-06 映射/交叉验证)   ← 依赖 43-01 staging 契约
Wave 3:  43-03 (台账 + 告警 + 交易日判定 + 三 job 调度 + 文档)          ← 依赖 43-01/02 job 函数
```

**Phase gate:** wave 3 合并后全 suite 绿 (43-01..03 全链路 + 诚实回归族 test_auction_sync / test_auction_columns / test_auction_probe / test_minute_sync_verify) + `git diff --stat frontend/src/pages/Watchlist.tsx` 零改动 → `/gsd-verify-work`。
