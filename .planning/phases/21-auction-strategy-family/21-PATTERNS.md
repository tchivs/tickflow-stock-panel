# Phase 21: 竞价策略族 (Auction Strategy Family) - Pattern Map

**Mapped:** 2026-08-05
**Files analyzed:** 14 (6 修改 / 8 新增)
**Analogs found:** 14 / 14（exact 9 / role-match 4 / partial 1；另有 5 处无既有 analog 的引擎级子功能缺口，见 No Analog Found）

> 本文件把 Phase 21 的每个新建/修改文件映射到仓库内最接近的既有实现，并给出可直接复制/镜像的具体代码段（带文件路径与行号）。Phase 21 的核心是**引擎 seam**（`requires_auction_data` 空安全 + `time_window`/`evaluation_time` 元数据 + `minute_loader`/`confirm_minute`）+ 受管列 `auction_volume_ratio` + 六策略。策略文件的 META/filter/scoring 形态有 Phase 17 三策略（`auction_bullish`/`auction_preopen_quant`/`auction_early_star`）可逐行复制；引擎改动镜像 `run()` 既有空帧早退 + `filter_history_fn` seam + `_apply_scoring` 缺列跳过；`evaluation_time` 截断与 `time_factor` 折算复用 `market_time.py`/`pipeline.py` 既有折算规约。**真正无类比的是 5 个引擎级子功能**（分钟 loader seam、单点截断、`requires_auction_data` 短路、受管列派生注入、文档契约字段），planner 需以 RESEARCH.md RQ3/RQ5 兜底。

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/strategy/engine.py` (modified) | engine | request-response | 模块内 `run()` 空帧早退 (302-307) + `filter_history_fn` seam (287-301) + `_load_file` meta.setdefault (180-189) + `_apply_scoring` 缺列跳过 (485-512, 496-497) | exact (in-file) |
| `backend/app/services/auction_columns.py` (modified) | service | transform | 模块内 `attach_auction_columns` probe×分区双闸门 (53-102) | exact (in-file) |
| `backend/app/indicators/pipeline.py` (modified) | config/registry | transform | 模块内 `ENRICHED_COLUMNS` (75-165) + `ENRICHED_COLUMNS_BY_CATEGORY["auction"]` (183) + `time_factor` 折算 (1404-1416) | exact (in-file) |
| `backend/app/strategy/builtin/auction_fast_grab.py` (new) | strategy | request-response | `auction_bullish.py` META+filter 全形 (4-19, 28-35) + 缺列守卫模式 (research Code Ex 2) | exact |
| `backend/app/strategy/builtin/auction_alpha.py` (new) | strategy | request-response | `auction_preopen_quant.py` 双阈值 filter (28-35) + `auction_early_star.py` 列存在性分支 (39-40) | exact |
| `backend/app/strategy/builtin/golden_230.py` (new) | strategy | request-response | `strong_open.py` EOD 列 (change_pct + close>open, 34-44) + `volume_price_surge.py` 收阳 (40) | role-match |
| `backend/tests/test_auction_strategy_family.py` (new) | test | transform | `test_auction_strategies.py` `_governed_fixture`/`_engine`/`_run_auction` (26-64) + 权重和=1.0 (105-108) + `test_auction_columns.py` `_patch_probe` 状态矩阵 (53-55, 132-158) | exact |
| `backend/app/strategy/builtin/auction_allround.py` (new, P2) | strategy | request-response | `auction_fast_grab` 的 fail-closed filter 形 + `auction_bullish` META 形（同期 21-01 产物为模板） | role-match |
| `backend/app/strategy/builtin/t1_flash.py` (new, P2) | strategy | request-response | `near_limit_up.py` EXIT_SIGNALS/MAX_HOLD_DAYS + EOD filter (46-62) + `auction_bullish` META 形 | role-match |
| `backend/app/strategy/builtin/auction_intraday_confirm.py` (new, P2) | strategy | request-response / minute | 无内置分钟消费先例 → 引擎 `filter_history_fn` seam (engine.py:287-301) + `strategy-guide.md` filter_history 模板 (103-138) | partial |
| `backend/tests/test_auction_strategy_family_p2.py` (new, P2) | test | transform | `test_auction_strategy_family.py`（21-01 测试 helpers 直接扩展）+ `test_auction_probe.py` FakeAuctionProvider 手工 parquet fixture (25-57) | role-match |
| `docs/features.md` (modified, P2) | docs | — | 模块内 9-11 内置策略计数段（现写 21，对账到 27） | exact (in-file) |
| `docs/strategy.md` (modified, P2) | docs | — | 模块内 9-11 内置策略计数段（现写 18，已漂移，对账到 27） | exact (in-file) |
| `backend/app/strategy/prompts/strategy-guide.md` (modified, P2) | docs/contract | — | 模块内 15-87 文件结构模板 + 89-145 filter_history 契约（补 time_window/evaluation_time/confirm_minute 字段契约） | exact (in-file) |

## Pattern Assignments

### 1. `backend/app/strategy/engine.py` (modified, engine / request-response)

**Analog:** 模块内既有 4 个 seam 组合 — `run()` 空帧早退 (302-307)、`filter_history_fn` 分支 (287-301)、`_load_file` meta.setdefault (180-189)、`_apply_scoring` 缺列跳过 (485-512)。

**META 新字段读取 — 沿 meta.setdefault 归一化** (engine.py:180-189) — `_load_file` 为新增 META 字段补默认值:
```python
meta.setdefault("id", path.stem)
meta.setdefault("name", path.stem)
meta.setdefault("description", "")
meta.setdefault("tags", [])
meta.setdefault("params", [])
meta.setdefault("scoring", {})
meta.setdefault("order_by", "score")
meta.setdefault("descending", True)
meta.setdefault("limit", 100)
```
> Phase 21 追加: `meta.setdefault("time_window", "intraday")` / `meta.setdefault("evaluation_time", None)` / `meta.setdefault("requires_auction_data", False)`。`StrategyDef` (96-113) 沿 `filter_history_fn` (109-110) 的形态增 `minute_confirm_fn`/`evaluation_time` 字段。

**`requires_auction_data` 短路空池 — 镜像 run() 空帧早退** (engine.py:302-307) — 在数据加载后、基础过滤前 (315-317) 插入:
```python
elif precomputed is not None and not precomputed.is_empty():
    df = precomputed
else:
    df = self._loader(as_of)
    if df.is_empty():
        return StrategyResult(as_of=as_of, strategy_id=strategy_id)
```
```python
# 新增 requires_auction_data 分支 (research Code Ex 4):
if s.meta.get("requires_auction_data") and "auction_volume" not in df.columns:
    return StrategyResult(as_of=as_of, strategy_id=strategy_id)   # fail-closed 空池
```

**minute_loader/confirm_minute seam — 镜像 filter_history_fn 分支** (engine.py:287-301):
```python
if s.filter_history_fn:
    if precomputed_history is not None and not precomputed_history.is_empty():
        df = precomputed_history
    elif self._history_loader:
        df = self._history_loader(as_of, max(1, s.lookback_days))
    else:
        logger.warning("strategy %s requires history loader", strategy_id)
        return StrategyResult(as_of=as_of, strategy_id=strategy_id)
    if df.is_empty():
        return StrategyResult(as_of=as_of, strategy_id=strategy_id)
    df = s.filter_history_fn(df, params)
    if df.is_empty():
        return StrategyResult(as_of=as_of, strategy_id=strategy_id)
    if "date" in df.columns:
        df = df.filter(pl.col("date") == as_of)
```
> 新 seam 执行序（RESEARCH RQ3）: 日线初筛得 candidates → `self._minute_loader(candidates, as_of)` → **引擎单点** `df_minute.filter(pl.col("datetime") <= evaluation_time)` → `s.minute_confirm_fn(df_minute, params)` → 只保留确认的 candidates 进评分。截断点只在引擎（"确认时刻之后无输入"硬验收）。

**评分缺列静默跳过（策略双分支/缺席列依赖它）** (engine.py:496-497):
```python
for col, weight in weights.items():
    if col not in df.columns:
        continue   # 缺失列被静默跳过 — 派生分支/缺席列自动退化, 不报错
```

---

### 2. `backend/app/services/auction_columns.py` (modified, service / transform)

**Analog:** 模块内 `attach_auction_columns` (53-102) — probe×分区双闸门 + 左联注入。

**读路径注入骨架 (auction_columns.py:53-102) — `auction_volume_ratio` 派生插在 unique 之后、join 之前:**
```python
def attach_auction_columns(df: pl.DataFrame, trade_date: date, repo: KlineRepository) -> pl.DataFrame:
    if df is None or df.is_empty():
        return df
    # 第一闸门: probe 必须 available
    if resolve_auction_probe().status != AuctionProbeStatus.available:
        return df
    # 第二闸门: 目标日分区存在且有行
    part = repo.store.data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    if not part.exists():
        return df
    auction = pl.read_parquet(part)
    if auction.is_empty():
        return df
    # … 派生未匹配金额 (86-88) + 真实列裁剪 (91-92) …
    # 防 fan-out: 每 symbol 只保留一行
    auction = auction.unique(subset=["symbol"], keep="last")
    return df.join(auction, on="symbol", how="left")
```
> **新增派生段**（21-RESEARCH RQ2 受管列, PIT-safe）: 分母取 `repo.get_enriched_history(trade_date, 6)`（repository.py:937-964）过滤 `date < trade_date` 后 tail 5 的 `volume` 均值 — 只用前日数据，绝不混入当日 EOD 量。派生列与真实竞价列同帧携带，`probe×分区双闸门`任一不过 → 列缺席（诚实缺列，不 0 填充）。

---

### 3. `backend/app/indicators/pipeline.py` (modified, config/registry / transform)

**Analog:** 模块内 `ENRICHED_COLUMNS` (75-165) + `ENRICHED_COLUMNS_BY_CATEGORY` (168-184) + `time_factor` 折算 (1404-1416)。

**注册表条目格式 (pipeline.py:158-160) — 新增 `auction_volume_ratio` 沿同形 dict[str,str] 中文描述:**
```python
# ── 竞价列 (probe 门控, 读路径左联注入; 不进存储窄表/计算闭包) ───
"auction_volume":          "竞价量 (集合竞价撮合成交量, 单位: 股; 仅 probe available 时存在)",
"auction_amount":          "竞价金额 (集合竞价撮合成交额, 单位: 元; 仅 probe available 时存在)",
"auction_unmatched_amount": "派生未匹配金额 (估算, 非真实成交; 委托量输入可得时存在)",
# 新增: "auction_volume_ratio": "竞价量比 (竞价量/前5日均量(不含当日), 仅 probe available 且分区有行时存在)",
```

**分类表条目格式 (pipeline.py:183) — 追加到 `auction` 类:**
```python
"auction":  ["auction_volume", "auction_amount", "auction_unmatched_amount"],
# 新增: "auction":  ["auction_volume", "auction_amount", "auction_unmatched_amount", "auction_volume_ratio"],
```
> **不进 `ENRICHED_STORAGE_COLS` (57-67) / 计算闭包**（20-RESEARCH 硬边界 4 沿续）— `auction_volume_ratio` 由读路径注入，不可从 OHLCV 重算。

**time_factor 折算（STRAT-09 盘中量比直接复用）** (pipeline.py:1408-1411 + market_time.py:14,31-47):
```python
if elapsed_minutes and elapsed_minutes > 0:
    time_factor = 240.0 / elapsed_minutes  # 盘中折算: 部分量 → 全天量级
else:
    time_factor = 1.0  # 盘后/无效时间: 不折算(此时 volume 已是全天量)
```
> `elapsed = trading_minutes_elapsed_from_dt(evaluation_time)`（market_time.py:31-47）; eval=09:45 → elapsed=15 → tf=16.0。

---

### 4. `backend/app/strategy/builtin/auction_fast_grab.py` (new, strategy / request-response)

**Analog:** `auction_bullish.py` (META 4-19 + filter 28-35) — Phase 17 内置策略全形。

**META 全形（复制 auction_bullish.py:4-19, 追加时间窗字段）:**
```python
META = {
    "id": "auction_bullish",
    "name": "竞价多头",
    "description": "开盘涨幅 (open/prev_close−1) 与日涨幅 (change_pct) 双动量同时达标",
    "tags": ["竞价", "高开", "动量"],
    "params": [
        {"id": "min_open_gap", "label": "最低开盘涨幅%", "type": "float",
         "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.5},
    ],
    "scoring": {"open_gap": 0.5, "change_pct": 0.5},
    "order_by": "score",
    "descending": True,
    "limit": 50,
}
ENTRY_SIGNALS = []
EXIT_SIGNALS = []
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 10
ALERTS = []
```
> Phase 21 追加 `"time_window": "pre_open"`, `"requires_auction_data": True`；`scoring` 只含 pre_open 可算列（禁 EOD 列）。

**filter 缺列 fail-closed 守卫（新模式, 沿 21-RESEARCH Code Ex 2; 镜像 auction_early_star 列存在性判断 39）:**
```python
def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    # 必需列缺席 → 整池为假 → 空池 (fail-closed, 绝不部分/0 填充)
    if "auction_volume_ratio" not in df.columns or "auction_amount" not in df.columns:
        return pl.lit(False)
    vol_r = params.get("min_auction_vol_ratio", 1.5)
    amt = params.get("min_auction_amount", 2_000_000)
    return (
        (pl.col("open_gap") >= 0.028) & (pl.col("open_gap") <= 0.035)
        & (pl.col("open_gap") <= 0.07)                      # >7% 风险带剔除
        & (pl.col("auction_volume_ratio") >= vol_r)
        & (pl.col("auction_amount") >= amt)
    )
```

---

### 5. `backend/app/strategy/builtin/auction_alpha.py` (new, strategy / request-response)

**Analog:** `auction_preopen_quant.py` (filter 28-35, 双阈值) + `auction_early_star.py` (filter 39-40, 列存在性分支) — 双分支互斥。

**列存在性互斥分支（复制 auction_early_star.py:37-41 的 `in df.columns` 模式）:**
```python
def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    if "auction_volume_ratio" in df.columns and "auction_amount" in df.columns:
        # 真列分支: probe available → 消费真实竞价列
        return (
            (pl.col("auction_volume_ratio") >= 1.0)
            & (pl.col("open_gap") >= 0.015)
            & (pl.col("auction_amount") >= 1_000_000)
        )
    # 派生分支: 竞价列缺席 → fail-closed 回退 open_gap + 量比/金额强度 (永不与真列混用)
    return (
        (pl.col("open_gap") >= 0.02)
        & (pl.col("vol_ratio_5d") >= 1.2)
        & (pl.col("amount") >= 1_000_000)
    )
```
> `scoring` 声明超集 `{"open_gap":0.25,"auction_volume_ratio":0.25,"auction_amount":0.25,"vol_ratio_5d":0.15,"amount":0.10}`（和=1.0），引擎 `_apply_scoring` 缺列跳过 + 归一化兜底（engine.py:496-497, 498）。

---

### 6. `backend/app/strategy/builtin/golden_230.py` (new, strategy / request-response)

**Analog:** `strong_open.py` (filter 34-44: change_pct + close>open + 参数化布尔开关) + `volume_price_surge.py` (filter 40: `pl.col("close") > pl.col("open")` 收阳) — EOD 日线列模式。

**EOD 日线带 + 收阳（复制 strong_open.py:37-43 的布尔开关链）:**
```python
def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("use_change_band", True):
        expr = expr & (pl.col("change_pct") >= 0.03) & (pl.col("change_pct") <= 0.05)
    if params.get("require_bullish_candle", True):
        expr = expr & (pl.col("close") > pl.col("open"))   # 收阳
    return expr
```
> **META 差异（label-drift 防线, T-21-02）**: `"time_window": "post_close"`, id 用 `golden_230`（**无 `auction_` 前缀**），描述明示"尾盘 14:30 后选股、次日持有，非竞价窗口"。分钟确认（14:30–15:00 尾盘不弱）为可选增强 — 经 21-01 的分钟 seam（engine.py 新 `minute_confirm_fn`），分钟数据缺席 → 日线核心池仍诚实产出。**禁引用任何 `auction_*` 列**。

---

### 7. `backend/tests/test_auction_strategy_family.py` (new, test / transform)

**Analog:** `test_auction_strategies.py` — `_governed_fixture`/`_engine`/`_run_auction` (26-64) + 权重和=1.0 (105-108) + `test_auction_columns.py` `_patch_probe` 状态矩阵 (53-55, 132-158)。

**fixture/engine helper 直接复制 (test_auction_strategies.py:26-64):**
```python
_auction_ids = (…)
_BUILTIN_DIR = Path(__file__).resolve().parents[1] / "app" / "strategy" / "builtin"

def _governed_fixture() -> pl.DataFrame:
    """仅含受管列的 fixture (symbol/open_gap/change_pct/vol_ratio_5d), 证明 filter 只在受管列上跑。"""
    return pl.DataFrame({…})

def _engine() -> StrategyEngine:
    return StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[_BUILTIN_DIR],
    )

def _run_auction(engine: StrategyEngine, strategy_id: str, fixture: pl.DataFrame):
    return engine.run(
        strategy_id, as_of=date(2026, 8, 4), precomputed=fixture,
        overrides={"basic_filter": {"enabled": False}},
    )
```

**probe 状态 × 缺列矩阵 (test_auction_columns.py:53-55 + 132-158) — 引擎短路 + filter 守卫双保险断言:**
```python
def _patch_probe(monkeypatch, verdict) -> None:
    from app.services import auction_columns
    monkeypatch.setattr(auction_columns, "resolve_auction_probe", lambda: verdict)

def test_non_available_statuses_keep_absent(…):
    """not_configured / fail_closed / error 三态 → 列缺席 + open_gap 恒在; error 详情 ≤200。"""
```
> Phase 21 新增: 遍历 `not_configured/fail_closed/error` 三态断言竞价策略空池（T-21-03）；权重和=1.0 fixture 沿 105-108；"确认时刻之后无输入"回归喂 eval 后 bar 断言未参与（T-21-01）。

---

### 8. `backend/app/strategy/builtin/auction_allround.py` (new, P2, strategy / request-response)

**Analog:** 21-01 产物 `auction_fast_grab` 的 fail-closed filter 形 + `auction_bullish` META 形（同期文件为模板, role-match）。

**核心 AND + 可选列守卫（复制 auction_fast_grab 守卫 + auction_early_star 可选列语义）:**
```python
def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    if "open_gap" not in df.columns or "auction_volume_ratio" not in df.columns:
        return pl.lit(False)
    expr = (
        (pl.col("open_gap") >= 0.02)
        & (pl.col("auction_volume_ratio") >= 1.2)
        & (pl.col("auction_amount") >= 1_000_000)
    )
    # 可选: 仅当列存在才收窄 (沿 auction_early_star.py:39 语义); pre_open 窗口禁 EOD 列
    if params.get("use_turnover", False) and "turnover_rate" in df.columns:
        expr = expr & (pl.col("turnover_rate") >= 0.03)
    return expr
```
> **pre_open 窗口白名单（T-21-04）**: 禁引用 `change_pct`/`vol_ratio_5d`/`amount`（EOD 列 = lookahead, PITFALLS #7）。

---

### 9. `backend/app/strategy/builtin/t1_flash.py` (new, P2, strategy / request-response)

**Analog:** `near_limit_up.py` (46-62: EXIT_SIGNALS + MAX_HOLD_DAYS + EOD filter) + `auction_bullish` META 形。

**EXIT/持有语义（复制 near_limit_up.py:46-50 的信号/持有段）:**
```python
ENTRY_SIGNALS = []
EXIT_SIGNALS = ["signal_ma20_breakdown"]   # T+1 次日早盘卖出确认 → EXIT 语义, 不进池
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 1                          # T+1 闪电: 次日卖出 (回测用)
ALERTS = []
```
> **池只含 T 日竞价买入信号（无 lookahead, T-21-08）**: "次日早盘分钟 K 卖出"只作 `EXIT_SIGNALS`/描述语义，**不**用 T+1 数据计算池成员。filter 形同 auction_fast_grab（`requires_auction_data` + 缺列 `pl.lit(False)`），阈值 `open_gap >= 0.025 & auction_volume_ratio >= 2.0 & auction_amount >= 2_000_000`。

---

### 10. `backend/app/strategy/builtin/auction_intraday_confirm.py` (new, P2, strategy / request-response + minute)

**Analog（partial）:** 无内置策略消费分钟帧；最接近的多行时间序列模式是 `filter_history`（engine.py:287-301 seam + strategy-guide.md:103-138 模板）。

**日线初筛 filter + 分钟确认钩子（seam 消费端, 无既有内置先例）:**
```python
# filter(): 日线初筛 — 只允许 pre_open 可算列 (open_gap/竞价列), EOD 列一票否决
def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    if "open_gap" not in df.columns:
        return pl.lit(False)
    return (pl.col("open_gap") >= 0.02)

# minute_confirm_fn(): 引擎已截断 datetime <= evaluation_time; 只消费分钟帧内统计
def minute_confirm(df_minute: pl.DataFrame, params: dict) -> pl.DataFrame:
    elapsed = trading_minutes_elapsed_from_dt(dt_time(9, 45))   # 15.0
    time_factor = 240.0 / elapsed if elapsed > 0 else 1.0       # 16.0
    # … cum_volume * time_factor >= 阈值 & close >= open (量价齐升/不破开盘价) …
```
> META: `"time_window": "intraday"`, `"evaluation_time": "09:45"`。`minute_loader` 数据访问唯一路径 = `repo.get_minute_batch(symbols, trade_date)`（repository.py:1259-1276）。分钟数据缺席 → 空池（fail-closed）。

---

### 11. `backend/tests/test_auction_strategy_family_p2.py` (new, P2, test / transform)

**Analog:** 21-01 `test_auction_strategy_family.py` helpers（直接扩展）+ `test_auction_probe.py` FakeAuctionProvider + 手工写 parquet fixture（test_auction_columns.py:58-61 `_write_auction_partition`）。

**手工分钟帧 fixture（复制 test_auction_columns.py:58-61 的写分区模式）:**
```python
def _write_minute_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    out = data_dir / "kline_minute" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)
```
> 分钟 canonical 8 列（kline_sync.py:535-537）: `["symbol", "datetime", "open", "high", "low", "close", "volume", "amount"]`。关键回归: `test_intraday_truncation`（喂 eval 后 bar → 断言未参与）+ `test_time_factor`（09:45→15→16.0 fixture）。

---

### 12. `docs/features.md` (modified, P2, docs)

**Analog:** 模块内 9-11 内置策略计数段。`docs/features.md:11` 现写 **"21 个内置策略"** — 与源码一致（21 .py，`__init__.py` 除外），+6 后对账到 **27**；13-18 表的 `竞价 / 盘前` 行追加 极速抢筹 · 竞价阿尔法 · 金色两点半 · 竞价全面 · T+1闪电 · 盘中确认。

### 13. `docs/strategy.md` (modified, P2, docs)

**Analog:** 模块内 9-11 内置策略计数段。`docs/strategy.md:11` 现写 **"18 个内置策略"** — **已漂移**（源码 21），对账到 **27**（PITFALLS #6 警告：文档声称数量 ≠ `strategy/builtin/*.py` 文件数）。

### 14. `backend/app/strategy/prompts/strategy-guide.md` (modified, P2, docs/contract)

**Analog:** 模块内 15-87 文件结构模板 + 89-145 filter_history 契约。

**META 字段契约追加（在 strategy-guide.md:21-49 META 块后补 3 字段）:**
```python
# Phase 21 契约字段 (引擎读取):
"time_window": "pre_open | intraday | post_close",  # 可计算时间窗声明
"evaluation_time": "HH:MM",                        # 盘中/尾盘分钟确认截断时刻 (如 09:45 / 15:00)
"requires_auction_data": True,                     # 竞价列缺席 → 引擎短路空池
```
> 同时在 89-145 后补 `minute_confirm_fn` 契约: 截断点只在引擎（`datetime <= evaluation_time`）、`time_factor = 240/elapsed`、禁 EOD 列引用。AI/自定义策略生成才知该字段（21-RESEARCH Deprecated/outdated 项）。

## Shared Patterns

### 内置策略 META 全形
**Source:** `auction_bullish.py:4-19` / `strong_open.py:4-25`
**Apply to:** 全部 6 新策略文件
```python
META = {"id", "name", "description", "tags", "params": [{"id","label","type","default","min","max","step"}], "scoring", "order_by", "descending", "limit"}
ENTRY_SIGNALS/EXIT_SIGNALS/STOP_LOSS/MAX_HOLD_DAYS/ALERTS
def filter(df: pl.DataFrame, params: dict) -> pl.Expr
```
Phase 21 追加 `time_window` / `evaluation_time` / `requires_auction_data`。

### filter 缺列 fail-closed 守卫
**Source:** 21-RESEARCH Code Ex 2（新模式；列存在性判断镜像 `auction_early_star.py:39`）
**Apply to:** 全部 `requires_auction_data=True` 策略 + 竞价全面 + 盘中确认
```python
if "col" not in df.columns: return pl.lit(False)   # 整池为假 → 空池, 绝不 0 填充
```

### 引擎缺列短路空池（双保险之一）
**Source:** `engine.py:302-307` 空帧早退 + `engine.py:496-497` 缺列跳过
**Apply to:** `engine.run()` 数据加载后
```python
if s.meta.get("requires_auction_data") and "auction_volume" not in df.columns:
    return StrategyResult(as_of=as_of, strategy_id=strategy_id)
```

### 评分权重和=1.0
**Source:** `test_auction_strategies.py:105-108`（fixture）+ `engine.py:498`（归一化）
**Apply to:** 全部 6 新策略 `META["scoring"]` + P1/P2 测试
```python
for strat in (…):
    assert sum(strat.META["scoring"].values()) == pytest.approx(1.0)
```

### probe×分区双闸门 + probe 状态矩阵
**Source:** `auction_columns.py:53-102`（attach 双闸门）+ `test_auction_columns.py:53-55`（`_patch_probe`）+ `auction_probe.py:33-37`（`AuctionProbeStatus` 四值）
**Apply to:** `auction_volume_ratio` 派生、引擎短路测试、P1 三策略缺列空池断言
```python
if resolve_auction_probe().status != AuctionProbeStatus.available:
    return df   # 列缺席
```

### 分钟帧读取（唯一数据访问路径）
**Source:** `repository.py:1259-1276`（`get_minute_batch`）
**Apply to:** 21-01 分钟 seam / STRAT-09 / STRAT-06 尾盘确认
```python
return pl.scan_parquet(self._minute_glob_for(asset_type)).filter(
    pl.col("symbol").is_in(symbols) & (pl.col("datetime").dt.date() == trade_date)
).sort(["symbol", "datetime"]).collect()
```

### time_factor 折算
**Source:** `market_time.py:14,31-47`（`_TRADING_TOTAL_MINUTES=240` + `trading_minutes_elapsed_from_dt`）+ `pipeline.py:1408-1411`
**Apply to:** STRAT-09 盘中量比 / STRAT-06 尾盘确认
```python
time_factor = 240.0 / elapsed if elapsed and elapsed > 0 else 1.0   # eval=09:45 → tf=16.0
```

### 注册/去重（无第三条轨道）
**Source:** `engine.py:149-169`（`_load_all`）+ `api/screener.py:218-251`（PRESET 先 + seen_ids 去重）
**Apply to:** 6 新策略文件 + `test_no_third_registry` 回归
```python
for meta in engine.list_strategies():
    sid = meta["id"]
    if sid not in seen_ids: …   # 只经 builtin 发现, PRESET 零碰撞
```

## Divergences (Phase 21 特有差异, planner 须注意)

1. **`pre_open` 窗口禁 EOD 列（lookahead 硬红线）:** 极速抢筹/竞价阿尔法真列分支/竞价全面/盘中确认初筛**禁**引用 `change_pct`/`vol_ratio_5d`/`amount`/`close`/`turnover_rate`（除显式"盘后参考"标注）— 这些只在收盘后可算（PITFALLS #7）。既有 Phase 17 三策略（auction_bullish 等）引用了 `change_pct`/`vol_ratio_5d`（EOD 列），**不可直接复制**到 pre_open 策略的 filter。
2. **`auction_volume_ratio` 只走受管列注入:** 禁用 `auction_volume/(volume/vol_ratio_5d)` 内联 — 内联分母含当日 EOD 量 → pre_open lookahead；受管列前 5 日均量（不含当日）PIT-safe（RESEARCH A1）。
3. **金色两点半永不带 `auction_` 前缀:** id `golden_230`、`time_window: "post_close"`、描述明示尾盘/隔夜 — 即使它属于"竞价策略族"分组（T-21-02 label drift 防线）。
4. **`requires_auction_data` 是引擎契约而非策略自觉:** 短路空池是双保险之一；策略 filter 还要对每个必需列 `pl.lit(False)` 守卫（漏写即 ColumnNotFoundError 而非 fail-closed）。
5. **`evaluation_time` 截断只在引擎单点:** 策略拿到的分钟帧物理上不含 eval 后 bar；策略内任何"当前墙钟"判断都是反模式（T-21-01 硬验收）。
6. **STRAT-08 T+1 卖出不进池:** "次日早盘卖出确认"只作 `EXIT_SIGNALS`/`MAX_HOLD_DAYS=1` 语义；用 T+1 数据算池成员即 lookahead（A5）。
7. **scoring 超集策略（竞价阿尔法）依赖引擎缺列跳过:** 真/派生分支共用超集权重，缺席列静默跳过 + 重归一化（engine.py:496-497）— 新策略的测试必须断言 `_apply_scoring` 在缺列时不崩溃。

## No Analog Found (Gaps)

| File / Feature | Role | Data Flow | Reason / Fallback |
|----------------|------|-----------|-------------------|
| engine `minute_loader`/`confirm_minute` seam | engine | minute | 引擎现无"按候选 symbols 二次加载分钟帧"的钩子；`filter_history_fn` (287-301) 是最接近的多日窗口钩子但返回整帧、非按池回载。**Fallback:** 镜像 `filter_history_fn` 分支形态 + `repo.get_minute_batch` (repository.py:1259-1276) + 21-RESEARCH RQ3 规约 |
| engine 单点 `datetime <= evaluation_time` 截断 | engine | minute | 引擎无任何分钟截断逻辑；`monitor.py:766-796` 的"历史窗口 + 今日实时行拼接"语义不同（拼行而非截断）。**Fallback:** 21-RESEARCH RQ3 规约 + "确认时刻之后无输入"回归 |
| engine `requires_auction_data` 短路空池 | engine | request-response | 现引擎对 filter 无列存在性 gate（引用缺失列抛 ColumnNotFoundError）；唯一"缺列静默"是 scoring 跳过 (496-497)。**Fallback:** 21-RESEARCH Code Ex 4 + filter `pl.lit(False)` 双保险 |
| `auction_volume_ratio` 受管列派生注入 | service | transform | 现无"受管列按 (trade_date) 用前日数据派生再注入"的先例；`vol_ratio_5d` (pipeline.py:1404-1416) 是日线折算语义最接近者，但无"注入列"机制（只作计算列）。**Fallback:** 21-RESEARCH RQ2 受管列规约 + `repo.get_enriched_history` (937-964) |
| `strategy-guide.md` 时间窗/分钟确认字段契约 | docs/contract | — | 文档现只有 META 标准字段 (15-87) + filter_history 契约 (89-145)，无 `time_window`/`evaluation_time`/`requires_auction_data`/`minute_confirm_fn`。**Fallback:** 21-RESEARCH RQ1 META 字段表 + RQ3 规约 |
| `auction_intraday_confirm.py`（盘中确认） | strategy | minute | 无既有内置策略消费 `kline_minute`；filter_history 模板 (strategy-guide.md:103-138) 是最接近的多行时间序列模式。**Fallback:** 引擎 seam + 21-RESEARCH STRAT-09 因子表 |

> 其余 9 个文件均有 exact/role-match analog；上述 6 项是**引擎级/契约级子功能**缺口，非整文件无类比 — planner 需以 21-RESEARCH.md（RQ1/RQ2/RQ3 + Code Examples + Threat Model）作为兜底实现依据。

## Metadata

**Analog search scope:** `backend/app/strategy/`（engine.py + builtin/ 21 策略）、`backend/app/services/`（auction_columns.py, auction_probe.py, screener.py）、`backend/app/indicators/pipeline.py`、`backend/app/market_time.py`、`backend/app/tickflow/repository.py`、`backend/app/api/screener.py`、`backend/tests/`（test_auction_strategies.py, test_auction_columns.py, test_auction_probe.py）、`backend/app/strategy/prompts/strategy-guide.md`、`docs/features.md`、`docs/strategy.md`、`.planning/milestones/v1.3-phases/17-auction-strategy-family/`（17-01/17-02-PLAN）
**Files scanned:** 18（engine.py, auction_bullish.py, auction_preopen_quant.py, auction_early_star.py, strong_open.py, volume_price_surge.py, near_limit_up.py, auction_columns.py, auction_probe.py, pipeline.py, market_time.py, repository.py, screener.py, api/screener.py, test_auction_strategies.py, test_auction_columns.py, strategy-guide.md, 17-01/17-02-PLAN）
**Pattern extraction date:** 2026-08-05
**Line numbers verified against live code:** 全部 excerpt 行号在本 session 逐行读取确认。
