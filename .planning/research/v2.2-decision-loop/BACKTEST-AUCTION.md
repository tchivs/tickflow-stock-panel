# 竞价策略历史验证 (Backtest-Auction) — v2.2 research

**Domain:** A股竞价/盘前策略的历史信号质量验证
**Researched:** 2026-08-06
**Researcher:** ResearcherBacktest
**Mode:** ecosystem (feasibility sub-mode for auction backtest seam)
**Overall confidence:** MEDIUM — 代码路径为直接观测; 湖覆盖率为当前环境实测; 生产部署后的竞价湖覆盖速度为 `[INFERENCE]`

---

## 现状 (current state)

### 1. 回测数据装载 seam

策略回测 (`backend/app/backtest/strategy.py`) 与信号/因子回测共用同一个数据装载入口
`BacktestEngine.load_panel` (`backend/app/backtest/engine.py:191-200`) → `_load_panel_inner`
(`engine.py:202-276`):

- **快路径:** `repo.get_enriched_range(start, end, symbols, columns)` — 复用启动时
  `_refresh_enriched` 预计算的 `_enriched_history_cache` (`repository.py:461-556`,
  `get_enriched_range` `repository.py:966-1010`)。缓存由 `compute_indicators` 构建,
  含全套技术指标 (open_gap / change_pct / vol_ratio_5d / momentum / rsi …), **不含竞价列**。
- **慢路径:** `scan_enriched_parquet(enriched_glob)` 扫 `kline_daily_enriched/**/*.parquet`
  (`parquet.py:48-58` `ENRICHED_STORAGE_SCHEMA` — 仅 15 列 symbol/date/OHLCV/amount/
  raw_*/turnover_rate/consecutive_limit_*/quote_ts, **无 auction_***), columns 缺省时再调
  `compute_all` (`indicators/pipeline.py:833`) 补全指标+信号。**仍无竞价列**。
- **冻结面板:** `StrategyBacktestService.freeze_panel_artifact` (`strategy.py:89-115`)
  把 `load_panel` 产出原样持久化为 checksum 受治理面板 (`frozen_panel.py`), 竞价列不会凭空出现。

**结论:** 回测面板今天物理上不可能含竞价列。`requires_auction_data=True` 的策略在回测里
直接空池 (见 §现状.3), 竞价值从不上回测数据路径。

### 2. 竞价列的读路径注入 (live-only)

竞价列 (`auction_volume` / `auction_amount` / `auction_volume_ratio` /
`auction_unmatched_amount`) 是 **probe×分区双闸门** 的读路径左联注入, 不落 enriched 存储:

- `attach_auction_columns` (`services/auction_columns.py:89-151`):
  - 闸门 1: `resolve_auction_probe().status == available` (`auction_probe.py:139`), 否则原样返回;
  - 闸门 2: `kline_auction/date={trade_date}/part.parquet` 存在且有行, 否则原样返回;
  - 通过后按 symbol 去重为单行 (防多窗口行 fan-out), 计算 `auction_volume_ratio` =
    竞价量 ÷ 前5日均量(不含当日, PIT-safe), 左联注入。
  - **平台铁律:** 分区不存在 → 诚实按日空态 (列缺席), 绝不做 null-as-present
    (`auction_columns.py:95-96` 注释)。
- 唯一调用点: `ScreenerService._attach_auction` (`screener.py:306-314`), 被
  `_load_enriched_for_date` (`screener.py:250-297`) 在**单日 as-of 帧**上调用。
  即: **只有 run_all / run_all_with_hits 的按日选股路径会注入竞价列; 回测的区间面板不会。**

### 3. `run_all_with_hits` 与 requires_auction_data 过滤

`ScreenerService.run_all_with_hits` (`screener.py:722-812`):
- 签名: `run_all_with_hits(self, as_of: date, strategy_ids=None, engine=None) -> dict`,
  输出 `{sid: {total, as_of, rows}}`, 每行附 `hit_factors` (STRAT-02)。
- **本身不按 requires_auction_data 过滤** — 短路在 `StrategyEngine.run`
  (`strategy/engine.py:345-348`): `requires_auction_data=True` 且帧缺 `auction_volume`
  → 返回空 `StrategyResult` (fail-closed); 策略 `filter` 的 `pl.lit(False)` 守卫是第二层。
- probe 门控通过 `_attach_auction` 在数据层完成: probe 非 available 或缺分区 → 列缺席 →
  requires_auction_data 策略空池; `auction_alpha` (requires=False) 走派生分支 (open_gap+
  vol_ratio_5d+amount), 永不与真列混用。

### 4. 9 个竞价/盘前策略的列依赖 (全部直接观测自 builtin 源文件)

| id | 名称 | requires_auction_data | time_window | 消费列 | 无竞价列回测行为 |
|---|---|---|---|---|---|
| `auction_fast_grab` | 极速抢筹 | **True** | pre_open | open_gap, auction_volume_ratio, auction_amount | 空池 (filter 判列缺席 → pl.lit(False)) |
| `auction_allround` | 竞价全面 | **True** | pre_open | open_gap, auction_volume_ratio, auction_amount | 空池 |
| `t1_flash` | T+1闪电 | **True** | pre_open | open_gap, auction_volume_ratio, auction_amount | 空池 |
| `auction_intraday_confirm` | 盘中确认 | **True** | intraday | open_gap + 分钟确认(09:45) | 空池; 且回测 seam 不调用 minute_confirm_fn |
| `auction_alpha` | 竞价阿尔法 | False (双分支) | pre_open | 真列: auction_volume_ratio/auction_amount; 派生: open_gap/vol_ratio_5d/amount | **可跑派生分支** (标注非真列) |
| `golden_230` | 金色两点半 | False | post_close | change_pct, close/open, amplitude, amount | **可跑** (EOD 列, 非竞价窗口) |
| `auction_bullish` | 竞价多头 (v1.3) | False | intraday | open_gap, change_pct | **可跑** (EOD 代理) |
| `auction_preopen_quant` | 盘前强势量化 (v1.3) | False | intraday | open_gap, vol_ratio_5d | **可跑** (EOD 代理) |
| `auction_early_star` | 早盘之星 (v1.3) | False | intraday | open_gap 或 change_pct | **可跑** (EOD 代理) |

**回测服务的行为:** `_build_candidate_filter_mask` (`strategy.py:522-570`) 直接调
`s.filter_fn(panel, params)`, 不经过 engine.run 的短路; 4 个 requires_auction_data 策略
的 filter 判列缺席 → 全 False 候选掩码 → `_build_entry_mask_from_candidate`
(`strategy.py:573-598`) 返回全 False → `run` 返回 `"在指定区间内未产生买入信号"`。

### 5. 数据湖覆盖实测 (当前环境, 直接观测)

| 湖 | 分区数 | 日期范围 |
|---|---|---|
| `data/kline_daily_enriched/date=*` | **248** | 2025-07-29 ~ 2026-08-05 |
| `data/kline_auction/date=*` | **0** | — (空) |
| `data/kline_minute/date=*` | **0** | — (空) |
| `data/screener_results/date=*` (part.json) | **0** | — (空) |
| `data/premarket_results/date=*` (part.json) | **0** | — (空) |

- enriched 分区实读 schema: 15 列, 无 auction_* (与 `ENRICHED_STORAGE_SCHEMA` 一致)。
- **无历史竞价回填路径:** `sync_and_persist_auction` (`services/auction_sync.py:97-152`)
  只由每日管道按当日 `trade_date` 调用 (`jobs/daily_pipeline.py:704-707`); 不存在
  "回填历史竞价日" 的任何代码。`pool_backfill` (`services/pool_backfill.py`) 只回填
  screener_results 点快照。
- `[INFERENCE]` 生产部署若配置了竞价数据源, kline_auction 湖从竞价特性上线之日起
  每交易日 +1 分区, **永远无法回溯覆盖上线前的日期**; 覆盖天数的下界即竞价特性年龄。

---

## 方案选项 (3 options, 诚实空态优先)

### 选项 A — 只读信号质量报告 (research-only GET) **[推荐]**

新增 `GET /api/research/auction/validation` (只读, 零写零执行), 分两步:

1. **竞价列区间注入原语** `attach_auction_columns_range(panel, start, end, repo)`:
   - 扫 `kline_auction/date=*/part.parquet` 落在 `[start,end]` 的分区 (probe available 时);
   - 每分区按 symbol 去重单行 (09:15-09:25 窗口内, 镜像 `auction_columns.py:122-146`);
   - 按 (symbol,date) 左联注入日线面板; **enabled-dates 集合 = 有分区的交易日**,
     无分区日不纳入验证日集 (诚实按日空态, 绝不做 null-as-present);
   - `auction_volume_ratio` 用面板内 `volume` 的 shift(1).rolling_mean(5) 分母 (PIT-safe,
     与 `_attach_auction_volume_ratio` 同语义, 但向量化到多日)。
2. **信号质量统计:** 对每个策略, 复用 `StrategyBacktestService._build_candidate_filter_mask`
   式向量化 filter 应用到 enabled-dates 面板 → 逐日 hit 列表 → 前瞻收益统计:
   - 口径锁死 (BT-04): 信号日 = T (竞价定开盘价), 入场 = T 开盘价 (竞价已知),
     主结果 = T+1 开盘/收盘前瞻收益 与 T+1 开盘跳空 (open_{T+1}/close_T − 1);
   - 输出: 每策略 `{branch: real|derived|eod, n_dates, n_hits, coverage,
     forward_stats{next_day_open_ret/next_day_close_ret/open_gap_outcome: mean/median/win_rate},
     per_date[{date,n_hits,avg_ret}], data_gate}`。
   - 湖空时 → 200 `{data_gate:"empty", coverage:0, strategies:[], probe: {...}}` (诚实空态,
     镜像 auction_history 的空态语义, 非 404/500)。

**权衡:**
- 优点: 满足 POOL-03 零执行边界; 零新增运行时依赖 (纯 polars + 现有服务);
  直接回答 "策略命中的是否真的会动"; 湖空时诚实空, 湖有数据时立即可用;
  不触碰受治理回测/frozen panel seam (竞价列 provenance 不污染冻结面板)。
- 缺点: 不做组合/资金/滑点模拟 → 不是完整回测; 只评价信号质量 (选股能力),
  不含 T+1 卖出模拟 (对 t1_flash 的 EXIT 语义是弱化); 需要新增注入原语 (一次性开发)。

### 选项 B — 全量竞价启用回测 (扩展 StrategyBacktestService)

在 `StrategyBacktestConfig` 加 `auction_only: bool`, `_load_panel_inner` 增加竞价列注入:
- 面板裁剪到 auction-enabled 日期; 注竞价列; requires_auction_data 策略得以走完整
  `simulate_portfolio` / `simulate_independent_candidates` (entry_fill=open_t+1, 手续费,
  滑点, 仓位)。

**权衡:**
- 优点: 给出完整净值/回撤/收益曲线; 与现有回测 UI/SSE/优化器/走前向复用。
- 缺点: **改动受治理回测 seam** — frozen panel scope/checksum 需纳入竞价列 (竞价列依赖
  冻结时刻的湖状态, provenance 复杂); 湖空时整条回测不可用 (必须诚实报错, 无法只评价
  派生分支); 盘中确认策略的 minute_confirm_fn 在回测 seam 里从未被调用 (需要额外接入
  分钟数据, 而 kline_minute 当前也空); 服务器回测区间 guard 186 天 (`backtest.py:29`),
  与 248 天 enriched 的完整覆盖冲突。工作量明显大于 A。

### 选项 C — 历史股池快照重放 (replay screener_results)

读 `screener_results/date=*/part.json` (含 `snapshot_origin`, 冻结 hit 列表 +
`strategy_version` 指纹), 对每个快照日的每策略 hit rows JOIN enriched 前瞻收益做统计。
- **优点:** 是生产 EOD/backfill 管道实际产出的 ground truth (零重算漂移); 直接验证
  "当时实际给的池" 的质量; `strategy_fingerprint` 保证策略版本不被静默重解释。
- **缺点:** 快照行只含 hit 行, 不含全市场竞价列值 → **无法测量漏报** (false negatives),
  也无法对非 hit 股算 auction_volume_ratio 阈值; 当前 screener_results 为 0 分区,
  需先跑 backfill; 而 backfill 走 `run_all_with_hits`, 湖空时 requires_auction_data
  策略的每日期望就是空池 → 重放只会报告 "0 hits on all dates", 不是真列验证。
  只能作为 A 的补充 (验证管道产出), 不能独立完成 "竞价信号历史验证"。

---

## 推荐方案

**推荐 选项 A (只读信号质量报告), 以竞价湖数据闸门为前提; 把 选项 B 标为 v2.3+
演进候选; 把 选项 C 标为互补管道产出验证 (Phase 25 已有快照时可增量做)。**

理由:
1. **诚实边界:** 当前 kline_auction 湖 0 分区、无历史回填路径。唯一能今天落地且
   湖空时仍诚实的验证形态, 就是 "报告数据覆盖 + 湖空即空态" 的只读报告。
   A 在湖有数据后立即对 4 个真列策略给出真实信号质量; 在湖空时对 5 个
   派生/EOD 策略仍可给出历史验证 (明确标注 branch=derived/eod, 绝不冒充真列)。
2. **平台约束:** POOL-03 零执行 (A 是 GET-only, 零写), 零新增运行时依赖, fail-closed +
   诚实标注 (branch 永不混用, 镜像 auction_alpha/early_star 互斥律)。
3. **不动受治理 seam:** B 会把竞价列 provenance 卷进 frozen panel checksum 与
   walk-forward 折叠, 治理成本高且当前湖空时毫无收益。A 把竞价注入限定在独立研究
   只读路径, 不污染受治理回测的输入清单。
4. **补足决策闭环:** v2.2 的主题是 "决策闭环与历史纵深"。A 为 9 个策略补上
   "信号→结果" 的实证闭环, 与 ResearcherMonitor/Recap/Concept 的研究正交。

**关键实现前置 (A 的唯一实质新代码):** 向量化 `attach_auction_columns_range`。它应当
作为只读研究原语 (放 `app/services/auction_columns.py` 或独立 `app/research/` 模块),
严格复用双闸门语义与 PIT-safe 分母, 产出 per-date presence 元数据。

---

## 需求草案 (BT-0x, 可验证)

- **BT-01 数据覆盖报告 (honest gate).** 提供
  `auction_enabled_dates = kline_auction 分区 ∩ enriched 分区 (probe available 时)`;
  报告 `{probe: {status,...}, auction_enabled_dates:[...], total_enriched_dates:N,
  coverage_ratio, data_gate: "available"|"empty"}`。`kline_auction` 无分区或 probe
  非 available → `data_gate:"empty"`, **不**抛错/404/500, 后续策略段返回空。
  验收: 湖空时端点返回 200 且 `data_gate=="empty"`, `strategies==[]`。

- **BT-02 区间竞价列注入原语.**
  `attach_auction_columns_range(df: pl.DataFrame, start: date, end: date, repo) ->
  (pl.DataFrame, list[date])`: 对 `[start,end]` 内每个含分区的交易日, 按 symbol 去重单行
  左联注入 `auction_volume`/`auction_amount`/`auction_volume_ratio`; 返回
  enabled-dates 列表。**禁止** null-as-present (无分区日不产生行, 列只在 enabled-dates
  子面板上存在)。`auction_volume_ratio` 分母 = `volume.shift(1).rolling_mean(5).over("symbol")`
  (不含当日, 与 `_attach_auction_volume_ratio` 同语义)。验收: 分区缺日 → 该日不在
  enabled-dates; probe 非 available → 全空 (列缺席)。

- **BT-03 信号质量报告端点.**
  `GET /api/research/auction/validation?strategy_ids=&start=&end=&symbols=` 返回每策略
  `{strategy_id, branch: "real"|"derived"|"eod", requires_auction_data, n_dates, n_hits,
  coverage (n_hits per enabled date), forward_stats, per_date:[...], data_gate}`。
  候选掩码复用 `StrategyBacktestService._build_candidate_filter_mask` 的向量化语义。
  验收: `strategy_ids` 缺省跑全部 9 个; 空列表 → `{}` (镜像 run_all_with_hits 语义);
  未知 id → 忽略并记录, 不 500。

- **BT-04 前瞻口径锁死 (no lookahead, no silent fill).**
  信号日 = T (竞价定开盘价)。入场 = T 开盘价 (竞价已知, pre_open 白名单列已禁 EOD
  lookahead)。主结果:
  `next_day_open_ret = open_{T+1}/open_T − 1`,
  `next_day_close_ret = close_{T+1}/open_T − 1`,
  `open_gap_outcome = open_{T+1}/close_T − 1` (隔夜跳空)。
  结果日缺行 (停牌/退市/数据缺失) → 该 hit 不计入统计但计入 `n_missing_outcomes` 字段,
  绝不 0 填或前向填充。验收: 统计字段与口径定义逐一对应; 存在缺失日时
  `n_missing_outcomes>0` 且均值/胜率不包含缺失行。

- **BT-05 分支标注互斥 (never mix branches).**
  报告显式标注每策略实际运行的 branch: `real` (竞价列存在) / `derived`
  (auction_alpha 等派生回退) / `eod` (golden_230/bullish/preopen_quant/early_star 的
  EOD 列代理)。同一策略同一次报告只含一个 branch 的统计; 若某日期竞价列缺席而其他日存在,
  缺席日从 real 统计中剔除 (不落入 derived)。验收: `branch` 字段存在且与输入列存在性一致;
  真列策略 (fast_grab/allround/t1_flash/intraday_confirm) 在湖空时 `n_dates==0` 且
  `data_gate=="empty"`, 而非落到 derived。

- **BT-06 零执行 + 零新增依赖守卫.**
  端点与其辅助模块不写 kline_auction / screener_results / premarket_results /
  strategy_cache / frozen panel, 不 import 执行族模块 (broker/order/trade/execution/
  portfolio/position/account/transaction), 不新增运行时依赖。验收: AST 守卫测试
  (镜像 `tests/test_pool_hub.py` E3 形) 锁定禁止 import 集与零写调用。

- **BT-07 (v2.3+ 演进, 显式延后) 竞价启用全量回测.**
  待 kline_auction 湖有足够历史分区后, 评估在 `_load_panel_inner` 增加
  `auction_columns=True` + `restrict_to_auction_dates` 配置, 使 requires_auction_data
  策略可走完整组合回测; 需先解决 frozen panel scope/checksum 纳入竞价列 provenance
  与 minute_confirm_fn 接入。**本里程碑不实现**, 仅记录为后续候选。

---

## 风险 / 开放问题

1. **[HIGH] 湖空 = 真列验证不可用 (当前现实).** kline_auction 0 分区且无历史竞价回填。
   BT-03 在湖空时对 4 个真列策略只能诚实报空。若产品期望 "今天就验证极速抢筹",
   这是数据缺口而非代码缺口 — 必须先打通历史竞价数据 (上游源是否提供历史竞价? 需
   Researcher 与数据源评估; 超出本 research 的代码范围)。
2. **[MEDIUM] 派生/EOD 分支 ≠ 真列.** 对 auction_alpha 等 5 个策略, 历史验证跑的是
   派生/EOD 代理分支。报告必须让 branch 一目了然, 防止把 derived 结果当作真列结论。
3. **[MEDIUM] 盘中确认策略的分钟确认缺口.** `auction_intraday_confirm` 需要 09:45
   分钟帧; 回测 seam 不调用 minute_confirm_fn, 且 kline_minute 当前 0 分区。BT-03 对该
   策略只能验证日线初筛层 (open_gap≥2%), 需显式标注 `minute_confirm:"not_applied"`。
4. **[MEDIUM] 服务器回测 guard.** `BACKTEST_MAX_SERVER_DAYS=186` (`backtest.py:29`)
   会限制区间; BT-03 若复用 guard 需评估, 否则研究端点应自带覆盖提示 (248 天 enriched)。
5. **[LOW] 结果日缺失口径.** 停牌/退市的 T+1 缺失 → 必须计 `n_missing_outcomes` 而非
   静默剔除或填充, 避免胜率虚高。
6. **[开放] 与 Phase 25 快照的关系.** 若后续 screener_results 回填完成, 选项 C 的
   管道产出验证可增量补充 BT-03 (验证 "实际给池" vs "重算信号" 双视角), 需确认
   ResearcherRecap / ResearcherConcept 不重复覆盖。

---

## 关键锚点 (exact files/symbols/lines)

| 用途 | 锚点 |
|---|---|
| 回测装载 seam | `backend/app/backtest/engine.py:191-200` `load_panel`; `:202-276` `_load_panel_inner` |
| 回测策略候选/入场掩码 | `backend/app/backtest/strategy.py:522-570` `_build_candidate_filter_mask`; `:573-598` `_build_entry_mask_from_candidate` |
| 冻结面板 | `backend/app/backtest/strategy.py:89-115` `freeze_panel_artifact`; `backend/app/backtest/frozen_panel.py:44-73` `FrozenPanelArtifactStore.load` |
| enriched 存储 schema (无竞价列) | `backend/app/parquet.py:48-58` `ENRICHED_STORAGE_SCHEMA` |
| 竞价列注入双闸门 | `backend/app/services/auction_columns.py:89-151` `attach_auction_columns`; `:54-87` `_attach_auction_volume_ratio`; probe `services/auction_probe.py:139` `resolve_auction_probe` |
| 按日注入调用点 | `backend/app/services/screener.py:306-314` `_attach_auction`; `:250-297` `_load_enriched_for_date` |
| run_all_with_hits | `backend/app/services/screener.py:722-812` |
| requires_auction_data 短路 | `backend/app/strategy/engine.py:345-348` |
| 9 策略 | `backend/app/strategy/builtin/auction_fast_grab.py` `auction_alpha.py` `golden_230.py` `auction_allround.py` `t1_flash.py` `auction_intraday_confirm.py` `auction_bullish.py` `auction_preopen_quant.py` `auction_early_star.py` |
| 点快照湖 | `backend/app/services/pool_snapshot.py:39-183` `persist_point_snapshot`/`load_point_snapshot`/`list_backfill_gaps` |
| 回填 (无竞价历史回填) | `backend/app/services/pool_backfill.py:26-96` `run_pool_backfill` |
| 盘前预览独立湖 | `backend/app/services/premarket_snapshot.py` |
| 回测 API / guard | `backend/app/api/backtest.py:29` `BACKTEST_MAX_SERVER_DAYS`; `:216-...` `strategy_run` |
| 走前向骨架 | `backend/app/backtest/walkforward.py` `build_plan`/`run_walk_forward` |
| 数据湖实测 | `data/kline_daily_enriched/date=*` (248), `data/kline_auction` (0), `data/kline_minute` (0), `data/screener_results` (0) |
