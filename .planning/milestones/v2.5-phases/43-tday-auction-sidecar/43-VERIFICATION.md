---
phase: 43-tday-auction-sidecar
verified: 2026-08-07
status: passed
score: 3/3 SDC requirements — SDC-01/02/03 verified (0 blockers; live 交易日采集未发生 = deploy-gated, 5 human_items 全部呈现态/部署面, 无代码缺陷)
overrides_applied: 0 — 提交集 e652734..b86cd72 未改动 REQUIREMENTS.md/ROADMAP.md 文本; SDC-01「逐秒快照」按 A1 决策以「3s 源原生粒度逐条捕获」执行 (43-01-PLAN.md:45 显式记录, 见 human_items #2)
human_verification: 5 items (live 交易日采集 deploy-gated / 逐秒→3s 粒度 A1 重述待定稿 / virtual_price 交叉验证未接线 job / 交易日判定数据在场依赖服务端 / num_trades 语义锚点单日样本)
---

# Phase 43 Verification — SDC T-day 竞价采集 sidecar (SDC-01..03)

**Verifier:** VerifierP43 · **Date:** 2026-08-07 · **Scope:** `.planning/REQUIREMENTS.md` SDC-01/SDC-02/SDC-03 (Phase 43), 提交集 `e652734..b86cd72` (12 commits: wave1 `e652734/e6adde7/5bd1da5/5c51abb`, wave2 `022d376/0809609/c98bfbb/e95497e/422beb7`, wave3 `ff53c68/90b41b9/b86cd72`).
**Method:** Behavior-level verification — 逐需求读实现 (auction_capture/auction_reconcile/auction_promote/auction_sidecar_ledger/daily_pipeline/stockdb_provider 全文) + 契约测试独立重跑 + 夹具实锤 RESEARCH 锚点 (3s 粒度 / 1308.66·173手·120笔 / 22,639,818 闭合 / num_trades 0=虚拟 120=真) + 守卫核验 (零新依赖 / Watchlist 零触碰 / canonical 只收 09:25 行 / 提交集完整性)。所有数字为本 verifier 亲自重推导, 不采信 SUMMARY 文本。NEVER read `frontend/src/pages/Watchlist.tsx` (全程只经 git diff/status 核验零触碰)。

## Verdict: **PASSED**

三项需求全部验证通过: SDC-01 采集面 (fetch-on-miss 单次 GET 全窗口 + staging 10 列独立湖 + 三重完整性 fail-closed + 三重对账 22,639,818 闭合, 虚拟量绝不入 canonical), SDC-02 T-day 累积 (逐日提审幂等 + 仅撮合行升湖 + 单位映射 ×100 + virtual_price 1e-6 交叉 + unmatched 诚实缺列), SDC-03 诚实门 (台账 JSONL W-5 键集 + fail-closed 无因不记 + capture_missing/reconcile_fail 告警 + 三 job 09:26/09:40/15:40 调度 + 交易日数据在场判定)。零新依赖, Watchlist 零触碰, canonical 只收 09:25 撮合行。唯一挂起项 = live 交易日采集尚未发生 (deploy-gated, Phase 44 DEP-03 D8 点亮门为首验项) — 呈现态非缺陷。

---

## 1. 守卫核验 (guard rails)

| 守卫 | 命令 (本 verifier 亲自跑) | 结果 |
|---|---|---|
| 零新增依赖 | `git show --stat --format="" <12 commits> \| grep -E "pyproject\|uv.lock"` | **0 匹配** — 12 commits 无一行触碰 `backend/pyproject.toml` / `backend/uv.lock` (uv.lock 最近触碰 ac1b2aa, 非本 phase) |
| Watchlist 零触碰 | 同上 grep `Watchlist` + `git status --short` | 提交内 **0**; 工作树唯一未暂存项 ` M frontend/src/pages/Watchlist.tsx` (会话开始前已存在的用户工作, 未入任何 commit; 本 verifier 未读取该文件) |
| canonical 只收 09:25 行 | 代码读 + `test_promote_excludes_virtual_rows` | 提审过滤 `time∈09:25:00..09:25:59 ∧ num_trades>0` + `write_auction_partitions` 555..565 谓词双保险 (09:25→565∈[555,565]; 09:30+ 结构性排除); 测试断言 df.height==1 且 datetime==09:25:00, 虚拟/回显/重复行全排除 |
| 提交集完整性 | `git log --oneline -20` + `git show --name-only` 逐 commit | 12 commits 与 claim 完全一致 (wave1 3 code+1 docs, wave2 4 code+1 docs, wave3 2 code+1 docs), 文件清单 = 5 service + provider + daily_pipeline + 6 测试 + fixture + 2 docs + 3 summaries, 无越界文件 |
| 全失败无半成品 | `test_capture_all_failed_no_partition` | fail-closed: 全不完整 → `tick_staging/date={T}` 目录不存在 |
| 单飞/调度形 | `test_sidecar_jobs_registered_in_scheduler` | 三 job id/时点/时区/replace_existing/misfire_grace_time 捕获断言 + 09:26 同槽位不同 id + 既有 job 零回归 + grep 门禁 `_run_tracked(_sidecar_*, _SIDECAR_*_JOB_ID)` |

## 2. 逐需求证据 (REQ-by-REQ)

### SDC-01 — 盘中采集 + staging + 三重对账 — **PASS**

证据 (auction_capture.py 全文 + auction_reconcile.py 全文 + stockdb_provider.get_ticks + 12 capture + 10 reconcile 测试 + 夹具实锤):

- **fetch-on-miss 单次 GET 全窗口** (get_ticks, provider): `GET /v1/ticks/{prefix}?date=T` — 服务端湖文件缺失 → 首次 GET 触发全窗口采集落盘, 文件存在后永不刷新; 请求**必带 date=T** (09:15 前无 date 服务端回退上一交易日, Pitfall 3) — 测试断言 `fake.calls == [("SH600519", date(2026,8,7))]`; 60/min 档位进程级共享限速器对齐; 零盘中轮询面 (research 明示轮询 = [CRITICAL] 反模式)。
- **staging 10 列独立湖** (`tick_staging/date={T}/part.parquet`): 10 列 `[symbol, trade_date, time, price, vol_hand, num_trades, buyorsell, source, fetched_at, ingested_at]` 顺序冻结 schema (pl.Datetime us, Asia/Shanghai/UTC aware), temp+os.replace 原子写; 根目录 `tick_staging` 与 canonical `kline_auction` 物理分离; `_DATE_RE` fullmatch 防路径穿越。测试断言 df.columns == 10 列且 height==87 (85 窗口 + 回显 + 重复撮合逐条保留)。
- **完整性 fail-closed 三拒** (`_validate_tick_window`): 归属日==T (09:15 前回退昨日 → 拒) ∧ 09:25:00 num_trades>0 撮合行存在 ∧ 窗口行数 ≥40 (3s×10min 理论 ≈200 / 实测 85 的保守阈值); 任一失败 → 该 symbol 不落分区 + `incomplete:…` reason; 全失败 → 无分区 (绝不写半成品); 部分成功 → ok/failed 计数 + manifest `symbols_failed` 诚实。
- **采集池 pool-gated** (`resolve_sidecar_pool`): 配置白名单 `auction_sidecar_symbols` (非空优先) → 缺省 watchlist 自选池; ≤200 硬 cap + truncated 注记 (5537 全量盘中不可行 descope, A2); suffix→prefix 归一 (`_to_prefix` 单一事实源); 归一失败 → `unparsable_symbol` 不猜。
- **三重对账 22,639,818 闭合** (`reconcile_window`): staged 09:25 撮合行 vs stockdb `/v1/minute` 09:30 bar (两条独立端点互证); `reconcile_match` = price 1e-6 ∧ vol 恒等 (手) ∧ amount 仅 OHLC 全等时派生 (`price×vol×100 == volume×close×100`, 契约 173×100×1308.66 = **22,639,818.0**, 测试 approx 断言); OHLC 不全等 → amount UNKNOWN (`ohlc_not_closed`), status 视为 mismatch, 绝不猜 (Pitfall 7)。09:30 bar 缺失 → 300s 重试 1 次 → 仍无 → per-symbol pending + 顶层 pending (A5); 无 staging/无撮合行 → `staging_missing` 诚实不伪造; `end=T+1` 端日语义 (provider 内置); 结果原子写回 manifest `reconciliation` 块 (旧键保留)。
- **夹具实锤 RESEARCH 锚点** (sh600519_20260807_window.json): 87 行, 09:15:07 起 3s 快照级 (09:15:07→09:15:10→09:15:13, gap 分布 47×3s/13×6s/6×9s); 09:24:58 前全 num_trades=0 (虚拟匹配非逐笔); 09:25:00 撮合行 price=1308.66 / vol_hand=173 / num_trades=120 (真实 120 笔) / buyorsell=2; 09:25:01 回显行 (num_trades=0) + 09:25:04 重复撮合行 (同值 120); 09:30:00 首根连续竞价行 (1302.5/27/19) — 后两者为「虚拟行永不入湖」与「单 symbol 单日单行」提供排除样本。

### SDC-02 — T-day 逐日累积 + DATA-06 映射 — **PASS**

证据 (auction_promote.py 全文 + 14 promote 测试):

- **提审闸门 fail-closed** (Pitfall 6): 当日 staging manifest `completeness.ok == True` ∧ `reconciliation.status == "closed"` — 当日 staging 判定, **绝不用** `resolve_auction_probe()` (tick 源不在 probe 枚举, 复用恒不过); 闸门不过 → 0 写 + 显式 reason (`manifest_missing` / `manifest_unreadable` / `capture_incomplete` / `reconciliation_not_closed` / `staging_missing` / `staging_schema` / `no_match_rows`), 绝不静默。gate 三拒测试独立锁死。
- **仅撮合行升湖**: 过滤 `time∈[09:25:00, 09:25:59] ∧ num_trades>0` → sort(time) → `unique(subset=["symbol"], keep="first")` (单 symbol 单日单行; 09:25:04 重复撮合行被去重, plan > research 骨架修正显式记录); 虚拟快照行 (num_trades=0) 与 09:25:01 回显行永不入湖 — `test_promote_excludes_virtual_rows` 断言 df.height==1, datetime==09:25:00, auction_volume==17300。
- **单位映射锁死**: 手→股 ×100 (`auction_volume=vol_hand×100`), 元 = `price×vol_hand×100` (契约 22,639,818 元), `auction_virtual_price=price` (xyz_provider.py:247 `current` 同语义); num_trades 只进返回/manifest 元数据 — canonical 无此列。
- **T-day 逐日累积** (`promote_trading_day`): 自 T-day 起逐日提审, 聚合 `{promoted_dates, skipped:[{date, reason}], total_written}`; 无 staging → skipped (staging_missing) 不写湖不报错; gate 拒绝 → skipped (reason 透传) — 全链路诚实可观测; 幂等天然 (merge-upsert + written=新增键计数) — `test_promote_rerun_idempotent` 断言重跑 written==0 且分区行数不变; 两日累积测试断言 promoted_dates==[08-06, 08-07], total_written==2。
- **DATA-06 诚实映射** (probe 确认后不猜测): `auction_unmatched_volume` **诚实缺列** — TickBar 10 字段 / 东财 details 7 字段 / QuoteSnapshot / depth 五档均无未匹配量字段 (RESEARCH.md:12 实锤), `_PROMOTE_COLS` 只含 4 canonical + virtual_price, 绝不构造/绝不 0 填 — `test_unmatched_volume_never_emitted` 逐字断言列不在 df.columns。
- **virtual_price 交叉验证** (`cross_validate_virtual_price`): kline_auction.auction_virtual_price vs kline_daily.open 独立第二来源互证 (镜像 verify_auction_backfill [4] 1e-6); 逐 symbol `{symbol, virtual_price, kline_open, diff, ok}`; 无 kline_daily 当日分区 → `{skipped, reason:"no_kline_daily"}` 诚实标注绝不吞; `test_cross_validate_virtual_price_closed` 断言 diff<=1e-6, drift 用例断言 all_ok False 如实报告。

### SDC-03 — 诚实门 + 台账 + 告警 + 调度 — **PASS**

证据 (auction_sidecar_ledger.py 全文 + daily_pipeline.py:1080-1286,1376-1418 + 10 ledger + 9 pipeline 测试):

- **台账 JSONL W-5 键集** (`append_ledger`): 成功态 7 键逐字 `{job, trade_date, requested, ok, failed_symbols, started_at, finished_at}` (CN 墙钟 isoformat, 显式可覆盖); **fail-closed 键形不变量** — ok==0 且无 reason/skipped → 自动补 `reason="fail_closed"` (失败态绝不无因, 显式 reason 优先); 非交易日行 `skipped:"no_data"` 与 reason 互斥 — 测试逐键断言锁死。JSONL append + threading.Lock; 滚动清理镜像 alert_store (MAX_DAYS=7 ∧ MAX_RECORDS=5000 取交集, PRUNE_EVERY=20, temp+os.replace 原子写) — `test_ledger_rolling_prune` monkeypatch 写 8 清 3 不膨胀; `list_ledger` 持锁读 + job 过滤 + 时间倒序 + 限量。
- **交易日判定 = 数据在场** (`confirm_trading_day`): 分钟 09:30 bar 存在 ⇒ 交易日 (AQ 无日历服务, Q6/A5); 缺失 → sleep 300s 重试 1 次 → 仍无 → False; 与 43-01 reconcile `trading_day_confirmed` 同源同判定点 — `test_trading_day_confirmed_by_0930_bar` 三态 (有/无/重试恢复) 锁定。
- **诚实门告警** (`evaluate_sidecar_alerts` 纯函数): 交易日 ∧ ok<requested → `auction_sidecar_capture_missing` {ts, rule_id, source, trade_date, requested, ok, failed_symbols}; 交易日 ∧ status=="mismatch" → `auction_sidecar_reconcile_fail` {ts, rule_id, source, trade_date, checks}; 非交易日 → 零告警 (假日不告警风暴); 正常日 (ok==requested ∧ closed) → 零事件零噪声 — 四测试各锁一面; 事件经 `alert_store.append` 落 `data/user_data/alerts.jsonl` (/api/alerts 查询面既有)。
- **三 job 调度注册** (start_scheduler): 09:26 `auction_sidecar_capture` / 09:40 `auction_sidecar_reconcile` / 15:40 `auction_sidecar_promote`, 全 CronTrigger `day_of_week="mon-fri"` Asia/Shanghai + `lambda: _run_tracked(fn, job_id)` 单飞 + `replace_existing=True`; misfire_grace_time 1800/1800/3600 (盘前窄窗镜像 premarket, EOD 宽窗); 09:26 与 `premarket_pool_preview` 同槽位不同 id (多 job 并发合法) — `test_sidecar_jobs_registered_in_scheduler` 形锁死 + 既有 job (instruments/pipeline/pool_eod/premarket/depth) 零回归断言。
- **job 接线** (_sidecar_capture/_sidecar_reconcile/_sidecar_promote): capture — 池解析 → `capture_auction_window` → 台账 (no_pool/capture_all_failed 显式 reason); reconcile — `reconcile_window` → trading_day 透传 → 非交易日台账 skipped_no_data 零告警 → 交易日 `read_sidecar_capture_state` (无 manifest → 池解析给 requested 提示, ok=0 → capture_missing 可告 — 「09:26 后缺失可告」) → `evaluate_sidecar_alerts` → events 透传台账; promote — `promote_trading_day([today])` → 台账 (reason 透传); 无 app state → 诚实 skip 不崩; `_run_tracked` 异常 → job_store 标记 failed 不吞。5 接线测试 (采集台账 / mismatch 告警链 / 无 manifest capture_missing / 非交易日静默 / promote 台账) hermetic stub seam 零网络全绿。

## 3. 独立测试跑 (本 verifier)

```
$ cd backend && .venv/bin/python -m pytest tests/test_auction_capture.py tests/test_auction_reconcile.py \
    tests/test_auction_promote.py tests/test_auction_sidecar_ledger.py tests/test_auction_columns.py \
    tests/test_auction_probe.py tests/test_minute_sync_verify.py tests/test_auction_sync.py \
    tests/test_stockdb_provider.py tests/test_daily_pipeline_refresh.py -q
125 passed, 1 skipped in 3.07s
```

| 文件 | 结果 | 构成 |
|---|---|---|
| test_auction_capture.py | 12 passed | 端到端 staging 10 列 / 完整性三拒 / 池解析四态 / 部分失败 / 全失败无分区 / 池合并归一失败 |
| test_auction_reconcile.py | 10 passed | closed 锚点 22,639,818 / price+vol mismatch / OHLC 非全等 amount UNKNOWN / end=T+1 / 重试 pending+恢复 / staging_missing / manifest 旧键保留 |
| test_auction_promote.py | 14 passed | 撮合行端到端 / 虚拟行排除 / gate 三拒 / no_match / 两日累积 / 幂等重跑 / skipped / manifest 块 / 交叉验证三态 / unmatched 永不产出 |
| test_auction_sidecar_ledger.py | 10 passed | W-5 键集 / fail-closed reason / 滚动清理 / 过滤倒序 / 交易日三态 / capture_missing / reconcile_fail / 非交易日零告警 / 正常日零噪声 / manifest 推导 |
| test_daily_pipeline_refresh.py | 9 passed | 3 既有 + 6 sidecar (注册形锁死 + 5 接线) |
| test_stockdb_provider.py | 20 passed | 含 get_ticks date=T 契约 + typed 异常面 |
| 回归族 (sync/columns/probe/minute_sync_verify) | 50 passed, 1 skipped | 诚实回归 — 1 skip 为既有 network-gated probe (test_auction_probe.py:276, 非本 phase 新增) |

核对 executor 声明: 43-01 24 新 (12+10+2 get_ticks) ✓ / 43-02 14 ✓ / 43-03 19 (10 ledger + 9 pipeline) ✓ / 全链路 46 ✓ (capture+reconcile+promote+ledger = 12+10+14+10) / 回归族 50+1 skipped ✓ — 数字与本 verifier 独立跑逐字一致。

## 4. 诚实性专项核验

| 专项 | 证据 (代码读 + 测试断言) | 结果 |
|---|---|---|
| 虚拟量绝不入 canonical | 提审过滤 (time∈09:25:00..09:25:59 ∧ num_trades>0) + 555..565 谓词双保险; `test_promote_excludes_virtual_rows` (df.height==1, datetime==09:25:00, 虚拟/回显/重复全排除) | **通过** |
| 单位映射锁死 | 手→股 ×100, 元=price×vol×100 — 契约 173×100×1308.66=22,639,818 (reconcile 锚点 + promote 输出双面断言) | **通过** |
| unmatched 诚实缺列 | `_PROMOTE_COLS` 无该列; `test_unmatched_volume_never_emitted` 逐字断言 `"auction_unmatched_volume" not in df.columns` (绝不 0 填) | **通过** |
| virtual_price 不猜测 | = 09:25 price (xyz `current` 同语义) + `cross_validate_virtual_price` vs kline_daily.open 1e-6 (diff<=1e-6 断言); 无 daily 分区 → skipped+reason 诚实标注 | **通过** |
| fail-closed 三面 | 采集 (不完整 → 无分区 + reason) / 提审 (gate 不过 → 0 写 + reason) / 台账 (ok==0 无因 → 自动 fail_closed) — 键形不变量测试逐键断言 | **通过** |
| 告警不噪声 | 交易日正常 (ok==requested ∧ closed) → 零事件; 非交易日 → 零告警 + skipped_no_data 台账; 事件落 alerts.jsonl 可查询 | **通过** |
| 幂等不重复 | promote 重跑 written==0 行数不变; reconcile 重跑 manifest 旧键保留; capture 部分失败重跑不写半成品 | **通过** |
| 对账不误报 | 09:30 bar 缺失 → 300s 重试 1 次 → pending (A5) 非 mismatch; 交易日判定同源 (数据在场) 不告警风暴 | **通过** |

## 5. ROADMAP/需求逐句对照

| 需求句 | 证据 | 结果 |
|---|---|---|
| SDC-01: 盘中 sidecar 采集 — 09:15-09:25 逐秒快照 + 09:25 撮合行定时采集 (独立脚本 + 盘中 cron 窗口) | get_ticks 单次 GET 全窗口 (3s 源原生粒度, A1) + capture_auction_window 完整性三拒 + 09:26 capture job (CronTrigger mon-fri) — 独立 service 模块 + 调度注册, 非盘内联 | PASS (3s 粒度按 A1 重述, 见 human_items #2) |
| SDC-01: live 对账闭合 (09:25 撮合行 price×vol == intraday 09:30 bar amt) | reconcile_window 三重闭合 — 22,639,818 元契约锚点 (173×100×1308.66) 双端点互证, price 1e-6 / vol 恒等 / amount OHLC 全等派生 | PASS (闭合锚点 = 2026-08-07 live 实测体冻结夹具; live 重验 deploy-gated) |
| SDC-01: 数据落 staging (tick 湖/独立目录), 不入 canonical 湖 (虚拟量非成交) | `tick_staging/date={T}` 物理独立 + canonical 仅经提审 gate (completeness.ok ∧ reconciliation.closed) + 撮合行过滤 | PASS |
| SDC-02: T-day 累积 — 自 T-day 逐日累积真实竞价列 (auction_volume/amount/price, 多 num_trades 元数据) | promote_trading_day 逐日 + promote_to_canonical 单位映射 ×100 + num_trades 只进元数据/manifest (canonical 无此列) + 幂等重跑 | PASS |
| SDC-02: DATA-06 派生输入 (unmatched_volume/virtual_price) 语义经 probe 确认后映射 (不猜测) | RESEARCH 实锤 unmatched 不可得 (TickBar/东财 details/QuoteSnapshot/depth 均无字段) → 诚实缺列; virtual_price=price + kline_daily.open 1e-6 交叉验证 | PASS |
| SDC-03: 采集失败 fail-closed (当日无数据 → 无当日分区, 不伪造) | 完整性三拒 + 全失败无分区 + gate 三拒 + 台账 reason 不变量 | PASS |
| SDC-03: sidecar 状态可观测 (台账/告警, 09:26 后缺失可告) | JSONL 台账 W-5 键集 + capture_missing/reconcile_fail 告警 (alert_store → alerts.jsonl) + 09:40 判定链 | PASS |

## 6. PLAN-CHECK 对照 (0 blocker 6 warnings, 执行期消化)

- **A1 (「逐秒快照」→ 3s 源原生粒度)**: 已按 43-01-PLAN.md:45 执行 — 验收口径「3s 快照级逐条捕获 (窗口行数 ≥40)」, 夹具 gap 分布如实 (47×3s/13×6s/6×9s), 绝不伪造逐秒。REQUIREMENTS.md 文本未改 (overrides 0) — 转 human_items #2。
- **A2 (池 ≤200 pool-gated)**: `_POOL_CAP=200` + 截断注记 + 白名单默认自选池, 测试四态锁定。**无残留**。
- **DATA-06 (unmatched 诚实缺列)**: probe 结论实锤 → `_PROMOTE_COLS` 无该列 + 测试逐字断言。**无残留**。
- **Pitfall 6 (提审 gate 不用 probe)**: 当日 staging manifest 判定, gate 三拒测试 (manifest_missing / completeness_not_ok / reconciliation_not_closed) 独立锁定。**无残留**。
- **Pitfall 7 (amount 不猜)**: OHLC 非全等 → amount_reason="ohlc_not_closed" + mismatch, 绝不派生。**无残留**。
- **Pitfall 3 (请求必带 date=T)**: get_ticks date=T 断言 + 昨日归属日拒收夹具。**无残留**。

## 7. Human items (sandbox 无法断言 / 待用户)

1. **live 交易日采集未发生 (deploy-gated, Phase 44)**: 三 job 已注册但调度器需部署后首个交易日实跑; 采集/对账/提审全链路目前仅 canned 夹具 + hermetic 测试验证。部署面首验项 = Phase 44 DEP-03 D8 点亮门 (09:26 采集 → 09:40 对账 closed → 15:40 提审 → kline_auction 当日分区存在), 另需确认 3018 容器能访问 stockdb 127.0.0.1:8000 (DEP-01)。
2. **SDC-01「逐秒快照」按 A1 重述为 3s 源原生粒度**: RESEARCH 实测源粒度 = TDX L1 3 秒快照级 (gap 分布 47×3s 占绝对多数), 实现按「3s 快照级逐条捕获 + 窗口 ≥40 行」验收 — 43-01-PLAN.md:45 显式记录但 REQUIREMENTS.md 文本未同步修订; 待用户确认需求文本定稿口径 (改文本或接受 3s 解释)。
3. **virtual_price 交叉验证未接线调度 job**: `cross_validate_virtual_price` 为独立可调用函数 (kline_daily.open 1e-6 互证), 未挂入任何 cron job — 若需周期性自动交叉验证, 需决策 (可加 15:41 job 或手动/报告期调用); 当前为机制交付 + 测试锁定。
4. **交易日判定 = 数据在场 (无日历服务)**: 依赖服务端在 mon-fri 假日无 09:30 bar 产出 (假日自然零分区零告警); 首个 A 股假日 (如国庆/春节休市周) 需实测确认服务端行为符合「非交易日静默」预期 — 部署后首个假日观察项。
5. **num_trades 语义锚点 (0=虚拟 / 120=真) 为单日单标的样本**: 2026-08-07 SH600519 一次 live 实测冻结; 语义判断 (num_trades>0 = 撮合行) 跨标的/跨日普适性需随 T-day 累积 (自选池多标的) 持续复核, 若出现撮合行 num_trades==0 的异常标的需重新审视谓词。

## 8. Honesty notes

- 所有 PASS 证据为本 verifier 亲自重观察: 自己的 pytest 跑 (125 passed / 1 skipped, 含 46 全链路 + 50 回归族 + 9 pipeline + 20 provider 分项, `-q`/`-v` 输出实录), 自己的 git log/show/status 跑 (12 commits 顺序与 claim 一致, dep/Watchlist/文件清单守卫), 自己的夹具独立解析 (3s 粒度 / 85 虚拟行 / 120 笔撮合行 / 22,639,818 闭合 / num_trades 分布逐条重算)。
- 未采信 SUMMARY 文本: 测试数 (24/14/19/46/50), pass/skip 数, 锚点数字, 调度时点均独立重推导核实。
- 诚实性纪律三面确认: (a) 虚拟量不入 canonical — 谓词 + 555..565 双保险 + 测试锁单行 09:25:00; (b) amount 不猜 — OHLC 非全等显式 UNKNOWN + mismatch; (c) 覆盖如实 — live 交易日采集未发生即如实标注 deploy-gated, 绝不以 canned 测试冒充 live 验证。
- `frontend/src/pages/Watchlist.tsx` 全程未读取, 仅经 `git diff/status` 核验: 提交内零触碰, 工作树唯一未暂存用户改动。
- 全量 backend 套件按分工由 orchestrator 收口, 本 verifier 只跑 43 族指定 10 文件 + 回归族, 不虚报全量。
