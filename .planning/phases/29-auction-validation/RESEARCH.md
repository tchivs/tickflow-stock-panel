# Phase 29 竞价策略历史验证 (BT-01..06) — RESEARCH.md

**Phase:** 29-auction-validation (v2.2, 决策闭环)
**Researched:** 2026-08-06
**Researcher:** ResearcherP29
**Mode:** ecosystem (phase-implementation feasibility)
**Inputs:** `.planning/research/v2.2-decision-loop/BACKTEST-AUCTION.md` (领域研究, 选项 A), `.planning/research/v2.2-decision-loop/SUMMARY.md` (Phase 29 段)
**Overall confidence:** HIGH — 全部锚点本次直接实读源码/实测磁盘; 残余不确定项仅为外部数据源 (历史竞价可得性, [INFERENCE])

---

## 1. 现状 (verified anchors, 2026-08-06 实测)

### 1.1 回测装载 seam 物理无竞价列 (确认 BACKTEST-AUCTION §1 结论)

- `BacktestEngine.load_panel` (`backend/app/backtest/engine.py:191-200`) → `_load_panel_inner` (`engine.py:202-276`):
  - 快路径 `repo.get_enriched_range(start, end, symbols, columns)` (`repository.py:966-998`) — 启动时 `_refresh_enriched` 预计算缓存, 含全套指标列 (open_gap/change_pct/vol_ratio_5d/amount/momentum/rsi…), **无 auction_\***。
  - 慢路径 `scan_enriched_parquet` (`parquet.py:48-58` `ENRICHED_STORAGE_SCHEMA`, 15 列, **无 auction_\***) + `compute_all`。
- 冻结面板 `freeze_panel_artifact` (`backtest/strategy.py:89-115`) 原样持久化 → 竞价列不会凭空出现。
- **结论不变:** 回测面板物理上不可能含竞价列; 4 个 `requires_auction_data=True` 策略在回测里恒空池。

### 1.2 竞价列读路径双闸门 (逐行核对 `auction_columns.py:89-151`)

`attach_auction_columns(df, trade_date, repo)`:
1. 闸门 1: `resolve_auction_probe().status != available` → 原样返回 (列缺席);
2. 闸门 2: `kline_auction/date={trade_date.isoformat()}/part.parquet` 不存在或空 → 原样返回 (**绝不做 null-as-present**, `:95-96` 注释);
3. 通过后: 输入列可得时先 `compute_auction_unmatched_amount` (`:47-66`), 再 `_attach_auction_volume_ratio` (`:54-87`), 按 keep-list 裁剪 (`symbol` + `_AUCTION_REAL_COLS` + unmatched + ratio), **symbol 级去重 `unique(subset=["symbol"], keep="last")`** (防多窗口行 fan-out), 最后 `df.join(auction, on="symbol", how="left")`。

**PIT-safe 分母逐行核对 (`_attach_auction_volume_ratio`, `:54-87`):**
```python
hist = repo.get_enriched_history(trade_date, 6)          # 按交易日切片: 最后 7 个交易日含 trade_date
prior = hist.filter(pl.col("date") < trade_date)         # = trade_date 前 6 个交易日
avg = prior.group_by("symbol").agg(pl.col("volume").tail(5).mean())
```
`get_enriched_history` (`repository.py:937-958`) 用 `trading_dates[-(lookback_days+1)]` 按**交易日计数**裁剪 (非自然日) — 因此分母 = **T 前最近 5 个交易日的均量**, 且历史不足 5 日时取可用行均值 (`tail(5).mean()`)。无历史/prior 空 → 列缺席。

### 1.3 短路与 9 策略列依赖 (全部实读 builtin 源文件)

`StrategyEngine.run` (`strategy/engine.py:345-348`): `requires_auction_data` 且帧缺 `auction_volume` → 空 `StrategyResult` (fail-closed); 策略 filter 的 `pl.lit(False)` 守卫为第二层。

| id | 名称 | requires | time_window | 消费列 (filter) | 无竞价列回测行为 | branch |
|---|---|---|---|---|---|---|
| `auction_fast_grab` | 极速抢筹 | **True** | pre_open | open_gap, auction_volume_ratio, auction_amount | 空池 (列缺席 → `pl.lit(False)`) | **real** |
| `auction_allround` | 竞价全面 | **True** | pre_open | open_gap, auction_volume_ratio, auction_amount (+可选 `turnover_rate` EOD, 默认关) | 空池 | **real** |
| `t1_flash` | T+1闪电 | **True** | pre_open | open_gap, auction_volume_ratio, auction_amount | 空池 | **real** |
| `auction_intraday_confirm` | 盘中确认 | **True** | intraday | 日线初筛 open_gap ≥ 2% + `minute_confirm_fn` (09:45 分钟帧, `minute_confirm_required=True`) | 空池; 回测 seam 不调 minute_confirm_fn | **real** (分钟层标注 not_applied) |
| `auction_alpha` | 竞价阿尔法 | False (双分支) | pre_open | 真列: auction_volume_ratio/auction_amount/open_gap; 派生: open_gap/vol_ratio_5d/amount | **可跑派生分支** | **real 或 derived** (按列存在性互斥) |
| `golden_230` | 金色两点半 | False | post_close | change_pct, close>open (收阳), amplitude/amount (scoring) | **可跑** (EOD 列) | **eod** |
| `auction_bullish` | 竞价多头 (v1.3) | False | intraday | open_gap, change_pct | **可跑** (EOD 代理) | **eod** |
| `auction_preopen_quant` | 盘前强势量化 (v1.3) | False | intraday | open_gap, vol_ratio_5d | **可跑** (EOD 代理) | **eod** |
| `auction_early_star` | 早盘之星 (v1.3) | False | intraday | open_gap 或 change_pct (OR) | **可跑** (EOD 代理) | **eod** |

实测观察 (报告须镜像现行为, 不修复):
- `auction_alpha` 真列分支 `pl.col("auction_amount") >= 1_000_000` **硬编码** 1M, 未用 `params["min_auction_amount"]` (META 有该参数但 filter 未消费) — 报告用 META 默认参数, 镜像现状, 修复属范围外。
- `auction_allround` 的 `use_turnover` 默认 False → 默认参数下不消费 EOD 列 (保持 pre_open 白名单语义)。

### 1.4 湖覆盖实测 (与 BACKTEST-AUCTION §5 一致, 本次复核)

| 湖 | 分区数 | 备注 |
|---|---|---|
| `data/kline_daily_enriched/date=*` | **248** | 2025-07-29 ~ 2026-08-05 |
| `data/kline_auction/date=*` | **0** | 空 |
| `data/kline_minute/date=*` | **0** | 空 |
| `data/screener_results/date=*` | **0** | 空 |
| `data/premarket_results/` | **MISSING** | 无预览文件 |

### 1.5 回测 API guard (核对 `backtest.py:29`)

`BACKTEST_MAX_SERVER_DAYS = 186` (`api/backtest.py:29`), 但 **`settings.backtest_range_guard` 默认 `False`** (`config.py:103`) — 186 天上限仅在显式开启时生效 (`_guard_server_backtest_range`, `backtest.py:57-63`, 超限 400)。`api/research.py:107-117` 的 `_validate_evaluation_guard` 对因子评估复用该 guard (因子评估是 per-symbol 滚动重算, 内存重)。

### 1.6 probe 语义 (核对 `auction_probe.py`)

`resolve_auction_probe()` (`auction_probe.py:139-173`) 是 **live-source 探测**: 枚举候选源 → 对 `PROBE_SYMBOL` 拉 `_last_trade_date()` (最新日K分区日或今天) 的竞价行 → 判 [09:15,09:25] 窗口内是否有行 → `AuctionProbeVerdict(status/source/probed_at/detail)` (`.to_dict()` 供响应)。**probe 判定的是"今天的数据源可用性", 对历史分区存在性无信息量。** REV-01 已锁定: 历史 as_of 用**分区存在性主闸门**。

### 1.7 端点挂载点 (核对 `api/`)

- `api/research.py` 已存在: `APIRouter(prefix="/api/research", tags=["research"])`, 是 typed 研究工作流 (factor DSL/hypotheses/experiments, 含 POST 写路径 + `_state_service` 503 语义), `main.py:856` 注册。
- `api/auction_history.py` 是**只读 POOL-03 模式范本**: 模块 docstring 声明零执行、GET-only、诚实空态 200 (`available:false`)、probe 透传、guest 掩码、专属守卫测试 `tests/test_auction_history.py`。
- `main.py:847-881` 逐 router 注册; `app.state.repo` (`:129`) / `app.state.strategy_engine` (`:563`) 可用。

---

## 2. 实现方案 (选项 A — 只读信号质量报告)

### 2.1 `attach_auction_columns_range` — 向量化区间注入原语

放 `backend/app/services/auction_columns.py` (与单日版同模块, 共享 `_AUCTION_REAL_COLS` / keep-list / 注释语义; 该模块 docstring 已声明"绝不写湖")。

```python
def attach_auction_columns_range(
    df: pl.DataFrame,          # enriched 面板 (symbol/date/open/close/volume/open_gap/change_pct/vol_ratio_5d/amount…),
                               # 须来自 get_enriched_range 快路径 (缓存 volume 与单日版同源);
                               # 需含 warmup 前导行 (见 2.1.4)
    start: date,
    end: date,
    repo: KlineRepository,
) -> tuple[pl.DataFrame, list[date]]:
    """区间竞价列注入 (只读研究原语, BT-02)。

    历史闸门 = 分区存在性 (REV-01: 历史 as_of 分区存在性主闸门; probe 是 live-source
    探测, 与历史分区无关 → 不参与闸门, 仅由端点透传报告)。
    返回 (注入后的面板, enabled_dates)。"""
```

**行为序列:**

1. **分区发现** (镜像 `auction_history.py:61-66` `_dir_date`): 扫 `repo.store.data_dir / "kline_auction" / "date=*" / "part.parquet"`, 解析 `date=YYYY-MM-DD` (解析失败跳过), 过滤 `[start, end]` ∩ 解析日; 目录无/无匹配 → 返回 `(df, [])`。
2. **逐分区读取 + symbol 去重**: 每个非空分区 `pl.read_parquet`, `unique(subset=["symbol"], keep="last")` (镜像 `auction_columns.py:146`); 空分区跳过 (镜像 `:119-121`); 级联为 `auction` 帧 (列: symbol/date/auction_volume/auction_amount[/auction_unmatched_amount 输入可得时]/…)。
3. **`auction_volume_ratio` 向量化 (PIT-safe, 与单日版逐点等价, 见 2.1.3)**: 在 `df` 上 `sort(["symbol","date"])` 后:
   ```python
   df.with_columns(
       (pl.col("auction_volume")
        / pl.col("volume").shift(1).rolling_mean(5, min_periods=1).over("symbol"))
       .alias("auction_volume_ratio")
   )
   ```
   在 `auction` 帧上计算后再左联 (保持 df 行基数不变), 或直接在 df 上 join 后计算; **推荐在 auction 帧上计算** (注入列与单日版同源, 且 panel 行数不受影响)。
4. **keep-list 裁剪** (镜像 `:128-137`): 仅注入存在的列。
5. **左联**: `df.join(auction, on=["symbol", "date"], how="left")` — 分区有行但某 symbol 缺席 → 该行列 null (诚实按标的缺席, 镜像 `:149-151`); **注入后裁剪** `df.filter(pl.col("date") >= start)` 到验证集 (warmup 行仅用于分母, 不出现在结果)。
6. **enabled-dates**: 排序去重的注入日列表 (与第 5 步的 join 键一致)。

**2.1.1 签名说明**: 不接收 probe verdict — 历史闸门只依赖分区存在性; probe 由端点解析并透传报告 (见 §4 `probe` 字段)。这与单日版 `attach_auction_columns` 的**双闸门**差异是**有意为之** (REV-01 锁定 + 1.6 依据): live 路径 probe 非 available → 列缺席 → fail-closed 回退派生; 历史报告反之, 分区存在即真值。二者不矛盾 (live 今日降级 ≠ 历史分区不是真数据)。

**2.1.2 enabled-dates 语义 (BT-01/BT-02 核心):**
- `enabled_dates = {d ∈ [start,end] : kline_auction/date=d 分区存在且非空 ∧ d ∈ enriched 交易日}` (排序)。
- 无分区日 → **不产生行、不进 enabled-dates、列缺席** — 绝不做 null-as-present (镜像 `auction_columns.py:95-96` 平台铁律)。
- `data_gate` = enabled_dates 非空 ? `"available"` : `"empty"` (enriched 窗口空 → `"empty"` + `empty_reason="enriched_unavailable"`)。

**2.1.3 向量化分母等价性证明 (关键实现细节):**
- 单日版分母 = `get_enriched_history(T, 6)` 按**交易日**取前 6 个交易日 → `filter(date < T)` → `tail(5).mean()` = **T 前最近 5 个交易日 volume 均值** (不足 5 日取可用行均值)。
- 向量化 `volume.shift(1).rolling_mean(5, min_periods=1).over("symbol")` (面板已按 symbol,date 排序): `shift(1)` 把 volume_{T-1} 移到行 T; `rolling_mean(5, min_periods=1)` 在行 T 取窗口 T-5..T-1 均值 = **T 前最近 5 个交易日均值**; `min_periods=1` 镜像 `tail(5).mean()` 的短历史行为 (≤4 个前导交易日时均值不置 null)。**二者逐值一致**。
- **前提:** 面板 volume 与 `_enriched_history_cache` 同源 (服务层必须走 `get_enriched_range` 快路径装载) — 见 2.2.1。
- 单日版无历史/prior 空 → 列缺席; 向量化等价行为: `min_periods=1` 且前导为空 (shift(1) 组内首行为 null) → rolling 均值 null → ratio null → 该行真实分支 filter 自然不命中 (诚实)。

**2.1.4 warmup 契约:** 面板须含 `start` 前最多 5 个交易日的行 (供首个 enabled 日分母)。服务层装载 `get_enriched_range(warmup_start, end)` (见 2.2.1); 原语内部注入后裁剪 `date >= start`。若调用方未提供 warmup 行 → 前导日 ratio 为 null → 真实分支该日无命中, 属诚实降级 (文档标注, 不报错)。

### 2.2 `AuctionValidationService` — 报告装配服务

新文件 `backend/app/services/auction_validation.py` (镜像 `pool_hub.py` 服务层约定; 只读, 零写零执行)。

```python
class AuctionValidationService:
    def __init__(self, repo: KlineRepository, engine: StrategyEngine) -> None: ...
    def build_report(
        self,
        *,
        start: date | None, end: date | None,
        strategy_ids: list[str] | None, symbols: list[str] | None,
    ) -> dict:
        """装配 GET /api/research/auction/validation 响应 (BT-03)。"""
```

**2.2.1 数据装载:**
1. **窗口解析**: `end` 缺省 = enriched 最新交易日 (缓存 max); `start` 缺省 = `end − 120 自然日` (与 `auction_history.py` days=120 默认对齐)。`start > end` → 由 API 层 400。
2. **窗口回夹 (诚实-listed)**: 从 `repo._enriched_history_cache` 取 `date.min()/date.max()` (fast path 缓存; 空 → 回退扫 `kline_daily_enriched/date=*` 目录); `requested` 窗口超出覆盖 → 回夹到 `[cache_min, cache_max]`, 响应 `window.requested_*` / `window.effective_*` 双字段回显 (见 §4)。
3. **面板装载**: `warmup_start = start − 14 自然日` (≥5 交易日余量); `panel = repo.get_enriched_range(warmup_start, end, symbols=symbols)`; `None`/空 → 诚实 `{data_gate:"empty", empty_reason:"enriched_unavailable", strategies:[]}` (绝不 500/404, 镜像 `load_panel` 快路径的 None 语义; 慢路径 `scan_enriched_parquet`+`compute_all` **不复用** — 研究报告不复制回测 fallback, 缓存未覆盖即诚实空, 见 §5 风险 3)。
4. **注入**: `panel, enabled_dates = attach_auction_columns_range(panel, start, end, repo)`; `verification_panel = panel.filter(date >= start)`。
5. **enriched_dates** = `verification_panel["date"].unique().sort()`; `auction_enabled_dates` = enabled_dates ∩ enriched_dates (原语已保证, 复核用)。

**2.2.2 策略枚举与分支选择 (BT-05 互斥):**

| 策略类别 | 判定 | 评估面板 | branch |
|---|---|---|---|
| 4 个 `requires_auction_data=True` | meta 标志 | enabled 子面板 (`verification_panel.filter(date.is_in(enabled_dates))`), 空 → n_dates=0 | `"real"` (湖空也不落 derived) |
| `auction_alpha` | enabled 非空 ? 真列 : 派生 | enabled 子面板 (真列) / verification_panel 全窗口 (派生) | `"real"` 或 `"derived"` (一次报告只取一个) |
| 4 个 EOD 代理 (golden_230/bullish/preopen_quant/early_star) | — | verification_panel 全窗口 | `"eod"` |

- 枚举源: `engine.list_strategies()` (id/name/meta) + `engine._strategies` (StrategyDef, 含 `filter_fn`/`meta`); 与 `screener.run_all_with_hits` 的枚举方式一致 (`screener.py:745-754`)。**硬编码 9 个 id 集合做"属竞价族"筛选** (`_AUCTION_FAMILY_IDS = {"auction_fast_grab","auction_allround","t1_flash","auction_intraday_confirm","auction_alpha","golden_230","auction_bullish","auction_preopen_quant","auction_early_star"}`), 从 engine 取定义 (不 import builtin 模块), 引擎缺失某 id → 忽略并记录 `skipped_ids`, 不 500。
- **参数**: 一律用 `META["params"]` 默认值 (镜像 `engine.py:229` 归一化后的 `{p["id"]: p["default"]}`), 确定性、跨日可比; 不做用户参数覆盖。

**2.2.3 候选掩码 (镜像 `StrategyBacktestService._build_candidate_filter_mask`, `strategy.py:522-570`):**
- 9 个竞价族策略全部只走 `filter_fn` (无 filter_history_fn) → 本地实现:
  ```python
  def _build_candidate_mask(panel, s: StrategyDef, params) -> pl.Series:
      if s.filter_fn is None:
          return pl.Series("_cand", [True] * len(panel), dtype=pl.Boolean)
      try:
          expr = s.filter_fn(panel, params)
          return panel.select(expr.alias("_cand"))["_cand"].fill_null(False).cast(pl.Boolean)
      except Exception:
          return pl.Series("_cand", [False] * len(panel), dtype=pl.Boolean)   # fail-closed, 镜像 strategy.py:551-552
  ```
- **不 import `app.backtest.strategy`**: 保持新模块 AST 守卫面最小 (BT-06); 语义镜像并在 docstring 标注来源锚点 `backtest/strategy.py:522-570`。
- hits = `verification_panel.filter(mask)` 的 (symbol, date) 行; `n_hits` = 行数; `per_date` = 按 date group_by 计数 (+ `n_screened` = 该日面板行数)。

**2.2.4 前瞻统计 (BT-04 口径锁死):**
- 信号日 = T (竞价定开盘价); 入场 = T 开盘价 (open_T, 竞价已知)。
- **结果日 = 全市场交易日历的下一交易日** (enriched 全局去重日期排序的 next-date 映射), **不是** symbol 行内 `shift(-1)` — 停牌标的的下一行可能是 T+2, 会错配; 严格口径 = (symbol, next_market_date(T)) 行缺席即缺失。
- 实现: `next_map = {d: next_d}` 从全局交易日历构建; hits join `next_map` 得 outcome_date; 再 join verification_panel (on symbol+outcome_date) 取 `open_{T+1}`/`close_{T+1}`。
- 三指标 (每 hit, 行缺 → null → 剔除):
  - `next_day_open_ret = open_{T+1}/open_T − 1`
  - `next_day_close_ret = close_{T+1}/open_T − 1`
  - `open_gap_outcome = open_{T+1}/close_T − 1` (隔夜跳空; 另需 close_T 非空且 >0, 否则该指标单点剔除但其余指标保留 — 各指标独立 `n`)
- `n_missing_outcomes` = hits 中 `next_open` 为 null 的行数 (结果日缺行: 停牌/退市/数据缺失); **绝不 0 填/前向填充**; 均值/胜率只含有效行。
- 每指标聚合: `mean`/`median`/`win_rate` (有效行 > 0 的比例)/`n` (有效行数)。

### 2.3 `GET /api/research/auction/validation` 端点

新文件 `backend/app/api/research_auction.py` (镜像 `auction_history.py` 只读范本):

```python
"""竞价策略历史验证只读报告 (BT-03, POOL-03 零执行)。

GET-only; 不写 kline_auction/screener_results/premarket_results/strategy_cache;
不 import 执行族 (broker/order/execution/trade/portfolio/position/account/transaction);
不触发同步/回填/run_all。任何违反都会触发 tests/test_auction_validation.py 的
POOL-03 AST 守卫 (镜像 test_pool_hub.py E1/E3/E4/E5 与 test_auction_history.py)。
"""
router = APIRouter(prefix="/api/research", tags=["research"])

@router.get("/auction/validation")
def auction_validation(
    request: Request,
    strategy_ids: str | None = Query(None),   # 逗号分隔; 缺省 = 9 个竞价族
    start: date | None = Query(None),
    end: date | None = Query(None),
    symbols: str | None = Query(None),        # 逗号分隔; 缺省 = 全市场
) -> dict: ...
```

- **为什么不放进 `api/research.py`**: 该模块是 typed 研究工作流 (POST 写路径 + `_state_service`), 混入会扩大其守卫面并与其"研究工作流"定位冲突; 独立模块获得独立 POOL-03 AST 守卫目标 (与 `auction_history.py`/`test_auction_history.py` 同构)。
- 挂载: `main.py` 在 `research.router` 之后 `app.include_router(research_auction.router)`。
- 参数校验: `start > end` → 400 (`{"code":"RESEARCH_VALIDATION", ...}` 镜像 research.py `_bad_request`); 非日期/非法格式 → FastAPI 422 (镜像 research.py Query date 行为); `strategy_ids` 逗号分隔解析 → 空串 → `[]` → 响应 `strategies: []` (镜像 `run_all_with_hits` 空列表 `{}` 语义, `screener.py:756`); 未知 id → 忽略 + `skipped_ids` 字段记录, 不 500。
- `probe = resolve_auction_probe()` 每次请求解析一次, 仅透传 (不 gate)。

**2.3.1 与 186 天 guard 的区间冲突 — 决策: 不套用 `BACKTEST_MAX_SERVER_DAYS`。**

| 方案 | 内容 | 结论 |
|---|---|---|
| (a) 复用 `_guard_server_backtest_range` | 超 186 天 → 400 (镜像 `research.py:107-117`) | ✗ 否决: guard 保护的是组合回测/因子评估的内存 (1.8GB 服务器, `backtest.py:30-32`); 本报告是单面板扫描 + 向量化统计 (≈ `load_panel` 快路径, 该路径本身无 guard), 248 天全量内存已由 enriched 缓存承载 |
| (b) **诚实-listed (推荐)** | 窗口回夹到 enriched 覆盖 + `window.requested_*/effective_*` 回显 + `coverage` 明示; 默认 120 天 | ✓ 采纳: 与 BT-01 覆盖报告同一诚实语义; 不丢 248 天数据; guard 默认 `False` (`config.py:103`) 佐证其非平台硬约束 |

补充: `settings.backtest_range_guard=True` 的部署下, 本端点仍**不**套 guard — 在端点 docstring 与 README 注明"研究报告区间不受回测 guard 限制, 覆盖由 enriched 缓存边界决定"。

---

## 3. 模块职责

| 模块 | 新增/复用 | 职责 | 守卫 |
|---|---|---|---|
| `app/services/auction_columns.py` | **新增函数** `attach_auction_columns_range` | 分区发现、逐日注入、symbol 去重、PIT-safe ratio 向量化、enabled-dates 产出 | 模块既有只读契约 (docstring "绝不写湖"); 新函数不引入新 import |
| `app/services/auction_validation.py` | **新增** | 窗口解析/回夹、面板装载(warmup)、9 策略枚举与 branch 选择、候选掩码、前瞻统计、报告装配 | POOL-03 AST 守卫目标 |
| `app/api/research_auction.py` | **新增** | GET 端点、参数校验、probe 透传、响应序列化 | POOL-03 AST 守卫目标 (GET-only + 零写 + 禁执行族 import) |
| `app/main.py` | 编辑 (1 行) | 注册 `research_auction.router` | — |
| `tests/test_auction_validation.py` | **新增** | POOL-03 守卫 (E-guard 形状) + 端点行为 | — |
| `tests/test_attach_auction_columns_range.py` | **新增** | 原语单测 + 与单日版等价性 | — |
| `tests/test_auction_validation_report.py` | **新增** | 报告集成测试 (fixture 湖) | — |

**新增 import 面 (全部白名单):** `app.services.auction_probe` (AuctionProbeStatus/verdict 类型), `app.tickflow.repository` (KlineRepository), `app.strategy.engine` (StrategyEngine/StrategyDef), `app.parquet` 不需要 (注入用目录 glob, 镜像 auction_history `_dir_date`), polars, fastapi, stdlib。**禁 import**: `auction_sync` / `pool_snapshot` / `pool_backfill` / `premarket_snapshot` / 任何执行族 / `screener` (其 `run_all*` 是计算触发面)。

---

## 4. 报告 Schema

```json
{
  "data_gate": "empty | available",
  "empty_reason": null | "no_auction_partitions" | "enriched_unavailable" | "no_dates_in_window",
  "generated_at": "2026-08-06T04:00:00Z",
  "window": {
    "requested_start": "2026-04-08", "requested_end": "2026-08-05",
    "effective_start": "2025-07-29", "effective_end": "2026-08-05"
  },
  "probe": { "status": "not_configured | available | error", "source": null, "probed_at": null, "detail": "…" },
  "coverage": {
    "auction_enabled_dates": ["2026-08-05", "…"],
    "auction_enabled_count": 0,
    "enriched_dates": ["2025-07-29", "…"],
    "enriched_count": 248,
    "coverage_ratio": 0.0
  },
  "skipped_ids": [],
  "strategies": [
    {
      "id": "auction_fast_grab",
      "name": "极速抢筹",
      "branch": "real | derived | eod",
      "requires_auction_data": true,
      "minute_confirm": "not_applied | applied",
      "params": { "min_auction_vol_ratio": 1.5, "…": "…" },
      "n_dates": 0,
      "n_hits": 0,
      "coverage": 0.0,
      "n_missing_outcomes": 0,
      "forward_stats": {
        "next_day_open_ret":  { "mean": null, "median": null, "win_rate": null, "n": 0 },
        "next_day_close_ret": { "mean": null, "median": null, "win_rate": null, "n": 0 },
        "open_gap_outcome":   { "mean": null, "median": null, "win_rate": null, "n": 0 }
      },
      "per_date": [ { "date": "2026-08-05", "n_screened": 5120, "n_hits": 3 } ]
    }
  ]
}
```

**字段语义:**
- `data_gate`/`empty_reason`: §2.1.2; 湖空 → `"empty"` + `no_auction_partitions`; enriched 窗口空 → `"empty"` + `enriched_unavailable`。
- `probe`: `resolve_auction_probe().to_dict()` 透传 (live-source 状态, 不参与闸门 — §1.6)。
- `coverage.coverage_ratio` = `auction_enabled_count / enriched_count` (enriched_count=0 → 0.0)。
- `strategies[].branch`: 互斥 (BT-05), 一次报告每策略只含一个 branch 的统计。
- `strategies[].coverage` = 有 ≥1 hit 的评估日数 / `n_dates`。
- `n_missing_outcomes`: §2.2.4; 湖空 real 策略 = 0 (无 hit)。
- `forward_stats` 每指标独立 `n`; 无有效行 → mean/median/win_rate 全 null (诚实, 不 0 填)。
- `minute_confirm`: `auction_intraday_confirm` 恒 `"not_applied"` (kline_minute 0 分区 + 回测 seam 不调 minute_confirm_fn); 其余策略 `"applied"` 仅当存在分钟确认层, 本报告 9 族里仅 intraday_confirm 有 → 其余 `"not_applied"` 或省略 (以 `"not_applied"` 显式标注更诚实, 推荐显式)。

---

## 5. 验收口径 (per BT-01..06, 锁定与调和)

### BT-01 数据覆盖报告 (honest gate)
- 响应恒含 `data_gate`/`coverage`/`probe`; 湖空 → 200 + `data_gate=="empty"` (绝不 404/500)。
- **调和 BT-01 vs BT-05 (BACKTEST-AUCTION 草案中两处验收文字冲突)**: BT-01 草案"`strategies==[]`"与 BT-05"真列策略 n_dates==0"以本上下文锁定为准 — **`strategies` 恒含全部 9 项**: 湖空时 4 个 real 策略 `n_dates==0, n_hits==0, branch=="real"` (不落 derived), 5 个 derived/eod 策略在 enriched 窗口给出真实统计 (branch 显式标注); `strategies==[]` 仅当 enriched 窗口本身为空 (`enriched_unavailable`/`no_dates_in_window`)。
- 验收测试: 空湖 fixture → 200, `data_gate=="empty"`, `empty_reason=="no_auction_partitions"`, 4 个 real 策略 n_dates==0, derived/eod 策略有统计; probe 透传。

### BT-02 区间竞价列注入原语
- 签名 `attach_auction_columns_range(df, start, end, repo) -> (df, list[date])` (§2.1)。
- 验收: 分区缺日 → 不在 enabled-dates; 空分区/非法目录名跳过; 每分区 symbol 去重单行; 无分区日无行 (禁 null-as-present); `auction_volume_ratio` 与单日版逐值一致 (属性测试, 见 §7); probe 不 gate (历史分区存在性主闸门) — 与单日版双闸门差异有 docstring 说明。
- 空湖 → `(df, [])`; 面板空 → `(df, [])`。

### BT-03 信号质量报告端点
- 缺省 `strategy_ids` → 9 个竞价族; 空列表 → `strategies: []` (coverage/probe 仍返回); 未知 id → `skipped_ids` 记录, 不 500; `start>end` → 400; 窗口超出 enriched 覆盖 → 回夹 + `window.*` 回显。
- 候选掩码语义镜像 `backtest/strategy.py:522-570` (docstring 标注锚点); 参数恒用 META 默认。

### BT-04 前瞻口径锁死
- 信号日 T、入场 T open; 三公式 §2.2.4; **结果日 = 全局交易日历 next-date** (非 symbol shift(-1)); 结果日缺行 → `n_missing_outcomes>0` 且统计排除, 绝不 0 填/前向填充。
- 验收: 合成 fixture 手工断言三公式数值; 制造 T+1 缺行 → 断言 n_missing_outcomes 且 mean/win_rate 与排除后一致。

### BT-05 分支标注互斥
- `branch ∈ {real, derived, eod}`; real 策略湖空 n_dates==0 且 data_gate=="empty", 不落 derived; auction_alpha 按 enabled 非空取 real/derived 其一; 4 个 EOD 代理恒 eod。
- 验收: 断言 branch 与面板列存在性一致; 同一策略单次报告只有单 branch 统计。

### BT-06 零执行 + 零新增依赖守卫
- 新模块不写 5 个湖/缓存 (`kline_auction`/`screener_results`/`premarket_results`/`strategy_cache`/frozen panel), 不 import 执行族, 不 import `auction_sync`/`pool_snapshot`/`pool_backfill`/`premarket_snapshot`/`screener` (run_all 触发面), 不新增运行时依赖 (纯 polars + 现有服务)。
- 验收: `tests/test_auction_validation.py` AST 守卫 (镜像 `test_pool_hub.py` E1/E3/E4/E5 + `test_auction_history.py` 风格): 禁 import token (`broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托` 作用于 `_imported_module_names`), GET-only (`@router.get` only), 禁写模式 (`open(...,"w"/"wb"/"a")`/`write_parquet`/`os.replace`/`unlink`/`mkdir`), 禁 `run_all|run_preset|write_cache|persist_point_snapshot` token, 禁 `strategy_cache` 引用。

### BT-07 (显式延后 v2.3+)
- 全量竞价回测 (frozen panel 竞价列 provenance + minute_confirm_fn 接入 + `_load_panel_inner` auction 配置) **本里程碑不实现**; RESEARCH 仅记录候选路径 (BACKTEST-AUCTION §方案 B)。

---

## 6. 风险

| # | 级别 | 风险 | 缓解 |
|---|---|---|---|
| 1 | **HIGH** | **湖空 = 真列验证不可用 (当前现实)**。kline_auction 0 分区、无历史回填代码 (`auction_sync.py:97-152` 仅按当日调用)。"今天就验证极速抢筹"是数据缺口而非代码缺口 | 4 个 real 策略诚实 `data_gate:"empty"` + n_dates==0; 派生/EOD 分支给历史验证; 需产品校准预期 (数据源历史竞价可得性为 [INFERENCE], 超出代码范围) |
| 2 | MEDIUM | **derived/eod ≠ 真列** — auction_alpha 派生分支、4 个 EOD 代理验证的是 EOD 代理因子, 防止被当作真列结论 | branch 显式互斥标注 (BT-05) + 报告顶部/字段级说明 |
| 3 | MEDIUM | **enriched 缓存未覆盖时报告诚实空** — 本设计不复用 `_load_panel_inner` 慢路径 fallback (不 import backtest seam) | `empty_reason="enriched_unavailable"`; 缓存由启动 `_refresh_enriched` 构建, 生产常态覆盖 248 天 |
| 4 | MEDIUM | **186 天 guard 区间冲突** — 若沿用 `research.py` 的 guard 会截断 248 天覆盖 | 决策: 不套 guard, 窗口回夹 + 回显 (§2.3.1); guard 默认关闭佐证 |
| 5 | MEDIUM | **盘中确认策略验证面弱化** — 只验证日线初筛层 (open_gap≥2%), minute_confirm_fn 不在回测 seam 调用且 kline_minute 0 分区 | 显式 `minute_confirm:"not_applied"` (BT-03 字段) |
| 6 | LOW | **结果日缺失口径** — 停牌/退市 T+1 缺失若静默剔除会虚高胜率 | `n_missing_outcomes` + 全局交易日历 next-date join (BT-04) |
| 7 | LOW | **auction_alpha 真列分支硬编码 1M 金额阈值** (未用 `min_auction_amount` 参数) — 报告会"如实复现"该现状 | 报告用 META 默认参数镜像现状; 修复列为范围外观察项 (记录到 RESEARCH 即可) |
| 8 | LOW | **向量化分母边界** — warmup 不足 5 日前导交易日 → 前导日 ratio null → 真实分支前导日无命中 | 服务层 warmup 契约 (§2.1.4) + min_periods=1 镜像单日版短历史行为 |
| 9 | LOW | 大请求 (1000+ symbols × 248 天 × 多策略) 报告延迟 | 单面板装载 + 向量化 mask/join; `symbols` 参数可裁剪; 不套 guard 但窗口回夹 |

---

## 7. 新增测试列表

### `backend/tests/test_attach_auction_columns_range.py` (原语, 镜像 `test_auction_columns.py` 风格)
1. **等价性属性测试 (核心)**: 合成 enriched 面板 + 连续交易日分区 fixture, 对每个 enabled 日断言 `attach_auction_columns_range` 的 `auction_volume_ratio` 与单日 `_attach_auction_volume_ratio`/`attach_auction_columns` 结果**逐值一致** (覆盖不足 5 日前导日的短历史行)。
2. 分区缺日 → 不在 enabled-dates; 空分区/非法目录名 (如 `date=bad`) 跳过不崩。
3. 多窗口行分区 → 每 symbol 单行 (防 fan-out)。
4. 左联: 分区有行但某 symbol 缺席 → 该 symbol 列 null (诚实按标的缺席)。
5. warmup: 面板含 `start` 前 5 交易日行时, 首个 enabled 日 ratio 正确; 无 warmup → 前导日 ratio null (不崩)。
6. 空湖/面板空 → `(df, [])`; `auction_unmatched_amount` 输入列可得时注入、缺席时不注入。

### `backend/tests/test_auction_validation_report.py` (服务+端点集成, fixture 湖)
1. 空湖 → 200 `data_gate=="empty"`, `empty_reason=="no_auction_partitions"`, 4 个 real 策略 `n_dates==0 branch=="real"`, 5 个 derived/eod 有统计, `probe` 透传 (BT-01/BT-05)。
2. 合成 auction 分区 + enriched fixture → 每策略 `n_hits`/`per_date` 与手工构造 mask 一致 (BT-03)。
3. **BT-04 公式断言**: 固定 2 日 fixture, 手工断言 `next_day_open_ret`/`next_day_close_ret`/`open_gap_outcome` 数值; 制造 T+1 缺行 (停牌 symbol) → `n_missing_outcomes>0` 且统计排除、无 0 填。
4. **BT-05 branch 互斥**: auction_alpha 有分区日 → real; 无分区 → derived; 同一响应单 branch。
5. `strategy_ids` 空 → `strategies: []`; 未知 id → `skipped_ids` 且 200; `start>end` → 400; 窗口超覆盖 → `window.effective_*` 回夹。
6. `minute_confirm=="not_applied"` 对 intraday_confirm。

### `backend/tests/test_auction_validation.py` (POOL-03 AST 守卫, 镜像 `test_pool_hub.py` E1/E3/E4/E5)
1. `test_validation_no_execution_imports` — `_EXECUTION_TOKEN` 作用于 `_imported_module_names(api/research_auction.py + services/auction_validation.py)`。
2. `test_validation_api_is_get_only` — `@router.get` only。
3. `test_validation_no_write_path` — `_WRITE_PATTERNS` 全集 + `auction_sync`/`pool_snapshot`/`pool_backfill`/`premarket_snapshot`/`screener` import 禁 + `run_all|run_preset|write_cache|persist_point_snapshot` token 禁。
4. `test_validation_no_strategy_cache_reference` — `strategy_cache`/`write_cache` 缺席。
5. `test_validation_modules_exist` — 守卫目标文件存在 (防守卫悬空)。

### 既有测试必须保持绿色 (回归锁)
- `backend/tests/test_pool_hub.py` (E1-E6) — pool 特性零改动; 新守卫独立文件。
- `backend/tests/test_auction_history.py` — `auction_history.py` 零改动。
- `backend/tests/test_auction_columns.py` — 单日 `attach_auction_columns` 零改动 (新函数纯增量)。
- `backend/tests/test_auction_probe.py` / `test_auction_sync.py` — probe/sync 零改动。
- `backend/tests/test_auction_strategies.py` / `test_auction_strategy_family*.py` — 策略源文件零改动。
- `backend/tests/research/test_research_api.py` — `api/research.py` 零改动。
- 回测套件 (`backend/tests/` 内 backtest 相关) — `backtest/` seam 零改动。

---

## 8. 关键锚点 (全部本次实测)

| 用途 | 锚点 | 实测 |
|---|---|---|
| 竞价列注入双闸门 | `backend/app/services/auction_columns.py:89-151` `attach_auction_columns` | ✅ 逐行核对 |
| PIT-safe ratio 单日实现 | `auction_columns.py:54-87` `_attach_auction_volume_ratio` | ✅ |
| enriched 历史按交易日切片 | `backend/app/tickflow/repository.py:937-958` `get_enriched_history` | ✅ (向量化等价性依据) |
| 区间面板快路径 | `repository.py:966-998` `get_enriched_range` | ✅ |
| requires_auction_data 短路 | `backend/app/strategy/engine.py:345-348` | ✅ |
| 策略枚举 | `engine.py:282-285` `get`; `screener.py:745-754` (list_strategies 用法) | ✅ |
| 9 策略列依赖 | `backend/app/strategy/builtin/{auction_fast_grab,auction_allround,t1_flash,auction_intraday_confirm,auction_alpha,golden_230,auction_bullish,auction_preopen_quant,auction_early_star}.py` | ✅ 全读 |
| 候选掩码语义来源 | `backend/app/backtest/strategy.py:522-570` `_build_candidate_filter_mask` | ✅ |
| 回测装载 seam (无竞价列) | `backend/app/backtest/engine.py:191-200` `load_panel`; `:202-276` `_load_panel_inner` | ✅ |
| enriched schema (15 列无 auction) | `backend/app/parquet.py:48-58` `ENRICHED_STORAGE_SCHEMA` | ✅ |
| 按日注入调用点 | `backend/app/services/screener.py:250-297` `_load_enriched_for_date`; `:306-314` `_attach_auction` | ✅ |
| 只读端点范本 | `backend/app/api/auction_history.py` (GET-only + 诚实空态 + probe 透传 + `_dir_date`) | ✅ |
| 端点挂载点 | `backend/app/api/research.py` (prefix `/api/research`); `main.py:856` + `:847-881` 注册区; `app.state.repo` `:129`; `app.state.strategy_engine` `:563` | ✅ |
| 回测 guard | `backend/app/api/backtest.py:29` `BACKTEST_MAX_SERVER_DAYS=186`; `:57-63`; `config.py:103` (默认 False) | ✅ |
| probe live 语义 | `backend/app/services/auction_probe.py:139-173` `resolve_auction_probe` (今日探测) | ✅ |
| POOL-03 守卫形状 | `backend/tests/test_pool_hub.py:857-963` (`_EXECUTION_TOKEN`/`_imported_module_names`/E1/E3/E4/E5) | ✅ |
| 湖覆盖实测 | `data/kline_daily_enriched/` 248, `kline_auction/` 0, `kline_minute/` 0, `screener_results/` 0, `premarket_results/` MISSING | ✅ 2026-08-06 |

---

## 9. 遗留开放问题 (供 planner)

1. **历史竞价数据可得性 (BT 风险 1, [INFERENCE])**: 上游是否提供历史竞价? 若否, 真列验证在湖有数据前只能诚实空 — 产品预期校准, 超出代码范围。
2. **`minute_confirm` 字段形态**: 全 9 策略显式 `"not_applied"` vs 仅 intraday_confirm 携带 (推荐显式, 诚实优先)。
3. **`per_date` 上限**: 248 天 × 9 策略 per_date 数组体积 (~2.2K 行) — 建议原样返回 (只读报告, 体积可控), 如需分页属 P2。
4. **与 Phase 24 回填的衔接 (SUMMARY 开放决策 9)**: `screener_results` 0 快照 → 选项 C 快照重放本期不做 (BACKTEST-AUCTION 已定), 不阻塞。
5. **前端消费**: 本端点无前端依赖 (纯研究报告); 若后续要 UI, 属 v2.2 之后 (不触碰 `frontend/src/pages/Watchlist.tsx`, off-limits 铁律保持)。
