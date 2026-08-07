"""verify_auction_backfill.py 的 hermetic 测试 (token: verify)。

tmp 湖 (kline_daily + kline_auction date=* 分区) + 真 KlineRepository (DuckDB 视图),
以 DATA_DIR env 驱动脚本 main(), 断言:

- 完整终态湖 → 退出 0 (PASS), 六项事实齐全, 覆盖口径为小数 (如 0.667) 而非 100%。
- partial 湖 (覆盖 symbol 数 < 预期) → 退出 1, 诚实 partial 口径 (fail-closed,
  回填进行中/中断不得假装完成)。
- 不变量破坏 (交叉 mismatch / .tmp 残留) → 退出 2 (FAIL)。
- BJ 台账再推导: .BJ symbol 缺失于 kline_auction 恒等 kline_daily 的 BJ 数;
  湖内 BJ 行恒 0 (绝不预填)。
- 覆盖口径守卫: 满覆盖场景打印 "1.000" 而绝不出现 "100%" 字符串。
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verify_auction_backfill as verify  # noqa: E402


def _seed_daily(tmp_path: Path, daily_dates, symbols, opens=None) -> None:
    """kline_daily/date=* 分区 (symbol/open 列, 镜像 36-01 _seed_daily)。"""
    opens = opens or {}
    for d in daily_dates:
        part = tmp_path / "kline_daily" / f"date={d.isoformat()}"
        part.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({
            "symbol": list(symbols),
            "open": [float(opens.get(d, 10.0))] * len(symbols),
        }).write_parquet(part / "part.parquet")


def _seed_auction(tmp_path: Path, daily_dates, symbols, vp_by_pair=None) -> None:
    """kline_auction/date=* 分区 (canonical 列形, auction_virtual_price 可注入)。"""
    vp_by_pair = vp_by_pair or {}
    for d in daily_dates:
        part = tmp_path / "kline_auction" / f"date={d.isoformat()}"
        part.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "symbol": s,
                "datetime": datetime(d.year, d.month, d.day, 9, 25),
                "auction_volume": 100.0,
                "auction_amount": 1000.0,
                "auction_virtual_price": float(vp_by_pair.get((s, d), 10.0)),
            }
            for s in symbols
        ]
        pl.DataFrame(rows).write_parquet(part / "part.parquet")


def _seed_minute(tmp_path: Path, daily_dates, symbols, include_0930=True) -> None:
    """kline_minute/date=* 分区: 每日期每 symbol 一根 09:30 bar (canonical 列形,
    镜像 _seed_auction)。include_0930=False → 只写 09:31 行 (无 09:30 → 统计 0)。"""
    for d in daily_dates:
        part = tmp_path / "kline_minute" / f"date={d.isoformat()}"
        part.mkdir(parents=True, exist_ok=True)
        minute = 30 if include_0930 else 31
        rows = [
            {
                "symbol": s,
                "datetime": datetime(d.year, d.month, d.day, 9, minute),
                "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
                "volume": 521.0, "amount": None,
            }
            for s in symbols
        ]
        pl.DataFrame(rows).write_parquet(part / "part.parquet")


def _run(monkeypatch, tmp_path, *argv) -> tuple[int, str]:
    """DATA_DIR 指向 tmp 湖, 跑脚本 main(), 返回 (退出码, stdout)。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = verify.main(list(argv))
    return code, buf.getvalue()


D1, D2, D3 = date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)
SZ, SH, BJ = "000001.SZ", "600000.SH", "920146.BJ"


def test_verify_pass_complete_lake(tmp_path, monkeypatch):
    """完整终态湖 (SZ+SH 全覆盖, BJ 只存在于 kline_daily) → PASS 退出 0, 六项事实齐全。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ, SH])
    code, out = _run(monkeypatch, tmp_path)

    assert code == 0
    assert "verdict: PASS" in out
    assert "[1] universe:" in out and "symbols=3 (SZ 1 / SH 1 / BJ 1)" in out
    assert "[2] lake:" in out and "partitions=3/3" in out and "rows=6" in out
    assert "[3] BJ ledger:" in out and "missing=1/1" in out and "present-in-lake=0" in out
    assert "[4] cross-check:" in out and "mismatches=0" in out
    assert "[5] .tmp residue:  0" in out
    assert "[6] coverage:" in out and "= 0.667" in out
    assert "100%" not in out


def test_verify_partial_lake_fail_closed(tmp_path, monkeypatch):
    """partial 湖 (只覆盖 1/2 非 BJ symbol) → PARTIAL 退出 1, 诚实数字, 不假装完成。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ])  # SH 缺失 (回填进行中)
    code, out = _run(monkeypatch, tmp_path)

    assert code == 1
    assert "verdict: PARTIAL" in out
    assert "回填进行中/中断/上游源受阻, 不得视为完成 (fail-closed)" in out
    assert "missing_non_bj=1" in out
    assert "rows=3" in out
    assert "[6] coverage:" in out and "0.333" in out
    assert "100%" not in out
    assert "suspected source-block: UNKNOWN" in out  # 未传 --ledger → 诚实 UNKNOWN


def test_verify_partial_source_block_yes_non_bj_failures(tmp_path, monkeypatch):
    """partial + 台账含非 BJ 标的 source_blocked → YES 策略封锁 (上游 403/配额窗 typed 信号)。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ])  # SH 缺失
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        '{"requested": 3, "backfilled_symbols": 1, "rows": 3, "dates": 3,'
        ' "failed": 2, "failed_symbols": ['
        '{"symbol": "600000.SH", "reason": "source_blocked"},'
        '{"symbol": "920146.BJ", "reason": "empty_response"}],'
        ' "origin": "backfill", "rpm": 30}',
        encoding="utf-8",
    )
    code, out = _run(monkeypatch, tmp_path, "--ledger", str(ledger))

    assert code == 1
    assert "verdict: PARTIAL" in out
    assert "suspected source-block: YES" in out
    assert "1 个非 BJ 标的 source_blocked" in out
    assert "策略封锁" in out


def test_verify_partial_source_block_vacuum_empty_response(tmp_path, monkeypatch):
    """partial + 台账只有非 BJ empty_response → 疑似真空缺口 (403 伪装已不存在, HON-01)。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ])  # SH 缺失
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        '{"requested": 2, "backfilled_symbols": 1, "rows": 3, "dates": 3,'
        ' "failed": 1, "failed_symbols": ['
        '{"symbol": "600000.SH", "reason": "empty_response"}],'
        ' "origin": "backfill", "rpm": 30}',
        encoding="utf-8",
    )
    code, out = _run(monkeypatch, tmp_path, "--ledger", str(ledger))

    assert code == 1
    assert "verdict: PARTIAL" in out
    assert "suspected source-block: 疑似" in out
    assert "真空" in out
    assert "source_blocked 已独立归类" in out


def test_verify_partial_source_block_no_bj_only_failures(tmp_path, monkeypatch):
    """partial + 台账失败全为 .BJ → 疑似源受阻 NO (已知永久缺口), 提示 --only-missing 续跑。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ])  # SH 缺失, 但台账只记了 BJ 失败
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        '{"requested": 1, "backfilled_symbols": 0, "rows": 0, "dates": 3,'
        ' "failed": 1, "failed_symbols": ['
        '{"symbol": "920146.BJ", "reason": "empty_response"}],'
        ' "origin": "backfill", "rpm": 30}',
        encoding="utf-8",
    )
    code, out = _run(monkeypatch, tmp_path, "--ledger", str(ledger))

    assert code == 1
    assert "verdict: PARTIAL" in out
    assert "suspected source-block: NO" in out
    assert "only-missing" in out


def test_verify_partial_source_block_ledger_unreadable(tmp_path, monkeypatch):
    """partial + 台账路径不存在/损坏 → UNKNOWN, 明示诚实缺口。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ])
    code, out = _run(monkeypatch, tmp_path, "--ledger", str(tmp_path / "missing.json"))

    assert code == 1
    assert "suspected source-block: UNKNOWN" in out
    assert "台账不可读" in out


def test_verify_fail_on_cross_check_mismatch(tmp_path, monkeypatch):
    """计数达终态但 virtual_price != open → FAIL 退出 2 (内在不变量破坏)。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ], opens={D1: 10.0, D2: 10.2, D3: 10.4})
    # 除 000001.SZ@D2 (10.0 vs open 10.2) 外全部对齐 —— 恰 1 处 mismatch
    _seed_auction(
        tmp_path, [D1, D2, D3], [SZ, SH],
        vp_by_pair={
            (SZ, D1): 10.0, (SZ, D3): 10.4,
            (SH, D1): 10.0, (SH, D2): 10.2, (SH, D3): 10.4,
        },
    )
    code, out = _run(monkeypatch, tmp_path)

    assert code == 2
    assert "verdict: FAIL" in out
    assert "mismatches=1" in out
    assert "100%" not in out


def test_verify_fail_on_tmp_residue(tmp_path, monkeypatch):
    """计数达终态但 kline_auction 树内有 .tmp 残留 → FAIL 退出 2。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ, SH])
    (tmp_path / "kline_auction" / "date=2026-08-05" / "part.parquet.tmp").write_text("x")
    code, out = _run(monkeypatch, tmp_path)

    assert code == 2
    assert "verdict: FAIL" in out
    assert ".tmp residue:  1" in out
    assert "100%" not in out


def test_verify_full_coverage_prints_fraction_not_100(tmp_path, monkeypatch):
    """满覆盖 (无 BJ, 全部 symbol 有 auction 行) → 覆盖 1.000, 绝不打印 "100%" 字符串。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ, SH])
    code, out = _run(monkeypatch, tmp_path)

    assert code == 0
    assert "verdict: PASS" in out
    assert "[3] BJ ledger:" in out and "missing=0/0" in out
    assert "[6] coverage:" in out and "= 1.000" in out
    assert "100%" not in out


def test_verify_never_writes_lake(tmp_path, monkeypatch):
    """只读守卫: 跑完脚本后湖文件树字节级不变 (零写入契约)。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ, SH])
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*.parquet")
    }
    code, _ = _run(monkeypatch, tmp_path)
    after = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*.parquet")
    }

    assert code == 0
    assert before == after


def test_verify_minute_stats_line_parallel(tmp_path, monkeypatch):
    """MIN-02: [6] 双口径并列 — canonical 行 (1/3) 与 minute_stats 行 (2/3,
    dates 计数 + caliber 标注) 各自独立打印, 绝不相加、绝不混同。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ])  # canonical 只覆盖 SZ
    _seed_minute(tmp_path, [D1, D2, D3], [SZ, SH])  # 统计口径覆盖 SZ+SH
    code, out = _run(monkeypatch, tmp_path)

    assert code == 1  # canonical partial (SH 缺失)
    assert "[6] coverage:" in out and "auction_symbol_count/3 = 0.333" in out
    assert "minute_stats: 2/3 = 0.667" in out
    assert "(dates=3" in out
    assert "caliber=statistical_minute_0930" in out
    assert "100%" not in out


def test_verify_minute_stats_no_100_percent(tmp_path, monkeypatch):
    """MIN-02: 满覆盖场景 (canonical 1.000 + minute_stats 1.000) → 绝不出 "100%"
    字符串 (既有覆盖口径守卫对双口径同时生效)。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ, SH])
    _seed_minute(tmp_path, [D1, D2, D3], [SZ, SH])
    code, out = _run(monkeypatch, tmp_path)

    assert code == 0
    assert "verdict: PASS" in out
    assert "[6] coverage:" in out and "= 1.000" in out
    assert "minute_stats: 2/2 = 1.000" in out
    assert "100%" not in out


def test_verify_minute_stats_honest_empty(tmp_path, monkeypatch):
    """MIN-02: 无 kline_minute 分区 → minute_stats 行 0/3 = 0.000, 退出码语义
    与 canonical 空态一致 (统计空绝不误判完成/失败)。"""
    _seed_daily(tmp_path, [D1, D2, D3], [SZ, SH, BJ])
    _seed_auction(tmp_path, [D1, D2, D3], [SZ])
    code, out = _run(monkeypatch, tmp_path)

    assert code == 1
    assert "minute_stats: 0/3 = 0.000" in out
    assert "(dates=0" in out
    assert "caliber=statistical_minute_0930" in out
    assert "100%" not in out
