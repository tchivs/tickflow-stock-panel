"""Phase 38 (MN-01/MN-03) — make_minute_loader 工厂 + hermetic 接线前行为测试。

Token 面: minute_loader / empty / truncate / readonly / not_applied。
- minute_loader: 工厂候选过滤 / 排序 / 缺分区空帧 / 损坏分区 fail-closed (W6)
- empty: 空湖行为保持 — required → 空 StrategyResult (与 minute_loader=None 逐字段一致,
  仅 elapsed_ms 除外); optional → 跳过确认保留日线核心池
- truncate: 分区在场点亮真实 auction_intraday_confirm + 单点截断 ≤ evaluation_time
  (T-21-01 "确认时刻之后无输入", W2/W3)
- readonly: loader 只读 — 分区在场两态 sha256+mtime 树快照逐字节一致 + 空湖态不建目录 +
  模块源码零写面结构门
- not_applied: 报告语义本文件不触碰; 既有 not_applied 锚点基线见 38-01-BASELINE.md (T3 批量)

Hermetic: 生产 import 全部放测试函数内 (repo 约定); fixture 镜像
test_auction_strategy_family.py / test_auction_strategy_family_p2.py (volume i×100k,
datetime cast Datetime("us") — 满足真实确认阈值 cum 1M × time_factor 16 ≥ 10M)。
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, time as dt_time
from pathlib import Path

import polars as pl
import pytest

_MINUTE_REQ_BODY = '''"""minute required probe"""
import polars as pl

META = {
    "id": "minute_req",
    "time_window": "intraday",
    "evaluation_time": "09:45",
    "minute_confirm_required": True,
    "scoring": {"open_gap": 1.0},
}

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("symbol").is_not_null()

def minute_confirm(df_minute: pl.DataFrame, params: dict) -> pl.DataFrame:
    return df_minute
'''

_MINUTE_OPT_BODY = '''"""minute optional probe"""
import polars as pl

META = {
    "id": "minute_opt",
    "time_window": "intraday",
    "evaluation_time": "09:45",
    "minute_confirm_required": False,
    "scoring": {"open_gap": 1.0},
}

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("symbol").is_not_null()

def minute_confirm(df_minute: pl.DataFrame, params: dict) -> pl.DataFrame:
    # 若被引擎调用 (空帧路径不调用) → 返回空 → 池清空; total==2 即证明确认被跳过而非空跑
    return df_minute.filter(pl.col("symbol").is_null())
'''

_INTRADAY_PROBE_BODY = '''"""intraday probe — 包装真实 auction_intraday_confirm + T-21-01 截断门禁"""
import polars as pl
from datetime import time as dt_time

from app.strategy.builtin.auction_intraday_confirm import minute_confirm as _real_minute_confirm

META = {
    "id": "intraday_probe",
    "time_window": "intraday",
    "evaluation_time": "09:45",
    "requires_auction_data": True,
    "minute_confirm_required": True,
    "scoring": {"open_gap": 1.0},
}

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("open_gap") >= 0.02

def minute_confirm(df_minute: pl.DataFrame, params: dict) -> pl.DataFrame:
    # 引擎单点截断后不应出现 > evaluation_time 的 bar (T-21-01 "确认时刻之后无输入")
    if not df_minute.is_empty():
        assert df_minute["datetime"].max().time() <= dt_time(9, 45), "确认时刻之后无输入"
    return _real_minute_confirm(df_minute, params)
'''


# ================================================================
# hermetic helpers (镜像 test_auction_strategy_family.py / _p2)
# ================================================================


def _engine(minute_loader=None, strategy_dirs=None):
    """真实引擎 + 空 enriched loader; 可注入 minute_loader。"""
    from app.strategy.engine import StrategyEngine

    return StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=strategy_dirs or [
            Path(__file__).resolve().parents[1] / "app" / "strategy" / "builtin",
        ],
        minute_loader=minute_loader,
    )


def _ctx(as_of, precomputed=None, asset_type="stock", timeframe="1d"):
    """创建 StrategyDataContext, 兼容 engine.run(context=...) 新签名。"""
    from app.strategy.engine import StrategyDataContext
    return StrategyDataContext(
        asset_type=asset_type,
        timeframe=timeframe,
        as_of=as_of,
        current=precomputed,
    )

def _write_strategy(tmp_path, name: str, body: str) -> Path:
    """写一个临时策略文件, 返回 strategies 目录。"""
    d = tmp_path / "strategies"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")
    return d


def _minute_partition_dir(tmp_path, trade_date: date) -> Path:
    d = tmp_path / "kline_minute" / f"date={trade_date.isoformat()}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_partition(data_dir, trade_date: date, frame: pl.DataFrame) -> None:
    """写 kline_minute/date={d}/part.parquet (canonical 列, datetime cast Datetime("us"))。"""
    out = data_dir / "kline_minute" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.with_columns(pl.col("datetime").cast(pl.Datetime("us"))).write_parquet(out)


def _minute_frame(symbols, times) -> pl.DataFrame:
    """构造含每 bar open=close、volume 递增 (i×100k) 的分钟帧 (canonical 8 列)。

    镜像 p2 _minute_frame: 满足真实 auction_intraday_confirm 阈值
    (eval=09:45 → time_factor=16 → 前 4 bar cum 1M × 16 = 16M ≥ 10M)。
    """
    rows = []
    for i, t in enumerate(times, start=1):
        for sym in symbols:
            rows.append({
                "symbol": sym,
                "datetime": datetime.combine(date(2026, 8, 4), t),
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": float(i * 100_000),
                "amount": float(i * 1_000_000),
            })
    return pl.DataFrame(rows, schema={
        "symbol": pl.Utf8,
        "datetime": pl.Datetime("us"),
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
    })


def _truncation_frame() -> pl.DataFrame:
    """600301/600302 全 6 bar (09:30..10:00), 600303 仅 09:50/10:00 bar。

    镜像 family test_minute_truncation_no_future 的 600003-drop 形: 截断后 600303 无行 → 落选。
    体积沿用 i×100k (前 4 bar cum 1M × time_factor 16 ≥ 10M, 满足真实确认阈值)。
    """
    times = [dt_time(9, 30), dt_time(9, 35), dt_time(9, 40), dt_time(9, 45),
             dt_time(9, 50), dt_time(10, 0)]
    rows = []
    for i, t in enumerate(times, start=1):
        for sym in ("600301", "600302"):
            rows.append({
                "symbol": sym,
                "datetime": datetime.combine(date(2026, 8, 4), t),
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": float(i * 100_000),
                "amount": float(i * 1_000_000),
            })
    for i, t in ((5, dt_time(9, 50)), (6, dt_time(10, 0))):
        rows.append({
            "symbol": "600303",
            "datetime": datetime.combine(date(2026, 8, 4), t),
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": float(i * 100_000),
            "amount": float(i * 1_000_000),
        })
    return pl.DataFrame(rows, schema={
        "symbol": pl.Utf8,
        "datetime": pl.Datetime("us"),
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
    })


def _snapshot_tree(root: Path) -> dict:
    """kline_minute 树快照: relpath → (sha256, mtime_ns) | ("dir",)。"""
    if not root.exists():
        return {}
    snap: dict = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_dir():
            snap[rel] = ("dir",)
        else:
            snap[rel] = (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
    return snap


# ================================================================
# MN-01/MN-03 hermetic tests
# ================================================================


def test_make_minute_loader_empty_lake_required_fail_closed(tmp_path):
    """token empty: 空湖 (无 kline_minute) + 工厂 loader + minute_req (required, eval 09:45)
    → 空 StrategyResult, 与 minute_loader=None 基线逐字段一致 (仅 elapsed_ms 除外)。"""
    from app.services.minute_loader import make_minute_loader

    _write_strategy(tmp_path, "minute_req.py", _MINUTE_REQ_BODY)
    daily = pl.DataFrame({"symbol": ["600001", "600002"], "open_gap": [0.03, 0.02]})
    kwargs = {
        "context": _ctx(date(2026, 8, 4), precomputed=daily),
        "overrides": {"basic_filter": {"enabled": False}},
    }

    wired = _engine(minute_loader=make_minute_loader(tmp_path), strategy_dirs=[tmp_path / "strategies"])
    baseline = _engine(minute_loader=None, strategy_dirs=[tmp_path / "strategies"])
    r_wired = wired.run("minute_req", **kwargs)
    r_base = baseline.run("minute_req", **kwargs)

    assert r_wired.total == 0
    assert r_wired.rows == []
    # 空湖行为字节保持: 与未接线基线逐字段一致 (elapsed_ms 除外)
    assert r_wired.as_of == r_base.as_of
    assert r_wired.strategy_id == r_base.strategy_id
    assert r_wired.rows == r_base.rows
    assert r_wired.total == r_base.total
    assert r_wired.scores == r_base.scores


def test_make_minute_loader_empty_lake_optional_keeps_pool(tmp_path):
    """token empty: 空湖 + minute_opt (minute_confirm_required=False) → 跳过确认, 日线核心池保留 total == 2。"""
    from app.services.minute_loader import make_minute_loader

    _write_strategy(tmp_path, "minute_opt.py", _MINUTE_OPT_BODY)
    daily = pl.DataFrame({"symbol": ["600001", "600002"], "open_gap": [0.03, 0.04]})
    engine = _engine(minute_loader=make_minute_loader(tmp_path), strategy_dirs=[tmp_path / "strategies"])
    result = engine.run(
        "minute_opt", context=_ctx(date(2026, 8, 4), precomputed=daily),
        overrides={"basic_filter": {"enabled": False}},
    )
    # minute_confirm 若被调用会清空池 → total==2 证明确认被跳过 (非空跑), 日线核心池保留
    assert result.total == 2
    assert {r["symbol"] for r in result.rows} == {"600001", "600002"}


def test_make_minute_loader_partition_truncation_lights_confirm(tmp_path, monkeypatch):
    """token truncate: 分区在场 + 工厂 loader + 真实 auction_intraday_confirm → 点亮确认 + 单点截断
    ≤ evaluation_time=09:45 (T-21-01)。断言包装器经引擎静默 (W2: patch 先于引擎构造, 策略文件经
    from-import 在 exec 时绑定 patched 函数 → 包装器真实经引擎运行); 600003 只有 09:50/10:00 bar
    → 截断后落选, result.total == 2。"""
    from app.services.minute_loader import make_minute_loader
    from app.strategy.builtin import auction_intraday_confirm

    times = [dt_time(9, 30), dt_time(9, 35), dt_time(9, 40), dt_time(9, 45),
             dt_time(9, 50), dt_time(10, 0)]
    frame = _truncation_frame()
    _write_partition(tmp_path, date(2026, 8, 4), frame)

    orig = auction_intraday_confirm.minute_confirm

    def asserting(df_minute, params):
        if not df_minute.is_empty():
            assert df_minute["datetime"].max().time() <= dt_time(9, 45)
        return orig(df_minute, params)

    # W2: minute_confirm_fn 在引擎 __init__ 时经 getattr 捕获 → patch 必须先于引擎构造;
    # 策略文件 from app.strategy.builtin.auction_intraday_confirm import minute_confirm
    # 在 exec 时取到 patched 函数, 包装器由此真实经引擎运行。
    monkeypatch.setattr(auction_intraday_confirm, "minute_confirm", asserting)

    # 直接喂未截断帧 → 断言触发, 证明门禁有效
    with pytest.raises(AssertionError):
        asserting(frame, {})

    _write_strategy(tmp_path, "intraday_probe.py", _INTRADAY_PROBE_BODY)
    daily = pl.DataFrame({
        "symbol": ["600301", "600302", "600303"],
        "open_gap": [0.03, 0.03, 0.03],
        "auction_volume": [1_000_000, 1_000_000, 1_000_000],
    })
    engine = _engine(minute_loader=make_minute_loader(tmp_path), strategy_dirs=[tmp_path / "strategies"])
    result = engine.run(
        "intraday_probe", context=_ctx(date(2026, 8, 4), precomputed=daily),
        overrides={"basic_filter": {"enabled": False}},
    )
    # 截断生效 (双门禁静默): 真实确认阈值 cum 1M × 16 ≥ 10M 只留 600301/600302
    assert result.total == 2
    assert {r["symbol"] for r in result.rows} == {"600301", "600302"}


def test_make_minute_loader_readonly(tmp_path):
    """token readonly: 调用前快照 kline_minute 树 (路径集 + sha256 + mtime), loader 调用 + 完整引擎
    run 后逐字节一致; 空湖态调用后 kline_minute 目录不存在 (工厂不创建)。"""
    from app.services.minute_loader import make_minute_loader

    loader = make_minute_loader(tmp_path)
    # 空湖态: 目录不存在, 调用后仍不存在
    assert not (tmp_path / "kline_minute").exists()
    assert loader(["600001"], date(2026, 8, 4)).is_empty()
    assert not (tmp_path / "kline_minute").exists()

    # 分区在场态: 完整引擎 run 前后 kline_minute 树逐字节一致
    _write_partition(tmp_path, date(2026, 8, 4), _minute_frame(["600001"], [dt_time(9, 30), dt_time(9, 45)]))
    _write_strategy(tmp_path, "minute_req.py", _MINUTE_REQ_BODY)
    snap_before = _snapshot_tree(tmp_path / "kline_minute")
    assert snap_before, "分区在场态快照不应为空"

    engine = _engine(minute_loader=loader, strategy_dirs=[tmp_path / "strategies"])
    daily = pl.DataFrame({"symbol": ["600001"], "open_gap": [0.03]})
    result = engine.run(
        "minute_req", context=_ctx(date(2026, 8, 4), precomputed=daily),
        overrides={"basic_filter": {"enabled": False}},
    )
    assert result.total == 1  # 确认点亮, 池保留 (loader 读到了分区)
    assert _snapshot_tree(tmp_path / "kline_minute") == snap_before


def test_make_minute_loader_candidate_filter_and_sort(tmp_path):
    """token minute_loader: 分区 3 symbol; loader(["600001","600003"], d) → 只含候选 2 symbol,
    行序 (symbol, datetime) 升序。"""
    from app.services.kline_sync import CANONICAL_MINUTE_COLS
    from app.services.minute_loader import make_minute_loader

    _write_partition(tmp_path, date(2026, 8, 4),
                     _minute_frame(["600001", "600002", "600003"],
                                   [dt_time(9, 30), dt_time(9, 45), dt_time(10, 0)]))
    loader = make_minute_loader(tmp_path)
    out = loader(["600003", "600001"], date(2026, 8, 4))

    assert not out.is_empty()
    assert out.columns == CANONICAL_MINUTE_COLS
    assert out.height == 6  # 2 候选 × 3 bar
    assert set(out["symbol"].unique().to_list()) == {"600001", "600003"}
    pairs = list(zip(out["symbol"].to_list(), [t.time() for t in out["datetime"].to_list()]))
    assert pairs == sorted(pairs)


def test_make_minute_loader_missing_partition_returns_empty(tmp_path):
    """token minute_loader/empty: 湖有分区 (date=2026-08-03) 但请求 date=2026-08-04 → 空帧不抛,
    列 == CANONICAL_MINUTE_COLS。"""
    from app.services.kline_sync import CANONICAL_MINUTE_COLS
    from app.services.minute_loader import make_minute_loader

    _write_partition(tmp_path, date(2026, 8, 3), _minute_frame(["600001"], [dt_time(9, 30)]))
    loader = make_minute_loader(tmp_path)
    out = loader(["600001"], date(2026, 8, 4))
    assert out.is_empty()
    assert out.columns == CANONICAL_MINUTE_COLS


def test_make_minute_loader_corrupt_partition_fail_closed(tmp_path, caplog):
    """token minute_loader/empty (W6): 分区文件损坏 (非 parquet 字节) → 空帧不抛 + logger.warning
    可见 (fail-closed, 不静默)。"""
    from app.services.kline_sync import CANONICAL_MINUTE_COLS
    from app.services.minute_loader import make_minute_loader

    d = _minute_partition_dir(tmp_path, date(2026, 8, 4))
    (d / "part.parquet").write_bytes(b"this is not a parquet file")
    loader = make_minute_loader(tmp_path)
    with caplog.at_level(logging.WARNING):
        out = loader(["600001"], date(2026, 8, 4))
    assert out.is_empty()
    assert out.columns == CANONICAL_MINUTE_COLS
    assert "fail-closed" in caplog.text


def test_make_minute_loader_module_no_write_paths():
    """token readonly: 结构门 — minute_loader.py 全文无写面调用 (镜像 test_concept_history.py
    _WRITE_PATTERNS 形)。"""
    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "minute_loader.py").read_text(
        encoding="utf-8")
    patterns = (
        re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"),
        re.compile(r"write_parquet"),
        re.compile(r"write_text"),
        re.compile(r"write_bytes"),
        re.compile(r"mkdir\s*\("),
        re.compile(r"create_dir"),
        re.compile(r"os\.replace"),
        re.compile(r"unlink\s*\("),
        re.compile(r"touch\s*\("),
    )
    for pat in patterns:
        assert not pat.search(src), f"minute_loader.py 出现写面: {pat.pattern}"


# ================================================================
# 38-02 (MN-02) — 双接线结构门 + wired-vs-unwired 空湖字节保持证明
# ================================================================


def _main_src() -> str:
    """应用组装层源码: main.py (路由/中间件) + bootstrap.py (lifespan 接线)。"""
    backend = Path(__file__).resolve().parents[1]
    return (backend / "app" / "main.py").read_text(encoding="utf-8") + "\n" + (
        backend / "app" / "bootstrap.py"
    ).read_text(encoding="utf-8")


def _governed_src() -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / "app" / "advanced" / "governed_runner.py").read_text(encoding="utf-8")


def test_main_wired_minute_loader():
    """token minute_loader: main.py 结构门 — 接线 import + 构造参数存在 (镜像
    test_auction_backfill.py:659-667 的 _main_src() 形; 后续重构不得静默拆除)。"""
    src = _main_src()
    assert "from app.services.minute_loader import make_minute_loader" in src
    assert "minute_loader=make_minute_loader(store.data_dir)" in src


def test_governed_runner_wired_minute_loader():
    """token minute_loader: governed_runner.py 结构门 — _service() 内接线 + import 严格本地
    (模块顶层零新增 import: make_minute_loader 的 import 行缩进 > 0, 防 DuckDB 单例采集期导入)。"""
    src = _governed_src()
    assert "minute_loader=make_minute_loader(data_dir)" in src
    hit = False
    for line in src.splitlines():
        if "from app.services.minute_loader import make_minute_loader" in line:
            hit = True
            assert line.startswith(" "), \
                "governed_runner.py 的 minute_loader import 必须留在 _service() 内 (缩进 > 0)"
    assert hit, "governed_runner.py 缺少 minute_loader 本地 import"


def test_wired_empty_lake_byte_identical_to_unwired(tmp_path):
    """token empty: 生产形接线 (make_minute_loader(tmp_path) == 两构造点注入的同一工厂) vs
    minute_loader=None 基线 — 同一 tmp_path/策略目录/日线 fixture, required+optional 双策略
    逐字段一致 (strategy_id/total/rows/scores, elapsed_ms 时序字段除外);
    补缺分区态: 湖有分区但 date={as_of} 缺席 → 工厂缺分区空帧路径 == 未接线路径。"""
    from app.services.minute_loader import make_minute_loader

    _write_strategy(tmp_path, "minute_req.py", _MINUTE_REQ_BODY)
    _write_strategy(tmp_path, "minute_opt.py", _MINUTE_OPT_BODY)
    daily = pl.DataFrame({"symbol": ["600001", "600002"], "open_gap": [0.03, 0.04]})
    kwargs = {
        "context": _ctx(date(2026, 8, 4), precomputed=daily),
        "overrides": {"basic_filter": {"enabled": False}},
    }

    def _assert_byte_identical(wired_engine, baseline_engine):
        for sid in ("minute_req", "minute_opt"):
            r_wired = wired_engine.run(sid, **kwargs)
            r_base = baseline_engine.run(sid, **kwargs)
            # 逐字段一致 (elapsed_ms 时序字段除外) — MN-02 空湖字节保持
            assert r_wired.as_of == r_base.as_of
            assert r_wired.strategy_id == r_base.strategy_id == sid
            assert r_wired.total == r_base.total
            assert r_wired.rows == r_base.rows
            assert r_wired.scores == r_base.scores
            if sid == "minute_req":
                assert r_wired.total == 0 and r_wired.rows == []
            else:
                assert r_wired.total == 2  # optional → 跳过确认保留日线核心池

    # 态 1: 空湖 (无 kline_minute) — required → 空 StrategyResult / optional → 跳过确认
    wired = _engine(minute_loader=make_minute_loader(tmp_path),
                    strategy_dirs=[tmp_path / "strategies"])
    baseline = _engine(minute_loader=None, strategy_dirs=[tmp_path / "strategies"])
    _assert_byte_identical(wired, baseline)

    # 态 2: 湖有分区 (date=2026-08-03) 但 as_of=2026-08-04 缺席 → 工厂缺分区空帧 == 未接线
    _write_partition(tmp_path, date(2026, 8, 3),
                     _minute_frame(["600001"], [dt_time(9, 30)]))
    wired2 = _engine(minute_loader=make_minute_loader(tmp_path),
                     strategy_dirs=[tmp_path / "strategies"])
    baseline2 = _engine(minute_loader=None, strategy_dirs=[tmp_path / "strategies"])
    _assert_byte_identical(wired2, baseline2)
