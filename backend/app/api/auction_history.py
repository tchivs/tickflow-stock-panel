"""竞价历史只读聚合 API (CHART-01)。

只读 ``GET /api/kline/auction/history`` (POOL-03: 零执行权限) —— 按 symbol 拉多日
集合竞价窗口末行 (09:25 最终撮合) 序列。本模块只暴露 GET 端点: 不写湖、不触发
同步/回填、不持久化任何计算、不 import 任何执行族模块。

空湖/该 symbol 无行 → 诚实 200 ``available:false`` 空态 (绝不 404/500/0 填充);
probe 非 available → 空态 + ``probe.status`` 透传; guest 会话 → 掩码空态
(量/价零泄露, D5)。任何 mutating 路由、写路径 pattern 或执行族 import 的引入
都会触发 ``tests/test_auction_history.py`` 的 POOL-03 AST 守卫 (T-26-01-03)。

严禁复制 kline.get_daily 的空库 live-fetch 兜底 (kline.py:159-181) —— 本端点
空湖必须 available:false 诚实返回, 绝不触发任何同步/回填/写路径。
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Request

from app.services.auction_probe import AuctionProbeStatus, resolve_auction_probe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kline/auction", tags=["kline"])

# 全限定 symbol 格式: 6 位数字 + 交易所后缀 (防非法输入进 SQL/文件系统扫描, T-26-01-02)
_SYMBOL_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")

# 窗口标签文案 (与 auction_probe.py:23-24 / auction_sync.py:29-30 同语义, 此处仅标签不复算分钟)
_WINDOW_LABEL = "09:15-09:25"

# 响应单位标注 (诚实声明量/价单位, 供前端轴标签)
_UNIT = {"auction_volume": "股", "auction_amount": "元"}

# 可选委托量输入列 (与 auction_sync.OPTIONAL_AUCTION_COLS 逐字一致, CHART-03) ——
# 源提供才透传, 诚实缺列不 0 填; 派生 auction_unmatched_amount 由读路径在输入可得时计算。
_OPTIONAL_COLS = ("auction_unmatched_volume", "auction_virtual_price")


def _empty_response(symbol, name, probe_dict, mode: str) -> dict:
    """诚实空态骨架 (200 available:false, 绝不 404/500/0 填充)。"""
    return {
        "symbol": symbol,
        "name": name,
        "available": False,
        "probe": probe_dict,
        "mode": mode,
        "coverage": 0,
        "window": _WINDOW_LABEL,
        "rows": [],
        "unit": _UNIT,
    }


def _dir_date(part_dir) -> date | None:
    """从 ``date=YYYY-MM-DD`` 分区目录名解析日期; 解析失败返回 None (跳过该分区)。"""
    name = part_dir.parent.name
    if not name.startswith("date="):
        return None
    try:
        return date.fromisoformat(name[len("date="):])
    except ValueError:
        return None


@router.get("/history")
def get_auction_history(
    request: Request,
    symbol: str = Query(..., description="标的代码,如 000001.SZ"),
    days: int = Query(120, description="回看自然日数 (1..120)"),
):
    """按 symbol 拉多日竞价窗口末行聚合序列 (只读, POOL-03 零执行)。

    - ``symbol`` 严格正则校验 (``^\\d{6}\\.(SH|SZ|BJ)$``) → 非法 400 (防注入/路径穿越)。
    - ``days`` 在 handler 内显式判 1..120 → 越界 400 (非 FastAPI Query ge/le 的 422, R2)。
    - guest (无 ``request.state.reviewer_principal``) → 200 掩码空态 (量/价零泄露, D5)。
    - probe 非 available → 200 诚实空态 + ``probe.status`` 透传。
    - 湖空 / 该 symbol 无行 → 200 诚实空态 (绝不 0 填充/绝不触发同步)。
    - 聚合: 每交易日取窗口末行 (datetime 降序首行 = 09:25 最终撮合, 镜像
      auction_columns.py:146 的 keep="last"), 附带 row_count/min_datetime/max_datetime
      粒度标注; rows 按 date 升序。
    """
    if not _SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(status_code=400, detail="invalid symbol")
    if not (1 <= days <= 120):
        raise HTTPException(status_code=400, detail="invalid days")

    repo = request.app.state.repo
    probe = resolve_auction_probe()
    probe_dict = probe.to_dict()

    # D5 guest 掩码 (镜像 pool.py:109-112): 无 reviewer_principal → 空态, 量/价零泄露
    is_vip = getattr(request.state, "reviewer_principal", None) is not None
    if not is_vip:
        return _empty_response(symbol, None, probe_dict, mode="guest")

    # 第一闸门: probe 必须 available (镜像 auction_columns.py:93-107)
    if probe.status != AuctionProbeStatus.available:
        return _empty_response(symbol, None, probe_dict, mode="vip")

    # 名称 (内联同名查询, 不 import kline._get_stock_info —— 避免拉入 kline_sync 等
    # 写路径相邻 import 触发 POOL-03 AST 守卫)。名称只是富化字段, 查询失败不阻断主数据。
    name = None
    try:
        row = repo.execute_one(
            "SELECT name FROM instruments WHERE symbol = ? LIMIT 1",
            [symbol],
        )
        if row:
            name = row[0]
    except Exception:  # noqa: BLE001
        logger.debug("auction_history: instruments name lookup failed for %s", symbol)

    # 第二闸门: 湖根目录存在 (镜像 auction_columns.py:112-120)
    base = repo.store.data_dir / "kline_auction"
    if not base.is_dir():
        return _empty_response(symbol, name, probe_dict, mode="vip")

    start = date.today() - timedelta(days=days)

    # 分区扫描 (纯读; 与 repository.py:162-163 kline_auction 视图同源同过滤语义)。
    # 日期解析失败 / 读盘异常 / 缺 symbol 或 datetime 列的异常分区跳过 (诚实缺列)。
    frames: list[pl.DataFrame] = []
    for part in base.glob("date=*/part.parquet"):
        d = _dir_date(part)
        if d is None or d < start:
            continue
        try:
            df = pl.read_parquet(part)
        except Exception:  # noqa: BLE001
            continue
        if "symbol" not in df.columns or "datetime" not in df.columns:
            continue
        df = df.filter(pl.col("symbol") == symbol)
        if not df.is_empty():
            frames.append(df)

    if not frames:
        return _empty_response(symbol, name, probe_dict, mode="vip")

    # 新旧分区 schema 可能不同 (4 列旧 / 6 列新) → diagonal_relaxed 并集 (R7);
    # 再按 (symbol, datetime) 去重 (镜像写路径 merge-upsert 语义), 防同日重复分区 inflate row_count。
    frame = pl.concat(frames, how="diagonal_relaxed").unique(
        subset=["symbol", "datetime"], keep="last",
    )

    # D1 末行语义 (镜像 auction_columns.py:146 keep="last"): 每 date 取 datetime 末行 = 09:25
    frame = frame.with_columns(pl.col("datetime").dt.date().alias("_date"))
    last_rows = frame.sort(["symbol", "_date", "datetime"]).unique(
        subset=["symbol", "_date"], keep="last",
    )
    agg = frame.group_by(["symbol", "_date"]).agg(
        pl.len().alias("row_count"),
        pl.col("datetime").min().alias("min_datetime"),
        pl.col("datetime").max().alias("max_datetime"),
    )
    merged = last_rows.join(agg, on=["symbol", "_date"], how="left").sort("_date")

    rows = []
    for r in merged.to_dicts():
        row = {
            "date": str(r["_date"]),
            "datetime": r["datetime"].isoformat(),
            "auction_volume": r.get("auction_volume"),
            "auction_amount": r.get("auction_amount"),
            "row_count": r["row_count"],
            "min_datetime": r["min_datetime"].isoformat(),
            "max_datetime": r["max_datetime"].isoformat(),
        }
        # 可选列仅当在合并帧时透传 (诚实缺列不 0 填)
        for col in _OPTIONAL_COLS:
            if col in merged.columns:
                row[col] = r.get(col)
        rows.append(row)

    return {
        "symbol": symbol,
        "name": name,
        "available": True,
        "probe": probe_dict,
        "mode": "vip",
        "coverage": len(rows),
        "window": _WINDOW_LABEL,
        "rows": rows,
        "unit": _UNIT,
    }
