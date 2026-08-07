"""竞价族策略全量回测服务 (BT-07/BT-09) — 单面板向量化回测 + 确定性持久化。

``run_full_backtest`` 把 9 个竞价族策略在 enriched 历史窗口上的信号质量端到端
装配为可持久化回测: 单面板装载 (get_enriched_range 快路径) → 分区存在性注入
(attach_auction_columns_range, D-03) → 策略枚举 + 互斥 branch (BT-05) →
候选掩码 (镜像 auction_validation 模块级助手) → BT-04 前瞻 (unbound
``AuctionValidationService._forward_stats`` 共源) → 长格式命中行 + manifest →
``backtest_results/run_id={确定性哈希}/`` 原子持久化, 幂等可重跑。

铁律 (镜像 auction_validation.py:1-33 纪律):
- 写根隔离 (E2): 只写 ``backtest_results/`` 根 (mkdir/write_parquet/os.replace 的
  目标路径一律构造在该根之下); 绝不触碰 strategy_cache / screener_results /
  kline_auction / kline_daily_enriched 等湖。
- 零 live probe (D-03): 历史闸门 = kline_auction 分区存在性 ONLY
  (attach_auction_columns_range 主闸门), 绝不调用 live 探测 —— 历史日确定性/
  网络无关/可复现; 本模块不 import 探测模块 (34-03 AST 守卫零 token 锁)。
- 零执行族 import: 不 import 执行族模块 (broker/order/execution/trade/portfolio/
  position/account/transaction); 不 import 竞价同步/快照/回填/预览/选股触发面模块。
- 本回测区间不受回测 186 天 guard 限制 (D-06): 回测 guard 保护组合回测/因子评估
  内存 (api/backtest.py:29-32, 默认关闭 config.py:103); 本回测是单面板向量化扫描,
  覆盖由 enriched 缓存边界决定, 窗口回夹 + requested/effective 双字段回显。
- O3: backtest_results v1 不含概念 PIT as_of 列 (镜像验证报告; 概念归属属 pool
  渲染, 不属于信号回测 —— 诚实缺维度, manifest 不声称概念归属)。
- BT-10: kline_minute 历史 CLOSED, 逐行 ``minute_confirm="not_applied"`` +
  manifest ``minute_note`` 诚实注解; auction_intraday_confirm 恒空 (设计使然)。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from app.services.auction_columns import attach_auction_columns_range
from app.services.auction_validation import (
    AuctionValidationService,
    _FORWARD_METRICS,
    _aggregate_metric,  # noqa: F401 — 模块级纯助手 import 面 (34-03 守卫白名单契约)
    _build_candidate_mask,
    _null_metric,
)
from app.services.pool_snapshot import strategy_fingerprint

logger = logging.getLogger(__name__)

# 竞价族 9 策略硬编码 id 集 (与服务/测试文件逐字一致防漂移; 策略定义一律从 engine 取)
_AUCTION_FAMILY_IDS = frozenset({
    "auction_fast_grab", "auction_allround", "t1_flash", "auction_intraday_confirm",
    "auction_alpha", "golden_230", "auction_bullish", "auction_preopen_quant",
    "auction_early_star",
})

# 缺省窗口: end 缺省 = enriched 最新交易日; start 缺省 = end − 120 自然日 (与 auction_history days=120 对齐)
_DEFAULT_WINDOW_DAYS = 120
# warmup 前导余量 (≥5 交易日, 镜像 auction_validation._WARMUP_DAYS)
_WARMUP_DAYS = 14

# 回测湖 provenance (与 {eod,backfill,manual} 池词汇区分)
_ORIGIN = "research"
# BT-10 逐行分钟确认注解
_MINUTE_CONFIRM = "not_applied"
_MINUTE_NOTE = (
    "kline_minute 历史 CLOSED — 确认维度诚实受限; auction_intraday_confirm minute 确认恒空 (BT-10); "
    "auction_intraday_confirm branch=real 日线初筛仅消费 open_gap (enriched 派生列, 非竞价列) — "
    "其 hits 不随湖覆盖增长 (52,591 全市场恒定, 2026-08-07 实测)"
)

# 写根 (E2): 本模块唯一写面
_BACKTEST_ROOT = "backtest_results"


def _empty_rows_frame() -> pl.DataFrame:
    """长格式命中行的空帧 (统一 schema, 空策略/空 run 亦可持久化)。"""
    return pl.DataFrame(schema=_ROW_SCHEMA)


_ROW_SCHEMA: dict[str, pl.DataType] = {
    "run_id": pl.Utf8,
    "strategy": pl.Utf8,
    "branch": pl.Utf8,
    "as_of": pl.Date,
    "symbol": pl.Utf8,
    "entry_open": pl.Float64,
    "open_t1": pl.Float64,
    "close_t1": pl.Float64,
    "next_day_open_ret": pl.Float64,
    "next_day_close_ret": pl.Float64,
    "open_gap_outcome": pl.Float64,
    "outcome_missing": pl.Boolean,
    "params_json": pl.Utf8,
    "strategy_version": pl.Utf8,
    "origin": pl.Utf8,
    "minute_confirm": pl.Utf8,
    "created_at": pl.Utf8,
}


# ── 装载 / 窗口 (镜像 auction_validation.build_report 装配形) ─────────────


def _enriched_coverage(repo) -> tuple[date | None, date | None]:
    """enriched 缓存覆盖 [min, max]; 缓存空 → 回退扫 kline_daily_enriched/date=* 目录
    (解析失败跳过); 仍无 → (None, None) → enriched_unavailable。
    语义镜像 AuctionValidationService._enriched_coverage。"""
    cache = repo._enriched_history_cache
    if cache is not None and not cache.is_empty() and "date" in cache.columns:
        return cache["date"].min(), cache["date"].max()

    base = repo.store.data_dir / "kline_daily_enriched"
    dates: list[date] = []
    if base.exists():
        for part in base.glob("date=*"):
            name = part.name
            if not name.startswith("date="):
                continue
            try:
                dates.append(date.fromisoformat(name[len("date="):]))
            except ValueError:
                continue
    if not dates:
        return None, None
    return min(dates), max(dates)


def _resolve_window(
    start: date | None,
    end: date | None,
    cache_min: date,
    cache_max: date,
) -> tuple[dict, date, date]:
    """窗口解析 + 回夹 (D-06): requested_* 保留原始请求, effective_* 回夹到缓存覆盖。
    绝不套用回测 186 天 guard; 回夹后 start > end 由调用方判 no_dates_in_window。"""
    end = end or cache_max
    start = start or (end - timedelta(days=_DEFAULT_WINDOW_DAYS))
    requested_start, requested_end = start, end
    start = max(start, cache_min)
    end = min(end, cache_max)
    window = {
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "effective_start": start.isoformat(),
        "effective_end": end.isoformat(),
    }
    return window, start, end


def _resolve_strategy_ids(
    strategy_ids: list[str] | None, engine
) -> tuple[list[str], list[str]]:
    """解析待回测策略 id 列表 + skipped_ids (语义镜像 AuctionValidationService._resolve_strategy_ids):

    - None → 9 个竞价族 ∩ engine (引擎缺失的族 id 记 skipped, 不静默消失);
    - 显式 [] → 空列表 (strategies: [], 镜像选股服务空列表语义);
    - 非空列表 → 竞价族 ∩ engine ∩ 请求集; 请求集不含任何可解析竞价族策略
      (全未知/越界) → 回落默认竞价族范围; 请求但未报告的 id → skipped_ids。
    """
    family = sorted(_AUCTION_FAMILY_IDS)
    engine_ids = set(engine._strategies)
    if strategy_ids is None:
        ids = [sid for sid in family if sid in engine_ids]
        skipped = [sid for sid in family if sid not in engine_ids]
    elif not strategy_ids:
        ids, skipped = [], []
    else:
        requested = list(strategy_ids)
        ids = [sid for sid in family if sid in engine_ids and sid in requested]
        if not ids:
            ids = [sid for sid in family if sid in engine_ids]
        skipped = [sid for sid in requested if sid not in ids]
    return ids, skipped


# ── 单策略评估 (镜像 auction_validation._evaluate_strategy 逐字段语义) ──────


def _build_per_date(eval_panel: pl.DataFrame, hits: pl.DataFrame) -> list[dict]:
    """per_date: 评估面板全日期 (n_screened = 该日面板行数) 左联命中计数 (n_hits,
    缺命中的评估日 0 填 — 真实计数)。镜像 AuctionValidationService._build_per_date。"""
    per = (
        eval_panel.group_by("date").len().rename({"len": "n_screened"})
        .join(hits.group_by("date").len().rename({"len": "n_hits"}), on="date", how="left")
        .with_columns(pl.col("n_hits").fill_null(0).cast(pl.Int64))
        .sort("date")
    )
    return [
        {
            "date": row["date"].isoformat(),
            "n_screened": int(row["n_screened"]),
            "n_hits": int(row["n_hits"]),
        }
        for row in per.iter_rows(named=True)
    ]


def _n_symbols_covered(eval_panel: pl.DataFrame) -> int:
    """eval 面板中竞价列非空 symbol 去重数 (诚实覆盖: 稀疏湖 2-symbol 宇宙如实标注)。"""
    if eval_panel.is_empty() or "auction_volume" not in eval_panel.columns:
        return 0
    return int(eval_panel.filter(pl.col("auction_volume").is_not_null())["symbol"].n_unique())


def _build_strategy_rows(
    hits: pl.DataFrame,
    verification_panel: pl.DataFrame,
    enriched_dates: list[date],
    *,
    sid: str,
    branch: str,
    run_id: str,
    params: dict,
    strategy_version: str,
    created_at: str,
) -> pl.DataFrame:
    """长格式命中行 (RESEARCH §6 列 schema 逐字)。

    前瞻值 = 与 ``AuctionValidationService._forward_stats`` 逐字一致的日历 join
    (全局 next-date + 结果面板左联 + 三公式), 行级 outcome_missing/公式列与 BT-04
    聚合计数零漂移; 公式列 null 保留 (绝不 0 填/前向填充)。
    """
    if hits.is_empty():
        return _empty_rows_frame()

    dates = list(enriched_dates)
    calendar = pl.DataFrame({"date": dates, "outcome_date": dates[1:] + [None]}).with_columns(
        pl.col("outcome_date").cast(pl.Date)
    )
    h = hits.join(calendar, on="date", how="left")
    # 结果日全部为 null 时 (窗口末日命中) polars 会降级为 Null 型, 显式回 cast 到 Date
    h = h.with_columns(pl.col("outcome_date").cast(pl.Date, strict=False))

    outcomes = verification_panel.select(["symbol", "date", "open", "close"]).rename(
        {"date": "outcome_date", "open": "next_open", "close": "next_close"}
    )
    h = h.join(outcomes, on=["symbol", "outcome_date"], how="left")

    h = h.with_columns(
        [
            pl.when(
                pl.col("open").is_not_null() & (pl.col("open") > 0) & pl.col("next_open").is_not_null()
            )
            .then(pl.col("next_open") / pl.col("open") - 1.0)
            .otherwise(None)
            .alias("next_day_open_ret"),
            pl.when(
                pl.col("open").is_not_null() & (pl.col("open") > 0) & pl.col("next_close").is_not_null()
            )
            .then(pl.col("next_close") / pl.col("open") - 1.0)
            .otherwise(None)
            .alias("next_day_close_ret"),
            pl.when(
                pl.col("close").is_not_null() & (pl.col("close") > 0) & pl.col("next_open").is_not_null()
            )
            .then(pl.col("next_open") / pl.col("close") - 1.0)
            .otherwise(None)
            .alias("open_gap_outcome"),
            pl.col("next_open").is_null().alias("outcome_missing"),
        ]
    )
    params_json = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return h.select(
        [
            pl.lit(run_id).alias("run_id"),
            pl.lit(sid).alias("strategy"),
            pl.lit(branch).alias("branch"),
            pl.col("date").alias("as_of"),
            pl.col("symbol"),
            pl.col("open").alias("entry_open"),
            pl.col("next_open").alias("open_t1"),
            pl.col("next_close").alias("close_t1"),
            pl.col("next_day_open_ret"),
            pl.col("next_day_close_ret"),
            pl.col("open_gap_outcome"),
            pl.col("outcome_missing"),
            pl.lit(params_json).alias("params_json"),
            pl.lit(strategy_version).alias("strategy_version"),
            pl.lit(_ORIGIN).alias("origin"),
            pl.lit(_MINUTE_CONFIRM).alias("minute_confirm"),
            pl.lit(created_at).alias("created_at"),
        ]
    )


def _evaluate_strategy_rows(
    s,
    verification_panel: pl.DataFrame,
    auction_enabled_dates: list[date],
    enriched_dates: list[date],
    *,
    run_id: str,
    params_snapshot: dict,
    strategy_version: str,
    created_at: str,
) -> dict:
    """单策略评估 (镜像 auction_validation._evaluate_strategy 逐字段语义):

    - branch 互斥 (BT-05): 4 个 requires_auction_data 恒 real (enabled 子面板,
      湖空 n_dates==0 绝不落 derived); auction_alpha real|derived; 4 个 EOD 恒 eod;
    - 参数恒 META 默认 (镜像 engine.py:227-231 归一化后的 {p["id"]: p["default"]});
    - 候选掩码 import 模块级助手 → hits/per_date;
    - 前瞻 = unbound ``AuctionValidationService._forward_stats`` (BT-04 共源零漂移);
    - 行帧 = _build_strategy_rows (长格式命中行)。
    """
    meta = s.meta
    sid = str(meta.get("id", ""))
    requires = bool(meta.get("requires_auction_data", False))
    params = {p["id"]: p["default"] for p in meta.get("params", [])}

    if requires:
        branch = "real"
        eval_panel = verification_panel.filter(pl.col("date").is_in(auction_enabled_dates))
    elif sid == "auction_alpha":
        branch = "real" if auction_enabled_dates else "derived"
        eval_panel = (
            verification_panel.filter(pl.col("date").is_in(auction_enabled_dates))
            if branch == "real"
            else verification_panel
        )
    else:
        branch = "eod"
        eval_panel = verification_panel

    if eval_panel.is_empty():
        # 诚实空: n_dates==0, 不调掩码 (real 策略湖空绝不落 derived, D-02)
        n_dates, n_hits, coverage = 0, 0, 0.0
        per_date: list[dict] = []
        n_missing = 0
        forward_stats = {m: _null_metric() for m in _FORWARD_METRICS}
        n_symbols_hit = 0
        rows = _empty_rows_frame()
    else:
        n_dates = len(eval_panel["date"].unique())
        mask = _build_candidate_mask(eval_panel, s, params)
        hits = eval_panel.filter(mask)
        n_hits = hits.height
        coverage = (len(hits["date"].unique()) / n_dates) if n_dates else 0.0
        per_date = _build_per_date(eval_panel, hits)
        forward_stats, n_missing = AuctionValidationService._forward_stats(
            None, hits, verification_panel, enriched_dates
        )
        n_symbols_hit = int(hits["symbol"].n_unique()) if not hits.is_empty() else 0
        rows = _build_strategy_rows(
            hits,
            verification_panel,
            enriched_dates,
            sid=sid,
            branch=branch,
            run_id=run_id,
            params=params,
            strategy_version=strategy_version,
            created_at=created_at,
        )

    stats = {
        "id": sid,
        "name": str(meta.get("name", sid)),
        "branch": branch,
        "requires_auction_data": requires,
        "minute_confirm": _MINUTE_CONFIRM,
        "params": params,
        "n_dates": n_dates,
        "n_hits": n_hits,
        "coverage": coverage,
        "n_symbols_covered": _n_symbols_covered(eval_panel),
        "n_symbols_hit": n_symbols_hit,
        "n_missing_outcomes": n_missing,
        "forward_stats": forward_stats,
        "per_date": per_date,
    }
    return {"stats": stats, "rows": rows}


# ── 覆盖统计 (BT-08 符号级诚实覆盖) ────────────────────────────────────────


def _lake_auction_symbol_count(data_dir: Path, start: date, end: date) -> int:
    """湖覆盖 digest 分量 (RC-01): [start, end] 窗口内 kline_auction 去重 symbol 数。

    镜像 _coverage_symbols 的分区扫描语义逐字 (glob date=*/part.parquet,
    fromisoformat 目录名解析, 坏名/空分区/缺 symbol 列跳过, 窗口过滤) —
    保证 digest 与 coverage.symbols.auction_symbol_count 报告值恒等 (零 view-vs-scan 漂移)。
    只读, 零写面 (E2 守卫安全); 异常/空湖 → 0 (fail-closed 确定性)。"""
    base = data_dir / "kline_auction"
    symbols: set[str] = set()
    if base.exists():
        for part in sorted(base.glob("date=*/part.parquet")):
            name = part.parent.name
            if not name.startswith("date="):
                continue
            try:
                d = date.fromisoformat(name[len("date="):])
            except ValueError:
                continue
            if not (start <= d <= end):
                continue
            try:
                f = pl.read_parquet(part)
            except Exception:  # noqa: BLE001 — 只读统计 fail-closed 跳过
                continue
            if f.is_empty() or "symbol" not in f.columns:
                continue
            symbols.update(f["symbol"].unique().to_list())
    return len(symbols)


def _coverage_symbols(
    data_dir: Path,
    start: date,
    end: date,
    verification_panel: pl.DataFrame,
    enriched_dates: list[date],
) -> dict:
    """符号级覆盖 (诚实): 扫 kline_auction 窗口 date=* 分区 (只读; 坏目录名/空分区/
    读盘异常 fail-closed 跳过) 统计 auction_symbol_count / auction_rows_present;
    enriched_symbol_count = 验证面板 symbol n_unique;
    auction_rows_expected = enriched_symbol_count × n_dates。"""
    base = data_dir / "kline_auction"
    symbols: set[str] = set()
    rows_present = 0
    if base.exists():
        for part in sorted(base.glob("date=*/part.parquet")):
            name = part.parent.name
            if not name.startswith("date="):
                continue
            try:
                d = date.fromisoformat(name[len("date="):])
            except ValueError:
                continue
            if not (start <= d <= end):
                continue
            try:
                f = pl.read_parquet(part)
            except Exception:  # noqa: BLE001 — 只读统计 fail-closed 跳过
                continue
            if f.is_empty() or "symbol" not in f.columns:
                continue
            symbols.update(f["symbol"].unique().to_list())
            rows_present += f.height
    enriched_symbol_count = (
        int(verification_panel["symbol"].n_unique()) if not verification_panel.is_empty() else 0
    )
    return {
        "auction_symbol_count": len(symbols),
        "enriched_symbol_count": enriched_symbol_count,
        "symbol_coverage_ratio": (
            (len(symbols) / enriched_symbol_count) if enriched_symbol_count else 0.0
        ),
        "auction_rows_present": rows_present,
        "auction_rows_expected": enriched_symbol_count * len(enriched_dates),
    }


# ── 主函数 (BT-07 计算核心) ────────────────────────────────────────────────


def run_full_backtest(
    repo,
    engine,
    *,
    start: date | None = None,
    end: date | None = None,
    strategy_ids: list[str] | None = None,
    symbols: list[str] | None = None,
    on_progress: Callable[[str], None] | None = None,
    job_id: str | None = None,
) -> dict:
    """竞价族策略全量回测 (BT-07 计算面; BT-09 写侧见 _persist_run 接线)。

    步骤 (镜像 build_report 装配形):
    ① enriched 覆盖 [cache_min, cache_max] → 空 → 诚实 dict enriched_unavailable;
    ② 窗口解析+回夹 (D-06): end 缺省 = cache_max, start 缺省 = end−120 自然日,
       requested/effective 双字段回显; 回夹后 start>end → no_dates_in_window;
    ③ warmup_start = max(start−14, cache_min), get_enriched_range → None/空 →
       enriched_unavailable;
    ④ attach_auction_columns_range 注入 (分区存在性闸门, 零 live probe) →
       verification_panel + enabled_dates; enriched_dates / auction_enabled_dates;
    ⑤ 策略枚举 = 9 竞价族 ∩ engine (未知 id → skipped_ids, 不 500);
    ⑥ 每策略 _evaluate_strategy_rows (branch 互斥 + META 默认 params + 掩码 +
       per_date + 前瞻共源) → 长格式行帧;
    ⑦ coverage (dates + symbols 双块);
    ⑧ 持久化 (Task 2): 确定性 run_id → 原子 part.parquet + manifest → 幂等跳过。

    on_progress/job_id 为 CLI/未来 job 包装保留 (v1 全 None, 幂等身份计算不含二者)。
    服务级异常直接冒泡 (CLI 负责 try/except); 诚实空 dict 路径不抛。
    """
    data_dir = repo.store.data_dir

    def _progress(msg: str) -> None:
        if on_progress is not None:
            try:
                on_progress(msg)
            except Exception:  # noqa: BLE001 — 进度回调绝不阻塞主流程
                logger.debug("progress callback failed: %s", msg)

    # ① enriched 覆盖
    cache_min, cache_max = _enriched_coverage(repo)
    if cache_min is None or cache_max is None:
        return {"status": "no_enriched", "empty_reason": "enriched_unavailable"}
    _progress(f"load: enriched coverage {cache_min.isoformat()}..{cache_max.isoformat()}")

    # ② 窗口解析 + 回夹 (D-06)
    window, eff_start, eff_end = _resolve_window(start, end, cache_min, cache_max)
    if eff_start > eff_end:
        return {
            "status": "no_dates_in_window",
            "window": window,
            "empty_reason": "no_dates_in_window",
        }
    _progress(f"window: {window}")

    # ③ warmup 面板装载 (W1: warmup_start 夹到 cache_min, 诚实降级而非误报空)
    warmup_start = max(eff_start - timedelta(days=_WARMUP_DAYS), cache_min)
    panel = repo.get_enriched_range(warmup_start, eff_end, symbols=symbols)
    if panel is None or panel.is_empty():
        return {
            "status": "no_enriched",
            "window": window,
            "empty_reason": "enriched_unavailable",
        }
    _progress(f"panel: {panel.height} rows")

    # ④ 注入 (29-01 契约; 历史闸门 = 分区存在性, D-03)
    panel, enabled_dates = attach_auction_columns_range(panel, eff_start, eff_end, repo)
    verification_panel = panel.filter(pl.col("date") >= eff_start)
    enriched_dates = verification_panel["date"].unique().sort().to_list()
    auction_enabled_dates = sorted(set(enabled_dates) & set(enriched_dates))
    _progress(
        f"inject: auction_enabled={len(auction_enabled_dates)} enriched={len(enriched_dates)}"
    )

    # ⑤ 策略枚举 (D-07) + 参数快照 (META 默认, 与 run_id 身份同源)
    ids, skipped_ids = _resolve_strategy_ids(strategy_ids, engine)
    params_snapshot: dict = {}
    for sid in ids:
        try:
            s = engine.get(sid)
        except ValueError:
            skipped_ids.append(sid)
            continue
        params_snapshot[sid] = {p["id"]: p["default"] for p in s.meta.get("params", [])}
    strategy_version = strategy_fingerprint(engine)
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # ⑤-1 湖覆盖 digest (RC-01): 同命令 + 湖覆盖变化 → 新 run_id (防陈旧数据幂等跳过)
    lake_digest = (
        _lake_auction_symbol_count(data_dir, eff_start, eff_end),
        len(auction_enabled_dates),
    )
    run_id = _compute_run_id(ids, eff_start, eff_end, params_snapshot, strategy_version, symbols,
                             lake_digest=lake_digest)

    # ⑥ 逐策略评估
    strategy_results: list[dict] = []
    frames: list[pl.DataFrame] = []
    for sid in ids:
        try:
            s = engine.get(sid)
        except ValueError:
            continue  # 已在 ⑤ 记入 skipped
        res = _evaluate_strategy_rows(
            s,
            verification_panel,
            auction_enabled_dates,
            enriched_dates,
            run_id=run_id,
            params_snapshot=params_snapshot,
            strategy_version=strategy_version,
            created_at=created_at,
        )
        strategy_results.append(res)
        frames.append(res["rows"])
        _progress(
            f"strategy: {sid} branch={res['stats']['branch']} n_hits={res['stats']['n_hits']}"
        )

    rows_df = pl.concat(frames, how="vertical_relaxed") if frames else _empty_rows_frame()

    # ⑦ 覆盖 (日期 + 符号双块, BT-08 诚实覆盖)
    coverage = {
        "dates": {
            "auction_enabled_count": len(auction_enabled_dates),
            "enriched_count": len(enriched_dates),
            "coverage_ratio": (
                (len(auction_enabled_dates) / len(enriched_dates)) if enriched_dates else 0.0
            ),
        },
        "symbols": _coverage_symbols(data_dir, eff_start, eff_end, verification_panel, enriched_dates),
    }

    # ⑧ 持久化 (BT-09 写侧): 确定性 run_id → 原子 part.parquet + manifest → 幂等跳过
    per_date = _merge_per_date(strategy_results)
    fingerprint = json.dumps(
        {
            "strategy_ids": sorted(ids),
            "start": eff_start.isoformat(),
            "end": eff_end.isoformat(),
            "params": params_snapshot,
            "strategy_version": strategy_version,
            "symbols": sorted(symbols or []),
            "lake_coverage": list(lake_digest),
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    manifest = _build_manifest(
        run_id=run_id,
        strategy_version=strategy_version,
        created_at=created_at,
        window=window,
        strategy_summaries=[
            {
                "id": r["stats"]["id"],
                "branch": r["stats"]["branch"],
                "n_dates": r["stats"]["n_dates"],
                "n_hits": r["stats"]["n_hits"],
                "n_symbols_covered": r["stats"]["n_symbols_covered"],
                "n_symbols_hit": r["stats"]["n_symbols_hit"],
                "n_missing_outcomes": r["stats"]["n_missing_outcomes"],
                "forward_stats": r["stats"]["forward_stats"],
            }
            for r in strategy_results
        ],
        params_snapshot=params_snapshot,
        coverage=coverage,
        per_date=per_date,
        fingerprint=fingerprint,
    )
    run_dir, wrote, reused = _persist_run(data_dir, run_id, rows_df, manifest)
    _progress(f"persist: run_id={run_id} wrote={wrote} reused={reused}")

    return {
        "run_id": run_id,
        "origin": _ORIGIN,
        "strategy_version": strategy_version,
        "created_at": created_at,
        "window": window,
        "strategies": [r["stats"] for r in strategy_results],
        "coverage": coverage,
        "skipped_ids": skipped_ids,
        "rows": rows_df,
        "wrote": wrote,
        "reused": reused,
        "path": str(run_dir),
        "status": "ok" if wrote else "reused",
    }


# ── 确定性 run_id (BT-09 身份锚点; 时间无关) ───────────────────────────────


def _compute_run_id(
    strategy_ids: list[str],
    start: date,
    end: date,
    params_snapshot: dict,
    strategy_version: str,
    symbols: list[str] | None,
    *,
    lake_digest: tuple[int, int] | None = None,
) -> str:
    """确定性运行 id (时间无关, 幂等身份锚点):

    sha1(sorted(strategy_ids) | start.isoformat | end.isoformat |
    json(params_snapshot, sort_keys) | strategy_version | sorted(symbols)
    [| lake:auction_symbol_count:auction_enabled_dates])[:12]。

    symbols 纳入哈希 (对 RESEARCH §6 公式的加固): 稀疏 2-symbol 真列运行与全市场
    运行绝不共 run_id, 防幂等跳过遮蔽小宇宙运行。on_progress/job_id 不参与。

    湖覆盖 digest 纳入哈希 (RC-01, 2026-08-07 实测缺口): 同命令 + 湖回填后
    覆盖变化 → 新 run_id, 防幂等跳过静默保留陈旧数据; 同湖同输入 → 仍幂等同 id
    (digest 对湖态确定性)。lake_digest=None → 修复前 blob (向后兼容缺省)。
    """
    blob = (
        "|".join(sorted(strategy_ids))
        + "|" + start.isoformat()
        + "|" + end.isoformat()
        + "|" + json.dumps(params_snapshot, sort_keys=True, ensure_ascii=False)
        + "|" + strategy_version
        + "|" + "|".join(sorted(symbols or []))
    )
    if lake_digest is not None:
        blob += f"|lake:{lake_digest[0]}:{lake_digest[1]}"
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


# ── 持久化 (BT-09 写侧) ────────────────────────────────────────────────────


def _merge_per_date(strategy_results: list[dict]) -> list[dict]:
    """运行级 per_date 汇总: 按日期合并各策略 per_date 条目 (按日期升序)。

    n_screened = 该日所有策略评估行数之和, n_hits = 该日命中数之和 (跨 branch
    面板的如实计数; 语义在 manifest 由本函数 docstring 锚定)。"""
    merged: dict[date, list[int]] = {}
    for res in strategy_results:
        for entry in res["stats"]["per_date"]:
            d = date.fromisoformat(entry["date"])
            acc = merged.setdefault(d, [0, 0])
            acc[0] += entry["n_screened"]
            acc[1] += entry["n_hits"]
    return [
        {"date": d.isoformat(), "n_screened": acc[0], "n_hits": acc[1]}
        for d, acc in sorted(merged.items())
    ]


def _atomic_write_parquet(df: pl.DataFrame, out: Path) -> None:
    """先写临时文件再原子替换 — 逐字镜像 auction_sync.py:45-55 语义: .tmp 后缀不匹配
    *.parquet glob 不会被扫描误读; 同目录 rename 在 POSIX/NTFS 上均为原子操作。"""
    tmp = out.with_name(out.name + ".tmp")
    df.write_parquet(tmp)
    tmp.replace(out)


def _atomic_write_json(payload: dict, out: Path) -> None:
    """temp + os.replace 原子写 JSON — 镜像 pool_snapshot.py:103-106 语义。"""
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    os.replace(tmp, out)


def _build_manifest(
    *,
    run_id: str,
    strategy_version: str,
    created_at: str,
    window: dict,
    strategy_summaries: list[dict],
    params_snapshot: dict,
    coverage: dict,
    per_date: list[dict],
    fingerprint: str,
) -> dict:
    """manifest payload (镜像 RESEARCH §6 + pool_snapshot.py:91-101 惯例)。

    origin 固定 'research' (与 {eod,backfill,manual} 池词汇区分); minute_note 承载
    BT-10 分钟确认维度诚实受限说明; fingerprint = run 身份输入的确定性 json
    (与 _compute_run_id 输入同构 — 含 RC-01 lake_coverage digest 成员 —
    幂等跳过判据)。"""
    return {
        "run_id": run_id,
        "origin": _ORIGIN,
        "strategy_version": strategy_version,
        "created_at": created_at,
        "window": window,
        "strategies": strategy_summaries,
        "params": params_snapshot,
        "coverage": coverage,
        "per_date": per_date,
        "minute_note": _MINUTE_NOTE,
        "fingerprint": fingerprint,
    }


def _persist_run(
    data_dir: Path,
    run_id: str,
    rows_df: pl.DataFrame,
    manifest: dict,
) -> tuple[Path, bool, bool]:
    """原子持久化回测运行到 ``backtest_results/run_id={id}/`` (E2 写根隔离)。

    - 先 part.parquet 原子写, 再 manifest.json 原子写 (manifest 最后落 —
      存在 manifest 即视为运行完整);
    - 幂等: manifest 已存在且 fingerprint 与本次相同 → 跳过重写
      (wrote=False, reused=True, 原子无操作, 镜像 pool_backfill 分区差集语义);
    - 返回 (run_dir, wrote, reused)。"""
    run_dir = data_dir / _BACKTEST_ROOT / f"run_id={run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    part_path = run_dir / "part.parquet"
    manifest_path = run_dir / "manifest.json"

    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 损坏 manifest fail-open 重写 (诚实恢复)
            existing = {}
        if existing.get("fingerprint") == manifest["fingerprint"]:
            logger.info("backtest run %s reused (identical fingerprint)", run_id)
            return run_dir, False, True

    _atomic_write_parquet(rows_df, part_path)
    _atomic_write_json(manifest, manifest_path)
    logger.info("backtest run %s written (%d rows)", run_id, rows_df.height)
    return run_dir, True, False
