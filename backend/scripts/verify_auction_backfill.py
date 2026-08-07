"""FA-04 只读验收验证脚本 — 湖六项事实 + 完整性裁决 (verify_auction_backfill.py)。

只读: 全部事实经 KlineRepository 注册的 DuckDB 视图 (kline_daily / kline_auction)
SELECT 推导 + data_dir 路径 glob; 零写入、零网络、零新依赖。绝不 consult 回填台账
(--out JSON) —— 验收只信湖本身, 台账只是旁证。

输出 (打印清单):
  [1] universe  (kline_daily): distinct symbols 5537 (SZ/SH/BJ 拆解) + 总行数
  [2] lake      (kline_auction): 分区数 (date=* 目录) + 总行数 + distinct symbols
  [3] BJ 台账再推导: kline_daily 内 .BJ (920xxx) 缺失于 kline_auction 的 symbol 集合
      (终态恒 333 —— 上游无 BJ 竞价数据, empty_response 诚实集合, 独立于运行台账);
      湖内 BJ 行 symbol 数 (恒 0) + 非 92 号段异常计数 (恒 0)
  [4] 交叉校验: >=3 日 x 全部已写 symbol, auction_virtual_price == kline_daily.open
      (1e-6 容差, 镜像 honesty 罐装断言 rel=1e-6) -> mismatch 恒 0
  [5] .tmp 残留: kline_auction 树内 *.tmp = 0
  [6] 覆盖口径: auction_symbol_count / 5537 (如 0.940) —— 永不打印 "100%"

完整性裁决 (退出码):
  0  PASS      —— 湖达预期终态: 全部非 BJ symbol 已覆盖 + 分区数对齐 kline_daily
                 + 行数在 [kline_daily 推导下限, 非BJ数 x 分区数 上限] + 全部不变量成立
  1  PARTIAL   —— 回填进行中/中断/上游源受阻 (覆盖 symbol 数 < 预期, 或行数低于下限):
                 诚实打印 partial 状态, 绝不假装完成 (fail-closed); 若传 --ledger,
                 按 failed_symbols 归类疑似源受阻 (非 BJ 标的 source_blocked = 上游
                 403/配额窗策略封锁; empty_response = 真空缺口, HON-01 已区分, FA-05)
  2  FAIL      —— 计数已达终态但内在不变量被破坏 (交叉 mismatch / .tmp 残留 /
                 BJ 台账漂移 / 湖外多出 symbol)

用法:
    python scripts/verify_auction_backfill.py [--dates N] [--ledger PATH]
    DATA_DIR=/path/to/data python scripts/verify_auction_backfill.py

--ledger 为回填运行终态台账 (--out JSON, 只读旁证): 仅用于 partial 状态下归类
疑似源受阻 (source_blocked 策略封锁 / empty_response 真空缺口, HON-01 独立归类);
PASS/FAIL 判定完全不依赖台账 (验收只信湖本身)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))  # backend/ — app 包根

import polars as pl  # noqa: E402

from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402

_CROSS_TOL = 1e-6  # 交叉校验容差 (镜像 honesty 罐装断言 pytest.approx rel=1e-6)
_ROW_FLOOR_RATIO = 0.99  # 行数下限 = kline_daily 推导 (symbol,date) 对数的 99%


def _fetch_one(db, sql, params=None):
    row = db.execute(sql, params or []).fetchone()
    return None if row is None else row[0]


def _universe(db) -> dict:
    """kline_daily distinct symbol 后缀拆解 (SZ/SH/BJ) + 总行数。"""
    row = db.execute(
        "SELECT COUNT(DISTINCT symbol) AS total,"
        " COUNT(DISTINCT CASE WHEN symbol LIKE '%.SZ' THEN symbol END) AS sz,"
        " COUNT(DISTINCT CASE WHEN symbol LIKE '%.SH' THEN symbol END) AS sh,"
        " COUNT(DISTINCT CASE WHEN symbol LIKE '%.BJ' THEN symbol END) AS bj"
        " FROM kline_daily"
    ).fetchone()
    return {
        "total": int(row[0]),
        "SZ": int(row[1]),
        "SH": int(row[2]),
        "BJ": int(row[3]),
    }


def _lake(db, data_dir: Path) -> dict:
    """kline_auction 分区数 (date=* 目录) + 行数 + distinct symbols。"""
    parts = [p for p in (data_dir / "kline_auction").glob("date=*") if p.is_dir()]
    rows = _fetch_one(db, "SELECT COUNT(*) FROM kline_auction") or 0
    syms = _fetch_one(db, "SELECT COUNT(DISTINCT symbol) FROM kline_auction") or 0
    return {"partitions": len(parts), "rows": int(rows), "symbols": int(syms)}


def _minute_stats(data_dir: Path) -> dict:
    """kline_minute 09:30 bar 统计口径 (只读, 镜像 _lake 形态)。

    09:30 bar = 集合竞价统计 (非逐笔, caliber=statistical_minute_0930) — 只数
    ``datetime.time()==09:30`` 的行; 坏分区/空分区/缺 canonical 列 → fail-closed
    skip (T-29-01-05); dates = 含 09:30 行的分区数 (诚实 — 无 09:30 行的分区不计,
    绝不虚报日期深度)。统计口径只进报告, 绝不写 canonical 湖。
    """
    base = data_dir / "kline_minute"
    symbols: set[str] = set()
    rows = 0
    dates = 0
    if base.exists():
        for part in base.glob("date=*/part.parquet"):
            try:
                f = pl.read_parquet(part)
            except Exception:  # noqa: BLE001 — fail-closed
                continue
            if (
                f.is_empty()
                or not {"datetime", "symbol"} <= set(f.columns)
            ):
                continue
            bars = f.filter(pl.col("datetime").dt.time() == time(9, 30))
            if bars.is_empty():
                continue
            symbols.update(bars["symbol"].unique().to_list())
            rows += bars.height
            dates += 1
    return {"symbols": len(symbols), "rows": rows, "dates": dates}


def _bj_ledger(db) -> dict:
    """BJ 台账再推导: kline_daily .BJ 缺失于 kline_auction 的集合 (独立于运行台账)。"""
    base = (
        "SELECT DISTINCT d.symbol FROM kline_daily d"
        " LEFT JOIN (SELECT DISTINCT symbol FROM kline_auction) a USING (symbol)"
        " WHERE d.symbol LIKE '%.BJ' AND a.symbol IS NULL"
    )
    missing = _fetch_one(db, f"SELECT COUNT(*) FROM ({base}) t") or 0
    off_segment = (
        _fetch_one(
            db,
            "SELECT COUNT(DISTINCT d.symbol) FROM kline_daily d"
            " LEFT JOIN (SELECT DISTINCT symbol FROM kline_auction) a USING (symbol)"
            " WHERE d.symbol LIKE '%.BJ' AND a.symbol IS NULL AND d.symbol NOT LIKE '92%'",
        )
        or 0
    )
    present = _fetch_one(
        db, "SELECT COUNT(DISTINCT symbol) FROM kline_auction WHERE symbol LIKE '%.BJ'"
    ) or 0
    sample = [str(r[0]) for r in db.execute(
        f"{base} ORDER BY d.symbol LIMIT 5",
    ).fetchall()]
    return {
        "missing": int(missing),
        "expected": int(_fetch_one(db, "SELECT COUNT(DISTINCT symbol) FROM kline_daily WHERE symbol LIKE '%.BJ'") or 0),
        "off_segment": int(off_segment),
        "present": int(present),
        "sample": sample,
    }


def _missing_non_bj(db) -> int:
    """非 BJ (SZ/SH) kline_daily symbol 缺失于 kline_auction 的计数 —— 覆盖完整性主闸门。"""
    return int(
        _fetch_one(
            db,
            "SELECT COUNT(DISTINCT d.symbol) FROM kline_daily d"
            " LEFT JOIN (SELECT DISTINCT symbol FROM kline_auction) a USING (symbol)"
            " WHERE d.symbol NOT LIKE '%.BJ' AND a.symbol IS NULL",
        )
        or 0
    )


def _extra_auction_symbols(db) -> int:
    """kline_auction 内不在 kline_daily 的 symbol 计数 (历史残留/越界写入 → 不变量破坏)。"""
    return int(
        _fetch_one(
            db,
            "SELECT COUNT(DISTINCT a.symbol) FROM kline_auction a"
            " LEFT JOIN (SELECT DISTINCT symbol FROM kline_daily) d USING (symbol)"
            " WHERE d.symbol IS NULL",
        )
        or 0
    )


def _expected_rows(db, non_bj_syms: int, partitions: int) -> tuple[int, int]:
    """行数预期: 下限 = kline_daily (symbol,date) 对数 (真实覆盖, 含新股/停牌短历史);
    上限 = 非 BJ symbol 数 x 分区数 (每 symbol 每日恰 1 行 canonical 不变式)。"""
    floor = int(
        _fetch_one(
            db,
            "SELECT COUNT(*) FROM (SELECT DISTINCT symbol, date FROM kline_daily"
            " WHERE symbol NOT LIKE '%.BJ')",
        )
        or 0
    )
    return floor, non_bj_syms * partitions


def _cross_check(db, n_dates: int) -> dict:
    """>=3 日 x 全部已写 symbol: auction_virtual_price == kline_daily.open (1e-6 容差)。"""
    dates = [r[0] for r in db.execute(
        "SELECT DISTINCT date FROM kline_daily ORDER BY date DESC LIMIT ?", [n_dates],
    ).fetchall()]
    if not dates:
        return {"dates": [], "pairs": 0, "mismatches": 0}
    marks = ",".join("?" for _ in dates)
    params = list(dates)
    pairs = int(_fetch_one(
        db,
        f"SELECT COUNT(*) FROM kline_auction a JOIN kline_daily d"
        f" ON a.symbol = d.symbol AND CAST(a.datetime AS DATE) = d.date"
        f" WHERE d.date IN ({marks})",
        params,
    ) or 0)
    mismatches = int(_fetch_one(
        db,
        f"SELECT COUNT(*) FROM kline_auction a JOIN kline_daily d"
        f" ON a.symbol = d.symbol AND CAST(a.datetime AS DATE) = d.date"
        f" WHERE d.date IN ({marks}) AND a.auction_virtual_price IS NOT NULL"
        f" AND abs(a.auction_virtual_price - d.open) > ?",
        params + [_CROSS_TOL],
    ) or 0)
    return {"dates": [str(d) for d in dates], "pairs": pairs, "mismatches": mismatches}


def _tmp_residue(data_dir: Path) -> list[Path]:
    """kline_auction 树内 *.tmp 残留扫描。"""
    return list((data_dir / "kline_auction").rglob("*.tmp"))


def _classify_source_block(ledger_path: str | None, lake_partial: bool) -> str:
    """partial 状态下按运行台账 failed_symbols 归类疑似源受阻 (只读旁证)。

    - 非 BJ 标的 source_blocked → YES 策略封锁 (HON-01: 上游 403/配额窗 typed
      信号, 与 empty_response 互斥)。
    - 非 BJ 标的 empty_response → 疑似真空缺口 (HON-01 后不再含 403 伪装含义;
      empty_response = 上游真空/无数据, 诚实缺口见 FA-05-BJ-STANCE.md)。
    - 全部失败皆 .BJ → 已知永久缺口; 湖仍缺非 BJ 覆盖 → 台账无法解释, 续跑
      --all --only-missing。
    - 无台账 → UNKNOWN, 明示缺口。
    """
    if not lake_partial:
        return "N/A — 湖已达预期终态, 无需归类"
    if not ledger_path:
        return (
            "UNKNOWN — 未传 --ledger 运行台账; 403/配额窗策略封锁现已独立记"
            " source_blocked (HON-01), 传 --ledger 即可归类"
        )
    try:
        data = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return f"UNKNOWN — 台账不可读 ({e})"
    failed_symbols = data.get("failed_symbols") or []
    blocked = [
        f for f in failed_symbols
        if f.get("reason") == "source_blocked"
        and not str(f.get("symbol", "")).endswith(".BJ")
    ]
    if blocked:
        sample = ", ".join(str(f.get("symbol")) for f in blocked[:5])
        return (
            f"YES — 台账含 {len(blocked)} 个非 BJ 标的 source_blocked"
            f" (上游 403/配额窗策略封锁: {sample} ...)"
        )
    non_bj = [f for f in failed_symbols if not str(f.get("symbol", "")).endswith(".BJ")]
    if non_bj:
        sample = ", ".join(str(f.get("symbol")) for f in non_bj[:5])
        return (
            f"疑似 — 台账含 {len(non_bj)} 个非 BJ 标的 empty_response"
            f" (上游真空/无数据, 非策略封锁 — source_blocked 已独立归类: {sample} ...)"
        )
    if failed_symbols:
        return (
            "NO — 台账失败全为 .BJ (已知永久缺口); 湖仍缺非 BJ 覆盖且台账无法解释"
            " → 以 --all --only-missing 续跑"
        )
    return "UNKNOWN — 台账无 failed_symbols 但湖为 partial"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verify_auction_backfill",
        description="FA-04 只读验收: 湖六项事实 + 完整性裁决 (0=PASS / 1=PARTIAL / 2=FAIL)",
    )
    parser.add_argument(
        "--dates",
        type=int,
        default=3,
        help="交叉校验日期数 (>=1, 缺省 3; 取 kline_daily 最近 N 个交易日)",
    )
    parser.add_argument(
        "--ledger",
        default=None,
        help="回填运行终态台账 JSON (--out, 只读旁证): partial 状态下归类疑似源受阻",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    env_data = os.environ.get("DATA_DIR")
    data_dir = Path(env_data) if env_data else (Path(__file__).resolve().parents[2] / "data")
    repo = KlineRepository(DataStore(data_dir))
    db = repo.db

    uni = _universe(db)
    lake = _lake(db, data_dir)
    bj = _bj_ledger(db)
    missing_non_bj = _missing_non_bj(db)
    extra = _extra_auction_symbols(db)
    daily_parts = len([p for p in (data_dir / "kline_daily").glob("date=*") if p.is_dir()])
    floor, nominal = _expected_rows(db, uni["total"] - uni["BJ"], daily_parts)
    cross = _cross_check(db, args.dates)
    tmp = _tmp_residue(data_dir)
    coverage = (lake["symbols"] / uni["total"]) if uni["total"] else 0.0

    print("=== verify_auction_backfill (read-only, lake-derived) ===")
    print(
        f"[1] universe:      symbols={uni['total']} "
        f"(SZ {uni['SZ']} / SH {uni['SH']} / BJ {uni['BJ']}), rows={_fetch_one(db, 'SELECT COUNT(*) FROM kline_daily')}"
    )
    print(
        f"[2] lake:          partitions={lake['partitions']}/{daily_parts}, "
        f"rows={lake['rows']} (floor {floor} / nominal {nominal}), symbols={lake['symbols']}/{uni['total'] - uni['BJ']}"
    )
    sample_txt = " ".join(bj["sample"])
    print(
        f"[3] BJ ledger:     missing={bj['missing']}/{bj['expected']} (92xxxxx.BJ), "
        f"present-in-lake={bj['present']}, off-segment={bj['off_segment']}; "
        f"sample: {sample_txt}{' ...' if bj['missing'] > len(bj['sample']) else ''}"
    )
    print(
        f"[4] cross-check:   dates={len(cross['dates'])} ({', '.join(cross['dates'])}), "
        f"pairs={cross['pairs']}, mismatches={cross['mismatches']}"
    )
    print(f"[5] .tmp residue:  {len(tmp)}")
    print(
        f"[6] coverage:      auction_symbol_count/{uni['total']} = {coverage:.3f}"
        f"{' — PARTIAL' if coverage < 1.0 else ''}"
    )
    # MIN-02 统计口径并列行 (独立 caliber, 与 canonical 绝不相加; 分母 = 运行期 universe)
    m_stats = _minute_stats(data_dir)
    m_ratio = (m_stats["symbols"] / uni["total"]) if uni["total"] else 0.0
    print(
        f"minute_stats: {m_stats['symbols']}/{uni['total']} = {m_ratio:.3f}"
        f" (dates={m_stats['dates']}, caliber=statistical_minute_0930)"
        f"{' — PARTIAL' if m_ratio < 1.0 else ''}"
    )

    complete = (
        missing_non_bj == 0
        and lake["partitions"] == daily_parts
        and lake["rows"] >= _ROW_FLOOR_RATIO * floor
        and lake["rows"] <= nominal
    )
    if complete:
        broken = (
            cross["mismatches"] > 0
            or tmp
            or bj["missing"] != bj["expected"]
            or bj["present"] != 0
            or bj["off_segment"] != 0
            or extra != 0
        )
        if broken:
            print(
                "verdict: FAIL — 计数已达终态但内在不变量被破坏"
                f" (mismatches={cross['mismatches']}, tmp={len(tmp)}, "
                f"bj_missing={bj['missing']}/{bj['expected']}, bj_present={bj['present']}, "
                f"bj_off_segment={bj['off_segment']}, extra_symbols={extra}) (exit 2)"
            )
            return 2
        print("verdict: PASS — 湖达预期终态 (exit 0)")
        return 0
    print(
        "verdict: PARTIAL — 回填进行中/中断/上游源受阻, 不得视为完成 (fail-closed): "
        f"missing_non_bj={missing_non_bj}, rows={lake['rows']} "
        f"(floor {int(_ROW_FLOOR_RATIO * floor)}), partitions={lake['partitions']}/{daily_parts} (exit 1)"
    )
    print(f"suspected source-block: {_classify_source_block(args.ledger, lake_partial=True)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
