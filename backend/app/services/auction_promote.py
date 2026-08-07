"""T-day 竞价提审升湖 (SDC-02)。

把 staging (43-01 采集产物) 中**仅 09:25 num_trades>0 撮合行**升 canonical
``kline_auction``; 虚拟快照行 (num_trades=0) 与 09:25:01 回显行永不入湖
(555..565 谓词 + 提审过滤双保险, Pitfall 2); 单位映射锁死 (手→股 ×100, Pitfall 7);
自 T-day 起逐日累积幂等 (``promote_trading_day``); DATA-06 派生输入映射 —
``auction_virtual_price`` = 09:25 price 并交叉验证 ``kline_daily.open`` (1e-6, 镜像
verify_auction_backfill [4]), ``auction_unmatched_volume`` 诚实缺列 (tick 源无未匹配量
字段 → 绝不产出/绝不 0 填)。

提审闸门 (Pitfall 6): 当日 staging manifest ``completeness.ok`` ∧
``reconciliation.status == "closed"`` — 当日 staging 判定, **绝不用**
``resolve_auction_probe()`` (tick 源不在 probe 枚举, 复用恒不过); 闸门不过 →
0 写 + reason 显式返回, 绝不静默。

canonical 写面直调 ``auction_sync.write_auction_partitions`` (555..565 谓词 +
存在性 crop + merge-upsert 幂等 + 原子写; probe 闸门不在其内)。num_trades 只进
返回/manifest 元数据 — canonical 无此列。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

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


# promote 输出列: 4 canonical + auction_virtual_price (OPTIONAL_AUCTION_COLS 子集);
# auction_unmatched_volume 诚实缺列 — 本模块绝不构造该列。
_PROMOTE_COLS = [
    "symbol", "datetime", "auction_volume", "auction_amount", "auction_virtual_price",
]


def _json_default(obj: Any) -> Any:
    """date/datetime → isoformat (镜像 premarket_snapshot._json_default)。"""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _existing_partition_keys(data_dir: Path, trade_date: date) -> set[tuple[str, datetime]]:
    """kline_auction/date={T} 既有 (symbol, datetime) 键集 — 供 written 计数 (幂等重跑)。"""
    part = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    if not part.exists():
        return set()
    df = pl.read_parquet(part)
    return set(zip(df["symbol"].to_list(), df["datetime"].to_list()))


def _update_manifest_promoted(stage_dir: Path, payload: dict) -> None:
    """读旧 manifest → 增 promoted 块 → temp+os.replace 原子写 (镜像 premarket_snapshot)。

    旧 manifest 缺失 (gate 已拒) 不写 — 绝不伪造提审状态; 旧键全部保留。
    """
    mf = stage_dir / "manifest.json"
    if not mf.exists():
        return
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:  # pragma: no cover - gate 已验可读
        logger.warning("promote: manifest unreadable, promoted block skipped: %s", e)
        return
    manifest.update(payload)
    tmp = mf.with_name(mf.name + ".tmp")
    tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, default=_json_default, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, mf)


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
    }).select(_PROMOTE_COLS)  # 输出列契约锁形 (4 canonical + virtual_price; 无 unmatched)

    # ---- 写湖: 555..565 谓词 + 存在性 crop + merge-upsert 幂等 + 原子写 (直调, probe 闸门不在其内) ----
    existing_keys = _existing_partition_keys(repo.store.data_dir, trade_date)
    new_keys = set(zip(
        canonical_df["symbol"].to_list(), canonical_df["datetime"].to_list(),
    ))
    written = len(new_keys - existing_keys)
    write_auction_partitions(canonical_df, repo)

    _update_manifest_promoted(stage_dir, {
        "promoted": True,
        "promoted_at": datetime.now().isoformat(timespec="seconds"),
        "written": written,
        "num_trades_by_symbol": num_trades_by_symbol,
    })
    logger.info(
        "promote %s: %d 撮合行升湖 (symbols=%s)",
        trade_date.isoformat(), written, sorted(num_trades_by_symbol),
    )
    return {
        "written": written,
        "symbols": sorted(num_trades_by_symbol),
        "num_trades_by_symbol": num_trades_by_symbol,
    }


def promote_trading_day(
    repo: KlineRepository,
    data_dir: Path,
    trade_dates: list[date],
) -> dict:
    """自 T-day 起逐日累积: 每交易日一分区逐日提审 (幂等重跑 merge-upsert)。

    无 staging 分区 → 该日 skipped (staging_missing), 不写湖不报错; gate 拒绝 →
    该日 skipped (reason 透传) — 全链路诚实可观测。

    Returns:
        ``{"promoted_dates": [iso], "skipped": [{"date": iso, "reason": …}],
        "total_written": int}``
    """
    promoted_dates: list[str] = []
    skipped: list[dict] = []
    total_written = 0
    for d in trade_dates:
        stage_dir = Path(data_dir) / "tick_staging" / f"date={d.isoformat()}"
        if not (stage_dir / "part.parquet").exists():
            skipped.append({"date": d.isoformat(), "reason": "staging_missing"})
            continue
        result = promote_to_canonical(stage_dir, repo, d)
        if result.get("written", 0) > 0:
            promoted_dates.append(d.isoformat())
            total_written += result["written"]
        else:
            skipped.append({
                "date": d.isoformat(),
                "reason": result.get("reason", "no_match_rows"),
            })
    return {
        "promoted_dates": promoted_dates,
        "skipped": skipped,
        "total_written": total_written,
    }


def cross_validate_virtual_price(
    repo: KlineRepository,
    trade_date: date,
    symbols: list[str] | None = None,
    tol: float = 1e-6,
) -> dict:
    """DATA-06 交叉验证: ``auction_virtual_price`` == ``kline_daily.open`` (1e-6)。

    镜像 verify_auction_backfill [4] 语义 — kline_daily.open 是独立第二来源互证。
    数据在场为准: 无 kline_daily 当日分区 → ``{"skipped": [symbols],
    "reason": "no_kline_daily"}`` 诚实标注, 绝不猜测/绝不吞。

    Returns:
        ``{"checked": [{symbol, virtual_price, kline_open, diff, ok}],
        "all_ok": bool, "skipped": [symbols], "reason"?: str}``
    """
    data_dir = repo.store.data_dir
    auc_part = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    if not auc_part.exists():
        return {"checked": [], "all_ok": True, "skipped": []}
    auction = pl.read_parquet(auc_part)
    if "auction_virtual_price" not in auction.columns:
        return {"checked": [], "all_ok": True, "skipped": []}
    if symbols is not None:
        auction = auction.filter(pl.col("symbol").is_in(symbols))
    if auction.is_empty():
        return {"checked": [], "all_ok": True, "skipped": []}
    auction_syms = sorted(auction["symbol"].unique().to_list())

    daily_part = data_dir / "kline_daily" / f"date={trade_date.isoformat()}" / "part.parquet"
    if not daily_part.exists() or "open" not in pl.read_parquet(daily_part).columns:
        return {
            "checked": [],
            "all_ok": True,
            "skipped": auction_syms,
            "reason": "no_kline_daily",
        }
    daily = pl.read_parquet(daily_part).select(["symbol", "open"])

    joined = auction.select(["symbol", "auction_virtual_price"]).join(
        daily, on="symbol", how="left",
    )
    checked: list[dict] = []
    skipped: list[str] = []
    for rec in joined.iter_rows(named=True):
        if rec.get("open") is None:  # 该 symbol 当日 daily 缺行 → 诚实标注
            skipped.append(rec["symbol"])
            continue
        vp = float(rec["auction_virtual_price"])
        open_ = float(rec["open"])
        diff = abs(vp - open_)
        checked.append({
            "symbol": rec["symbol"],
            "virtual_price": vp,
            "kline_open": open_,
            "diff": diff,
            "ok": diff <= tol,
        })
    return {
        "checked": checked,
        "all_ok": all(c["ok"] for c in checked),
        "skipped": sorted(set(skipped)),
    }
