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
    probe_status = verdict.get("status") if isinstance(verdict, dict) else "unknown"

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

    blocks: dict[str, Any] = {}

    # Block 2: 恒在块 (enriched 可得时)
    blocks["open_gap_snapshot"] = _build_open_gap_snapshot(repo, as_of, enriched_df)

    # Block 1 (real_auction_activity) / Block 3 (preopen_signal_quality):
    # 由后续任务装配 (Task 2/3); 头标签已诚实反映其缺席。

    # 头标签判别 (RESEARCH §4: pre_eod > no_auction_lake > no_premarket_preview > partial > full)
    label = "partial"
    if pre_eod:
        label = "pre_eod"
    elif not partition_exists or (as_of == today and probe_status != "available"):
        label = "no_auction_lake"
    else:
        preview = load_premarket_snapshot(repo.store.data_dir, as_of.isoformat())
        if preview is None:
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
