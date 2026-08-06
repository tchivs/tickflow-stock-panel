"""竞价复盘确定性装配服务 (REV-01/02/03, POOL-03 零执行, D-01)。

把三类冻结资产只读装配为确定性竞价复盘面板 dict (非 AI 生成):
  - kline_auction 湖分区: 真实竞价列 (Block 1 real_auction_activity);
  - premarket_results 盘前预览: 信号命中行 (Block 3 preopen_signal_quality);
  - enriched 读时计算: open_gap / change_pct 即时派生, 非存储列 (Block 2
    open_gap_snapshot + Block 3 EOD 口径 join)。

铁律 (镜像 premarket_pool.py:1-18 只读契约, 供 31-03 AST 守卫):
- 绝不触发任何批量执行 / 预设运行触发面; 绝不调运行期缓存写回、点快照
  持久化、报告落盘等一切写面; 绝不写任何文件 (含竞价湖 / 选股结果湖 /
  盘前结果湖 / 归档)。
- 绝不 import 执行族模块与单 as_of 运行期缓存指针模块 (平台一致性 E1/E3 形)。
- 历史 as_of 主闸门 = 竞价湖分区存在性 (probe 仅 provenance 透传, 不参与
  历史闸门); 今日 as_of 走 probe×分区双闸门 (镜像 attach_auction_columns)。
- 缺失数据诚实省略: data_completeness 单头标签按优先级取值, 逐块显式
  note/source, 绝不 0 填; 返回 dict 全 JSON 可序列化 (NaN/Inf → None)。

零新增运行时依赖 (stdlib + polars + 既有只读服务模块)。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from app.market_time import cn_now
from app.services.auction_columns import attach_auction_columns_range
from app.services.auction_probe import resolve_auction_probe
from app.services.auction_validation import _AUCTION_FAMILY_IDS
from app.services.premarket_snapshot import load_premarket_snapshot
from app.services.screener import ScreenerService, _strategy_display_name

logger = logging.getLogger(__name__)

# data_completeness 单头标签枚举 (RESEARCH §4 优先级: pre_eod > no_auction_lake >
# no_premarket_preview > partial > full)
_DATA_COMPLETENESS_VALUES = ("full", "no_auction_lake", "no_premarket_preview", "pre_eod", "partial")

# 集合竞价匹配数据窗口分钟数: [09:15:00, 09:25:59] (镜像 auction_probe :19-24)
_AUCTION_WINDOW_START_MIN = 555
_AUCTION_WINDOW_END_MIN = 565

# 中文注记常量 (REV-02/03 诚实缺项词汇)
_SIGNAL_NOTE_PRE_EOD = "盘后竞价同步未完成,建议 15:35 后重跑"
_SIGNAL_NOTE_NO_LAKE = "当日无竞价湖数据"
_SIGNAL_NOTE_EOD_PENDING = "EOD 收盘兑现率待盘后管道完成后更新"
_SIGNAL_NOTE_DEGRADED = "盘前信号基于派生因子(非真实竞价数据)"
_SIGNAL_NOTE_DISPLAY_LIMIT = "基于展示行(display_limit 截断)"
_SIGNAL_NOTE_PREVIEW_ABSENT = "当日无盘前预览(no_premarket_preview)"
_SIGNAL_NOTE_RATIO_UNAVAILABLE = "历史量能分母不可得"

_SOURCE_KLINE_AUCTION = "kline_auction"
_SOURCE_ENRICHED = "kline_daily_enriched(open_gap 读时计算)"
_SOURCE_PREVIEW = "premarket_results"
_SOURCE_PREVIEW_EOD = "premarket_results + kline_daily_enriched(EOD 口径)"


def _json_safe(value: Any) -> Any:
    """递归 JSON 消毒: float NaN/Inf → None (镜像 screener._json_safe, 无 math 依赖)。"""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _fmt_num(v) -> str:
    """数值格式化 (None → 占位符, 诚实缺项)。"""
    if v is None:
        return "—"
    return f"{v:.4f}"


def _fmt_pct(v) -> str:
    """比例格式化 (None → 占位符; 0.75 → 75.0%)。"""
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


def _is_present(blk: Any) -> bool:
    return isinstance(blk, dict) and blk.get("present") is True


# ================================================================
# Block 2 — 开盘涨幅快照 (恒在块, 唯一恒真档)
# ================================================================


def _build_open_gap_snapshot(repo, as_of: date, enriched_df) -> dict:
    """Block 2 装配 (REV-02): 高开分布 / 均值 / Top N, 源 = enriched 读时计算。

    open_gap 非存储列, 一律经 ``_load_enriched_for_date`` 计算入口取得;
    帧缺失 / 列缺失 → present:false + 显式注记 (防御分支, 不入枚举专名)。
    """
    if enriched_df is None or enriched_df.is_empty() or "open_gap" not in enriched_df.columns:
        return {
            "present": False,
            "note": "当日 enriched 数据缺失, 开盘涨幅快照暂不可用",
            "source": _SOURCE_ENRICHED,
        }
    try:
        gaps = enriched_df.select(
            [c for c in ("symbol", "open_gap", "name") if c in enriched_df.columns]
        ).drop_nulls("open_gap")
        if gaps.is_empty():
            return {
                "present": False,
                "note": "当日 enriched 数据缺失, 开盘涨幅快照暂不可用",
                "source": _SOURCE_ENRICHED,
            }
        n = gaps.height
        ge2 = gaps.filter(pl.col("open_gap") >= 0.02)
        ge5 = gaps.filter(pl.col("open_gap") >= 0.05)
        mean = gaps["open_gap"].mean()

        top_n = []
        for row in gaps.sort("open_gap", descending=True).head(10).iter_rows(named=True):
            top_n.append({
                "symbol": row["symbol"],
                "name": row.get("name") or row["symbol"],
                "open_gap": float(row["open_gap"]),
            })
        return {
            "present": True,
            "source": _SOURCE_ENRICHED,
            "note": "open_gap 基于 enriched 复权口径",
            "distribution": {
                "ge2_count": int(ge2.height),
                "ge2_pct": float(ge2.height) / n,
                "ge5_count": int(ge5.height),
                "ge5_pct": float(ge5.height) / n,
            },
            "high_open_count": int(ge2.height),
            "mean_open_gap": None if mean is None else float(mean),
            "top_n": top_n,
        }
    except Exception as e:  # noqa: BLE001 — per-block fail-closed (T-31-01-04)
        logger.warning("open_gap_snapshot failed for %s: %s", as_of, e)
        return {
            "present": False,
            "note": "开盘涨幅快照装配失败",
            "source": _SOURCE_ENRICHED,
        }


# ================================================================
# Block 1 — 真实竞价活跃度 (条件式: 湖有数据才亮)
# ================================================================


def _name_map(repo, symbols: list[str]) -> dict:
    """symbol → name (instruments 表; 缺则退 symbol, 诚实)。"""
    try:
        inst = repo.get_instruments_asset("stock")
    except Exception:  # noqa: BLE001 — fail-closed, 退 symbol
        inst = pl.DataFrame()
    names: dict[str, str] = {}
    if not inst.is_empty() and "symbol" in inst.columns and "name" in inst.columns:
        for row in inst.select(["symbol", "name"]).iter_rows(named=True):
            names[row["symbol"]] = row["name"]
    return names


def _build_real_auction_activity(repo, as_of: date, probe_verdict: dict, now, pre_eod: bool) -> dict:
    """Block 1 装配 (REV-01): 湖分区读 + 窗口谓词回归锁 + keep='last' 去重。

    闸门 (按 as_of 分治): 今日 → probe×分区双闸门 (镜像 attach_auction_columns
    :95-121); 历史 → 分区存在性主闸门 (probe 不参与, 镜像
    attach_auction_columns_range :178-182)。读盘异常/空分区/缺列 → fail-closed
    空块 (绝不冒泡 500, T-31-01-04)。
    """
    today = now.date()
    probe_status = probe_verdict.get("status") if isinstance(probe_verdict, dict) else "unknown"
    part = repo.store.data_dir / "kline_auction" / f"date={as_of.isoformat()}" / "part.parquet"

    def _empty(note: str) -> dict:
        blk = {"present": False, "note": note, "source": _SOURCE_KLINE_AUCTION}
        if as_of == today:
            blk["probe"] = probe_verdict
        return blk

    if pre_eod:
        return _empty(_SIGNAL_NOTE_PRE_EOD)
    if not part.exists():
        return _empty(_SIGNAL_NOTE_NO_LAKE)
    if as_of == today and probe_status != "available":
        return _empty(_SIGNAL_NOTE_NO_LAKE)

    try:
        df = pl.read_parquet(part)
    except Exception as e:  # noqa: BLE001 — fail-closed
        logger.warning("real_auction_activity: unreadable partition %s: %s", part, e)
        return _empty(_SIGNAL_NOTE_NO_LAKE)

    if df.is_empty() or "symbol" not in df.columns:
        return _empty(_SIGNAL_NOTE_NO_LAKE)

    # 读侧窗口谓词 (REV-02 回归锁, 防御纵深): [09:15:00, 09:25:59] 分钟粒度
    # (镜像 auction_probe._has_in_window_rows; 缺 datetime 列 → 整帧按窗口外处理)
    if "datetime" not in df.columns:
        return _empty(_SIGNAL_NOTE_NO_LAKE)
    try:
        dt = pl.col("datetime").cast(pl.Datetime("us"), strict=False)
        minutes = dt.dt.hour().cast(pl.Int32) * 60 + dt.dt.minute().cast(pl.Int32)
        df = df.filter(
            (minutes >= _AUCTION_WINDOW_START_MIN) & (minutes <= _AUCTION_WINDOW_END_MIN)
        )
    except Exception as e:  # noqa: BLE001 — fail-closed
        logger.warning("real_auction_activity: window predicate failed for %s: %s", as_of, e)
        return _empty(_SIGNAL_NOTE_NO_LAKE)

    if df.is_empty():
        return _empty(_SIGNAL_NOTE_NO_LAKE)

    # 09:25 最终撮合: 每 symbol 单行 (镜像 auction_columns.py:146)
    df = df.unique(subset=["symbol"], keep="last")

    n_symbols = df.height
    total_amount = None
    if "auction_amount" in df.columns:
        total_amount = float(df["auction_amount"].sum())
        if total_amount != total_amount or total_amount in (float("inf"), float("-inf")):
            total_amount = None

    name_map = _name_map(repo, df["symbol"].to_list())

    top_n: list[dict] = []
    if "auction_amount" in df.columns:
        for row in df.sort("auction_amount", descending=True).head(10).iter_rows(named=True):
            entry = {
                "symbol": row["symbol"],
                "name": name_map.get(row["symbol"], row["symbol"]),
                "auction_amount": float(row["auction_amount"]),
            }
            top_n.append(entry)
    # 委托量派生列计入行 (有列才计, 不求和)
    if "auction_unmatched_amount" in df.columns and top_n:
        by_sym = dict(zip(df["symbol"].to_list(), df["auction_unmatched_amount"].to_list()))
        for t in top_n:
            v = by_sym.get(t["symbol"])
            if v is not None:
                t["auction_unmatched_amount"] = float(v)

    blk = {
        "present": True,
        "source": _SOURCE_KLINE_AUCTION,
        "note": "真实竞价列(09:15-09:25 窗口末行)",
        "n_symbols": n_symbols,
        "total_amount": total_amount,
        "top_n": top_n,
        "ratio_subblock": _build_ratio_subblock(repo, as_of, top_n),
    }
    if as_of == today:
        blk["probe"] = probe_verdict
    return blk


def _build_ratio_subblock(repo, as_of: date, top_n: list[dict]) -> dict:
    """竞价量比子块 (R11 优先路径: 复用 attach_auction_columns_range, 零新 ratio 代码)。

    分母 = as_of 前 5 个交易日 volume 均值 (PIT-safe, 不含当日); 分母不可得 →
    子块省略 + 注记, 绝不 0 填。
    """
    try:
        window_start = as_of - timedelta(days=9)  # ≥6 交易日
        panel = repo.get_enriched_range(window_start, as_of)
        if panel is None or panel.is_empty():
            return {"present": False, "note": _SIGNAL_NOTE_RATIO_UNAVAILABLE, "values": {}}
        injected, _enabled = attach_auction_columns_range(panel, as_of, as_of, repo)
        if "auction_volume_ratio" not in injected.columns:
            return {"present": False, "note": _SIGNAL_NOTE_RATIO_UNAVAILABLE, "values": {}}
        ratio_by_symbol: dict[str, float | None] = {}
        for row in injected.filter(pl.col("date") == as_of).iter_rows(named=True):
            v = row.get("auction_volume_ratio")
            if v is not None:
                ratio_by_symbol[row["symbol"]] = float(v)
        # 并入 top_n 行 (缺失 symbol → 该行无 ratio 键, 诚实)
        for t in top_n:
            if t["symbol"] in ratio_by_symbol:
                t["auction_volume_ratio"] = ratio_by_symbol[t["symbol"]]
        if not ratio_by_symbol:
            return {"present": False, "note": _SIGNAL_NOTE_RATIO_UNAVAILABLE, "values": {}}
        return {"present": True, "note": "竞价量 ÷ 前 5 日均量 (PIT-safe)", "values": ratio_by_symbol}
    except Exception as e:  # noqa: BLE001 — per-block fail-closed (T-31-01-04)
        logger.warning("ratio_subblock failed for %s: %s", as_of, e)
        return {"present": False, "note": _SIGNAL_NOTE_RATIO_UNAVAILABLE, "values": {}}


# ================================================================
# Block 3 — 盘前信号质量 (条件式: 预览在才亮)
# ================================================================


def _mean(values: list[float]) -> float | None:
    """均值 (无有效值 → None, 诚实 null 绝不 0 填, 镜像 auction_validation._null_metric)。"""
    if not values:
        return None
    return sum(values) / len(values)


def _build_preopen_signal_quality(
    repo,
    as_of: date,
    engine,
    now: datetime,
    preview,
    enriched_df,
) -> dict:
    """Block 3 装配 (REV-03): 族∩预览策略集 + EOD 口径 join + n_missing + resonance。

    - 策略集 = ``_AUCTION_FAMILY_IDS`` (单一事实源) ∩ 预览 results keys,
      只含预览里实际有行的竞价族策略。
    - EOD 口径 join (R6 铁律): 收盘兑现率/收阳率一律按 symbol 左联 EOD enriched
      帧的 change_pct/close/open; 预览行有而 EOD 帧缺行 → n_missing 计数,
      该行不进率统计 (绝不 0 填/前向填充)。
    - 前 EOD 时刻 (as_of==today ∧ now < 管道调度): change_pct 系统计省略 +
      注记, open_gap 系统计照常 (open 已定盘)。
    """
    if preview is None:
        return {"present": False, "note": _SIGNAL_NOTE_PREVIEW_ABSENT, "source": _SOURCE_PREVIEW}
    results = preview.get("results") or {}
    if not results:
        return {"present": False, "note": _SIGNAL_NOTE_PREVIEW_ABSENT, "source": _SOURCE_PREVIEW}
    if enriched_df is None or enriched_df.is_empty():
        return {"present": False, "note": "EOD 口径不可得", "source": _SOURCE_PREVIEW_EOD}

    # EOD 口径帧 (与 Block 2 同帧复用, 单次装载)
    eod_cols = [c for c in ("symbol", "change_pct", "close", "open") if c in enriched_df.columns]
    eod_map: dict[str, dict] = {}
    for row in enriched_df.select(eod_cols).iter_rows(named=True):
        eod_map[row["symbol"]] = row

    # 前 EOD 时刻判别: as_of==today ∧ now < 管道调度 (change_pct 非终值)
    today = now.date()
    pre_eod_time = False
    if as_of == today:
        from app.services.preferences import get_pipeline_schedule

        sched = get_pipeline_schedule()
        pre_eod_time = (now.hour * 60 + now.minute) < (sched["hour"] * 60 + sched["minute"])

    family = _AUCTION_FAMILY_IDS
    strategies: dict[str, dict] = {}
    n_missing_total = 0

    for sid, item in results.items():
        if sid not in family:
            continue
        rows = (item or {}).get("rows") or []
        if not rows:
            continue
        total = (item or {}).get("total", len(rows))
        display_limited = total > len(rows)

        gaps: list[float] = []
        fulf: list[bool] = []
        chgs: list[float] = []
        close_fulf: list[bool] = []
        ups: list[bool] = []
        missing = 0
        for row in rows:
            gap = row.get("open_gap")
            if isinstance(gap, (int, float)):
                gaps.append(float(gap))
                fulf.append(gap >= 0.02)
            eod = eod_map.get(row["symbol"])
            if eod is None:
                missing += 1
                continue
            c = eod.get("change_pct")
            if isinstance(c, (int, float)):
                chgs.append(float(c))
                close_fulf.append(c >= 0.02)
            if isinstance(eod.get("close"), (int, float)) and isinstance(eod.get("open"), (int, float)):
                ups.append(eod["close"] > eod["open"])
        n_missing_total += missing

        st: dict[str, Any] = {
            "display_name": _strategy_display_name(engine, sid),
            "n": len(rows),
            "avg_open_gap": _mean(gaps),
            "open_gap_fulfill_rate": (sum(fulf) / len(fulf)) if fulf else None,
            "n_missing": missing,
        }
        if display_limited:
            st["note"] = _SIGNAL_NOTE_DISPLAY_LIMIT
        if not pre_eod_time:
            st["avg_change_pct"] = _mean(chgs)
            st["close_fulfill_rate"] = (sum(close_fulf) / len(close_fulf)) if close_fulf else None
            st["up_rate"] = (sum(ups) / len(ups)) if ups else None
        strategies[sid] = st

    block_notes: list[str] = []
    if pre_eod_time:
        block_notes.append(_SIGNAL_NOTE_EOD_PENDING)
    degraded = bool(preview.get("degraded"))
    if degraded:
        block_notes.append(_SIGNAL_NOTE_DEGRADED)

    blk: dict[str, Any] = {
        "present": True,
        "source": _SOURCE_PREVIEW_EOD,
        "note": "基于盘前预览·非收盘定稿",
        "provisional": bool(preview.get("provisional", True)),
        "degraded": degraded,
        "n_missing": n_missing_total,
        "notes": block_notes,
        "strategies": strategies,
    }

    # 交叉共振子块: 预览全行 hit_factors >= 2 的标的聚合同一组兑现率
    resonance = _build_resonance(results, eod_map, pre_eod_time)
    if resonance is not None:
        blk["resonance"] = resonance
    return blk


def _build_resonance(results: dict, eod_map: dict, pre_eod_time: bool) -> dict | None:
    """交叉共振子块 (只读复用预览行自带 hit_factors; 无共振标的 → 省略)。"""
    seen: dict[str, dict] = {}
    resonance_syms: list[str] = []
    for item in results.values():
        for row in (item or {}).get("rows") or []:
            sym = row.get("symbol")
            if not sym or sym in seen:
                continue
            seen[sym] = row
            if isinstance(row.get("hit_factors"), list) and len(row["hit_factors"]) >= 2:
                resonance_syms.append(sym)
    if not resonance_syms:
        return None

    gaps: list[float] = []
    fulf: list[bool] = []
    chgs: list[float] = []
    close_fulf: list[bool] = []
    ups: list[bool] = []
    for sym in resonance_syms:
        row = seen[sym]
        gap = row.get("open_gap")
        if isinstance(gap, (int, float)):
            gaps.append(float(gap))
            fulf.append(gap >= 0.02)
        eod = eod_map.get(sym)
        if eod is None:
            continue
        c = eod.get("change_pct")
        if isinstance(c, (int, float)):
            chgs.append(float(c))
            close_fulf.append(c >= 0.02)
        if isinstance(eod.get("close"), (int, float)) and isinstance(eod.get("open"), (int, float)):
            ups.append(eod["close"] > eod["open"])

    sub: dict[str, Any] = {
        "present": True,
        "note": "hit_factors≥2 的交叉共振标的",
        "n_symbols": len(resonance_syms),
        "avg_open_gap": _mean(gaps),
        "open_gap_fulfill_rate": (sum(fulf) / len(fulf)) if fulf else None,
    }
    if not pre_eod_time:
        sub["avg_change_pct"] = _mean(chgs)
        sub["close_fulfill_rate"] = (sum(close_fulf) / len(close_fulf)) if close_fulf else None
        sub["up_rate"] = (sum(ups) / len(ups)) if ups else None
    return sub


# ================================================================
# 装配主入口
# ================================================================


def build_auction_recap(
    repo,
    as_of: date,
    engine=None,
    *,
    probe_resolver=None,
    now=None,
) -> dict:
    """构造确定性竞价复盘面板 dict (REV-01/02/03, 纯只读, 不写盘)。

    - ``as_of`` 单一来源由调用方传入 (recap 场景 = overview['as_of'], REV-05
      端点 = query 或 ScreenerService.latest_date()), 服务内绝不复解析。
    - 历史 as_of (< today) 主闸门 = ``kline_auction/date={as_of}/part.parquet``
      分区存在性 (probe 不参与, 镜像 attach_auction_columns_range :178-182);
      今日 as_of (== now.date()) → probe×分区双闸门 (镜像 attach_auction_columns
      :95-121)。
    - data_completeness 单头标签按 RESEARCH §4 优先级取值
      (pre_eod > no_auction_lake > no_premarket_preview > partial > full);
      缺失块在 blocks 中带 ``{present: false, note, source}`` 显式注记。
    - probe 经 ``probe_resolver`` 注入点解析一次仅透传 provenance
      (镜像 premarket_pool :47-56); ``now`` 冻结墙钟供 pre_eod 判别测试。

    Returns:
        ``{as_of, data_completeness, blocks, built_at}`` 全 JSON 可序列化。
    """
    now = now or cn_now()
    today = now.date()
    probe_resolver = probe_resolver or resolve_auction_probe

    # probe 解析一次, 仅透传 provenance (今日闸门参与; 历史闸门不参与)
    probe = probe_resolver()
    verdict = probe.to_dict() if hasattr(probe, "to_dict") else probe

    # 湖分区存在性 (主闸门, 镜像 auction_columns.py:107)
    part = repo.store.data_dir / "kline_auction" / f"date={as_of.isoformat()}" / "part.parquet"
    partition_exists = part.exists()

    # pre_eod 判别 (W-2: 分钟算术, 绝不比较 tz-aware time 与 naive time)
    pre_eod = False
    if as_of == today and not partition_exists:
        from app.services.preferences import get_pipeline_schedule

        sched = get_pipeline_schedule()
        pre_eod = (now.hour * 60 + now.minute) < (sched["hour"] * 60 + sched["minute"])

    # enriched 帧单次装载 (Block 2 快照 + Block 3 EOD 口径 join 同帧复用)
    enriched_df = None
    try:
        enriched_df = ScreenerService(repo)._load_enriched_for_date(as_of)
    except Exception as e:  # noqa: BLE001 — per-block fail-closed (T-31-01-04)
        logger.warning("enriched load failed for %s: %s", as_of, e)

    # 盘前预览单次装载 (头标签判别 + Block 3 装配共用, 只读)
    preview = load_premarket_snapshot(repo.store.data_dir, as_of.isoformat())

    blocks: dict[str, Any] = {}

    # Block 2: 恒在块 (enriched 可得时)
    blocks["open_gap_snapshot"] = _build_open_gap_snapshot(repo, as_of, enriched_df)

    # Block 1: 真实竞价活跃度 (今日 probe×分区双闸门 / 历史分区存在性主闸门)
    blocks["real_auction_activity"] = _build_real_auction_activity(
        repo, as_of, verdict, now, pre_eod,
    )

    # Block 3: 盘前信号质量 (族∩预览 + EOD 口径 join; 预览缺失 → 块省略)
    blocks["preopen_signal_quality"] = _build_preopen_signal_quality(
        repo, as_of, engine, now, preview, enriched_df,
    )

    # 头标签判别 (RESEARCH §4: pre_eod > no_auction_lake > no_premarket_preview > partial > full)
    lake_ok = _is_present(blocks["real_auction_activity"])
    label = "partial"
    if pre_eod:
        label = "pre_eod"
    elif not lake_ok:
        # 分区缺失 / 今日 probe 非 available / 窗口内零行 → 湖无真值, 诚实降级
        label = "no_auction_lake"
    elif preview is None:
        label = "no_premarket_preview"
    else:
        all_present = all(_is_present(b) for b in blocks.values())
        label = "full" if all_present else "partial"

    return _json_safe({
        "as_of": as_of.isoformat(),
        "data_completeness": label,
        "blocks": blocks,
        "built_at": now.isoformat(),
    })


# ================================================================
# 渲染纯函数 (dict → markdown, REV-02 验收 3)
# ================================================================


def _render_open_gap_snapshot(blk: dict) -> list[str]:
    """开盘涨幅快照小节 (分布 bullet + Top N bullet)。"""
    dist = blk.get("distribution") or {}
    lines = [
        "### 开盘涨幅快照",
        f"- 高开分布: ≥2% {dist.get('ge2_count', 0)} 家 ({_fmt_pct(dist.get('ge2_pct'))}), "
        f"≥5% {dist.get('ge5_count', 0)} 家 ({_fmt_pct(dist.get('ge5_pct'))})",
        f"- 高开家数: {blk.get('high_open_count', 0)}",
        f"- 平均 open_gap: {_fmt_num(blk.get('mean_open_gap'))}",
    ]
    top = blk.get("top_n") or []
    if top:
        items = "、".join(
            f"{t.get('name') or t.get('symbol')}({_fmt_pct(t.get('open_gap'))})" for t in top[:10]
        )
        lines.append(f"- open_gap Top 10: {items}")
    if blk.get("note"):
        lines.append(f"- 注记: {blk['note']}")
    lines.append("")
    return lines


def render_auction_recap_markdown(panel: dict) -> str:
    """面板 dict → markdown 纯函数 (REV-02 验收 3, 确定性数据标识)。

    逐 present 块渲染小节; present:false 的块不渲染 (缺失理由已在 blocks
    note, 面板不重复); 输入任意缺块 panel 不抛 (纯函数, 无 repo 访问)。
    """
    lines = [
        "---",
        "## 📊 竞价复盘(确定性数据，非 AI 生成)",
        "",
        "> 数据来源:冻结资产(kline_auction 湖 / 盘前预览 / enriched)。本面板为确定性聚合, 非 AI 生成。",
        "",
    ]
    for name, blk in (panel.get("blocks") or {}).items():
        if not _is_present(blk):
            continue
        if name == "open_gap_snapshot":
            lines.extend(_render_open_gap_snapshot(blk))
        elif name == "real_auction_activity":
            lines.extend(_render_real_auction_activity(blk))
        elif name == "preopen_signal_quality":
            lines.extend(_render_preopen_signal_quality(blk))
    return "\n".join(lines)


def _render_real_auction_activity(blk: dict) -> list[str]:
    """真实竞价活跃度小节 (Task 2 装配后可用)。"""
    lines = [
        "### 真实竞价活跃度",
        f"- 竞价总额: {_fmt_num(blk.get('total_amount'))}",
        f"- 竞价标的总数: {blk.get('n_symbols', 0)} 家",
    ]
    top = blk.get("top_n") or []
    if top:
        items = "、".join(
            f"{t.get('name') or t.get('symbol')}({_fmt_num(t.get('auction_amount'))})" for t in top[:10]
        )
        lines.append(f"- 竞价金额 Top 10: {items}")
    ratio = blk.get("ratio_subblock") or {}
    if _is_present(ratio) and ratio.get("values"):
        vals = "、".join(f"{s}:{_fmt_num(v)}" for s, v in list(ratio["values"].items())[:10])
        lines.append(f"- 竞价量比: {vals}")
    elif isinstance(ratio, dict) and ratio.get("note"):
        lines.append(f"- 竞价量比: {ratio['note']}")
    if blk.get("note"):
        lines.append(f"- 注记: {blk['note']}")
    lines.append("")
    return lines


def _render_preopen_signal_quality(blk: dict) -> list[str]:
    """盘前信号质量小节 (Task 3 装配后可用)。"""
    lines = ["### 盘前信号质量"]
    header_note = blk.get("note") or "基于盘前预览·非收盘定稿"
    lines.append(f"> {header_note}")
    strategies = blk.get("strategies") or {}
    if strategies:
        lines.append("")
        lines.append("| 策略 | N | 平均 open_gap | 平均 change_pct(EOD) | 开盘兑现率 | 收盘兑现率 | 收阳率 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for sid, st in strategies.items():
            lines.append(
                f"| {st.get('display_name') or sid} | {st.get('n', 0)} | "
                f"{_fmt_num(st.get('avg_open_gap'))} | {_fmt_num(st.get('avg_change_pct'))} | "
                f"{_fmt_pct(st.get('open_gap_fulfill_rate'))} | "
                f"{_fmt_pct(st.get('close_fulfill_rate'))} | {_fmt_pct(st.get('up_rate'))} |"
            )
    if blk.get("n_missing"):
        lines.append(f"- 注记: {blk['n_missing']} 个标的预览有行但 EOD 帧缺失 (不填充)")
    for note in blk.get("notes") or []:
        lines.append(f"- 注记: {note}")
    lines.append("")
    return lines


def build_auction_slice(panel: dict) -> str:
    """面板 dict → LLM 精简切片 (REV-04 验收 6 构造性单源, 与 render 同一 dict)。

    缺失块显式声明 (护栏语义); 纯函数不访问 repo/engine, 返回非空 str。
    """
    lines = ["## 竞价复盘数据(确定性切片)"]
    for name, blk in (panel.get("blocks") or {}).items():
        if not _is_present(blk):
            lines.append(f"- 今日无竞价数据({name})")
            continue
        if name == "open_gap_snapshot":
            dist = blk.get("distribution") or {}
            lines.append(
                f"- 高开分布: ≥2% {dist.get('ge2_count', 0)} 家 ({_fmt_pct(dist.get('ge2_pct'))}), "
                f"≥5% {dist.get('ge5_count', 0)} 家 ({_fmt_pct(dist.get('ge5_pct'))}), "
                f"均值 {_fmt_num(blk.get('mean_open_gap'))}"
            )
        elif name == "preopen_signal_quality":
            for sid, st in (blk.get("strategies") or {}).items():
                lines.append(
                    f"- {sid}: N={st.get('n', 0)}, 平均open_gap={_fmt_num(st.get('avg_open_gap'))}, "
                    f"开盘兑现率={_fmt_pct(st.get('open_gap_fulfill_rate'))}"
                )
        elif name == "real_auction_activity":
            lines.append(
                f"- 竞价总额 {_fmt_num(blk.get('total_amount'))}, 标的 {blk.get('n_symbols', 0)} 家"
            )
    return "\n".join(lines)
