"""T-day 竞价提审升湖 (SDC-02)。

把 staging (43-01 采集产物) 中**仅 09:25 num_trades>0 撮合行**升 canonical
``kline_auction``; 虚拟快照行 (num_trades=0) 与 09:25:01 回显行永不入湖
(555..565 谓词 + 提审过滤双保险, Pitfall 2); 单位映射锁死 (手→股 ×100, Pitfall 7);
DATA-06 派生输入映射 — ``auction_virtual_price`` = 09:25 price, ``auction_unmatched_volume``
诚实缺列 (tick 源无未匹配量字段 → 绝不产出/绝不 0 填)。

提审闸门 (Pitfall 6): 当日 staging manifest ``completeness.ok`` ∧
``reconciliation.status == "closed"`` — 当日 staging 判定, **绝不用**
``resolve_auction_probe()`` (tick 源不在 probe 枚举, 复用恒不过); 闸门不过 →
0 写 + reason 显式返回, 绝不静默。

canonical 写面直调 ``auction_sync.write_auction_partitions`` (555..565 谓词 +
存在性 crop + merge-upsert 幂等 + 原子写; probe 闸门不在其内)。num_trades 只进
返回元数据 — canonical 无此列。
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

import polars as pl

from app.data_providers.stockdb_provider import _to_suffix  # 单一事实源 (SH600519→600519.SH)
from app.services.auction_sync import write_auction_partitions
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)

# 撮合行窗口谓词 (提审过滤): 09:25:00..09:25:59 且 num_trades>0; 555..565 分钟窗口
# 由 write_auction_partitions 双重保证 (09:25 → 565 ∈ [555, 565])。
_MATCH_TIME_LO = "09:25:00"
_MATCH_TIME_HI = "09:25:59"

# 单位映射: 手 → 股 ×100 (data.py:772 语义; 契约 173×100=17300 股 / 173×100×1308.66=22,639,818 元)
_HAND_TO_SHARE = 100


def promote_to_canonical(
    stage_dir: Path,
    repo: KlineRepository,
    trade_date: date,
    tol: float = 1e-6,
) -> dict:
    """单日提审: 仅 09:25 num_trades>0 撮合行升 canonical (SDC-02)。

    Args:
        stage_dir: ``data/tick_staging/date={T}`` 分区目录 (part.parquet + manifest.json)。
        repo: KlineRepository (写面走 ``write_auction_partitions`` 单一路径)。
        trade_date: 当日 T。
        tol: 保留占位 (plan 锁形签名); promote 映射为精确乘法, 无容差比较 — 容差
            用于 ``cross_validate_virtual_price``。

    Returns:
        fail-closed 时 ``{"written": 0, "reason": <原因>}`` (manifest_missing /
        capture_incomplete / reconciliation_not_closed / staging_missing /
        no_match_rows); 成功时 ``{"written": int, "symbols": […],
        "num_trades_by_symbol": {sym: num_trades}}`` — num_trades 只进元数据,
        canonical 无此列。
    """
    del tol  # 占位参数 (签名契约), promote 面无浮点比较

    # ---- gate (Pitfall 6): 当日 staging manifest 判定, fail-closed, 绝不用 xyz probe ----
    manifest_path = stage_dir / "manifest.json"
    if not manifest_path.exists():
        return {"written": 0, "reason": "manifest_missing"}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("promote: manifest unreadable, fail-closed: %s", e)
        return {"written": 0, "reason": "manifest_unreadable"}
    if (manifest.get("completeness") or {}).get("ok") is not True:
        return {"written": 0, "reason": "capture_incomplete"}
    if (manifest.get("reconciliation") or {}).get("status") != "closed":
        return {"written": 0, "reason": "reconciliation_not_closed"}

    # ---- 读 staging 分区 (43-01 契约: 10 列) ----
    part_path = stage_dir / "part.parquet"
    if not part_path.exists():
        return {"written": 0, "reason": "staging_missing"}
    staging = pl.read_parquet(part_path)
    required = {"symbol", "time", "price", "vol_hand", "num_trades"}
    missing = required - set(staging.columns)
    if missing:
        logger.warning("promote: staging 缺列 %s, fail-closed", sorted(missing))
        return {"written": 0, "reason": "staging_schema"}

    # ---- 撮合行过滤: 09:25:00..09:25:59 ∧ num_trades>0 → sort(time) → 单 symbol 单日单行 ----
    match = staging.filter(
        (pl.col("time") >= _MATCH_TIME_LO)
        & (pl.col("time") <= _MATCH_TIME_HI)
        & (pl.col("num_trades") > 0)
    ).sort("time")
    if match.is_empty():
        return {"written": 0, "reason": "no_match_rows"}
    # unique(subset=["symbol"], keep="first") — RESEARCH 骨架的 unique(["symbol","time"])
    # 会保留 09:25:00+09:25:04 两行 → 单 symbol 双 canonical 行, 破坏「一 symbol 一撮合行」
    # 不变量; 以本计划为准 (plan > research 骨架)。
    match = match.unique(subset=["symbol"], keep="first")

    # ---- 单位映射 (手→股 ×100; 元 = price×vol_hand×100; virtual_price = price) ----
    rows: list[dict] = []
    num_trades_by_symbol: dict[str, int] = {}
    for rec in match.iter_rows(named=True):
        sym = _to_suffix(str(rec["symbol"]))
        vol_hand = int(rec["vol_hand"])
        price = float(rec["price"])
        rows.append({
            "symbol": sym,
            "datetime": datetime(trade_date.year, trade_date.month, trade_date.day, 9, 25, 0),
            "auction_volume": vol_hand * _HAND_TO_SHARE,          # 股
            "auction_amount": price * vol_hand * _HAND_TO_SHARE,  # 元 (闭合 22,639,818)
            "auction_virtual_price": price,
        })
        num_trades_by_symbol[sym] = int(rec["num_trades"])  # 元数据只进返回/manifest
    canonical_df = pl.DataFrame({
        "symbol": [r["symbol"] for r in rows],
        "datetime": [r["datetime"] for r in rows],
        "auction_volume": [r["auction_volume"] for r in rows],
        "auction_amount": [r["auction_amount"] for r in rows],
        "auction_virtual_price": [r["auction_virtual_price"] for r in rows],
    })

    # ---- 写湖: 555..565 谓词 + 存在性 crop + merge-upsert 幂等 + 原子写 (直调, probe 闸门不在其内) ----
    write_auction_partitions(canonical_df, repo)
    logger.info(
        "promote %s: %d 撮合行升湖 (symbols=%s)",
        trade_date.isoformat(), canonical_df.height, sorted(num_trades_by_symbol),
    )
    return {
        "written": canonical_df.height,
        "symbols": sorted(num_trades_by_symbol),
        "num_trades_by_symbol": num_trades_by_symbol,
    }
