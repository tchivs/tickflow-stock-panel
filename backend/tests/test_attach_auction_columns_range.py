"""区间竞价列注入原语 ``attach_auction_columns_range`` (BT-02) — 端到端注入 / 空态 /
date 键 / PIT-safe 等价性属性 / warmup / 边界。

Hermetic: 所有生产 import 放测试函数内 (仓库约定: 模块级不触发 DuckDB 单例);
``kline_auction`` 分区由测试手工写盘; 等价性比较时用 monkeypatch 固定 probe verdict
(仅单日版路径消费 probe); 区间原语**不消费 probe** (历史闸门 = 分区存在性, D-03 / REV-01)。

等价性证明前提 (RESEARCH §2.1.3): 面板 volume 与 ``repo._enriched_history_cache``
同源 —— 测试直接 seed 缓存并以其为面板; 生产侧由服务层 ``get_enriched_range``
快路径装载保证 (29-02 契约)。等价性断言只用于 ≥5 前导行的全面板输入 (W2);
1-4 日前导短历史用 hand-computed 均值断言, 不做 <1e-9 面板裁剪比较。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl
import pytest


# ================================================================
# hermetic helpers (镜像 test_auction_columns.py repo_env / _write_auction_partition)
# ================================================================


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_auction_columns.py:20-32)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    repo = KlineRepository(store)
    try:
        yield repo, data_dir
    finally:
        store.db.close()


def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    """手工写盘 kline_auction/date=YYYY-MM-DD/part.parquet (镜像 :54-58)。"""
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _multi_day_panel(start: date, days: int = 5) -> pl.DataFrame:
    """多日 enriched 面板: 2 symbols × 连续自然日 (测试即交易日), 确定性 volume。

    volume(第 i 日) = 100000 × (1 + i × 0.1) → 前导日均量可手算 (W2: 1-4 日前导短历史
    用 hand-computed 断言, 不做 <1e-9 面板裁剪等价比较)。
    """
    rows = []
    for i in range(days):
        d = start + timedelta(days=i)
        vol = 100000.0 * (1 + i * 0.1)
        for sym in ("000001", "600000"):
            rows.append({
                "symbol": sym,
                "date": d,
                "open": 10.0 if sym == "000001" else 20.0,
                "close": 10.5 if sym == "000001" else 20.5,
                "volume": vol,
                "amount": vol * 10.0,
                "open_gap": 0.01,
                "change_pct": 0.02,
                "vol_ratio_5d": 1.0,
            })
    return pl.DataFrame(rows)


def _auction_rows(
    trade_date: date,
    symbol_volume: dict[str, tuple[float, float]],
    n_rows: int = 1,
) -> pl.DataFrame:
    """canonical 四列 (symbol, datetime, auction_volume, auction_amount)。

    ``symbol_volume``: {symbol: (auction_volume, auction_amount)}; ``n_rows`` > 1 时
    同一 symbol 写多窗口行 (09:16/09:20/09:25 形), 末行 = 09:25 最终撮合 (keep="last" 语义)。
    """
    _WINDOW_MINUTES = (16, 20, 25)
    rows = []
    for sym, (av, aa) in symbol_volume.items():
        for k in range(n_rows):
            rows.append({
                "symbol": sym,
                "datetime": datetime(trade_date.year, trade_date.month, trade_date.day, 9, _WINDOW_MINUTES[k]),
                "auction_volume": av,
                "auction_amount": aa,
            })
    return pl.DataFrame(rows)


# ================================================================
# Task 1 — Test 1: 端到端注入 (BT-02 主路径, tracer 垂直切片)
# ================================================================


def test_range_end_to_end_injection(repo_env):
    """多分区注入 + enabled_dates + warmup 裁剪 + 无分区日诚实空值。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env

    # 面板: 07-27..08-01 (6 日, 含 start=07-29 前 2 个 warmup 前导 + 1 个无分区日 08-01)
    panel = _multi_day_panel(start=date(2026, 7, 27), days=6)

    # 分区: 07-29 (A 2 窗口行 / B 1 行), 07-30 (各 1 行), 07-31 (A 3 窗口行 / B 1 行)
    _write_auction_partition(
        data_dir, date(2026, 7, 29),
        _auction_rows(date(2026, 7, 29), {"000001": (8000.0, 42000.0), "600000": (9000.0, 48000.0)}, n_rows=2),
    )
    _write_auction_partition(
        data_dir, date(2026, 7, 30),
        _auction_rows(date(2026, 7, 30), {"000001": (8100.0, 42500.0), "600000": (9100.0, 48500.0)}),
    )
    _write_auction_partition(
        data_dir, date(2026, 7, 31),
        _auction_rows(date(2026, 7, 31), {"000001": (8200.0, 43000.0), "600000": (9200.0, 49000.0)}, n_rows=3),
    )

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    # enabled_dates = 排序去重的非空分区日 (08-01 无分区 → 不在其中)
    assert enabled_dates == [date(2026, 7, 29), date(2026, 7, 30), date(2026, 7, 31)]

    # warmup 裁剪: 注入后无 date < start 行 (07-27/07-28 仅供分母, 不出现在结果)
    assert injected["date"].min() >= date(2026, 7, 29)
    assert injected.height == 4 * 2  # 07-29..08-01 × 2 symbols, 无 fan-out

    # 注入日带真实竞价列 + 派生 ratio 列
    for col in ("auction_volume", "auction_amount", "auction_volume_ratio"):
        assert col in injected.columns

    # 多窗口行去重: 07-31 A 取 09:25 末行值
    a0731 = injected.filter(
        (pl.col("symbol") == "000001") & (pl.col("date") == date(2026, 7, 31))
    )
    assert a0731.height == 1
    assert a0731.select("auction_amount").item() == 43000.0

    # 无分区日 (08-01) → auction 列 null (诚实按日空态, 绝无 null-as-present)
    aug01 = injected.filter(pl.col("date") == date(2026, 8, 1))
    assert aug01.height == 2
    assert aug01.select(pl.col("auction_volume").null_count()).item() == 2
    assert aug01.select(pl.col("auction_volume_ratio").null_count()).item() == 2

    # 首个 enabled 日 (07-29) ratio = 竞价量 ÷ 前 2 日 volume 均值 (hand-computed, W2)
    # 前导: 07-27 vol=100000, 07-28 vol=110000 → 均值 105000
    a0729 = injected.filter(
        (pl.col("symbol") == "000001") & (pl.col("date") == date(2026, 7, 29))
    )
    assert a0729.select("auction_volume_ratio").item() == pytest.approx(8000.0 / 105000.0, rel=1e-9)
    b0729 = injected.filter(
        (pl.col("symbol") == "600000") & (pl.col("date") == date(2026, 7, 29))
    )
    assert b0729.select("auction_volume_ratio").item() == pytest.approx(9000.0 / 105000.0, rel=1e-9)


# ================================================================
# Task 1 — Test 2: 空态 (平台铁律: 绝无异常 / 绝无 null-as-present)
# ================================================================


def test_range_empty_lake_returns_df_and_empty_dates(repo_env):
    """无 kline_auction 目录 → (df, []), 面板原样返回, 无 auction 列。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == []
    assert "auction_volume" not in injected.columns
    assert injected.height == panel.height
    # 函数防御性 sort(["symbol","date"]) → 顺序与输入可能不同; 集合语义相等即可
    assert sorted(injected["symbol"].to_list()) == sorted(panel["symbol"].to_list())


def test_range_no_partitions_returns_df_and_empty_dates(repo_env):
    """目录存在但无 date=* 分区 → (df, [])."""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    (data_dir / "kline_auction").mkdir(parents=True, exist_ok=True)
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == []
    assert "auction_volume" not in injected.columns


def test_range_empty_panel_returns_df_and_empty_dates(repo_env):
    """df 为空 → (df, []) 绝无异常。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    _write_auction_partition(
        data_dir, date(2026, 7, 29),
        _auction_rows(date(2026, 7, 29), {"000001": (8000.0, 42000.0)}),
    )

    empty = pl.DataFrame()
    injected, enabled_dates = attach_auction_columns_range(
        empty, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == []
    assert injected.height == 0


# ================================================================
# Task 1 — Test 3: date 列键 (分区帧无 date 列 → join 键 ["symbol","date"] 有效)
# ================================================================


def test_range_date_key_join_no_fanout(repo_env):
    """canonical 4 列分区 (无 date 列) → date 取自分区目录名, join 基数 = 面板行数。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    # 单分区 2 行/symbol (多窗口行) — 去重后每 (symbol, date) 仅 1 行 → 无 fan-out
    _write_auction_partition(
        data_dir, date(2026, 7, 30),
        _auction_rows(date(2026, 7, 30), {"000001": (8100.0, 42500.0), "600000": (9100.0, 48500.0)}, n_rows=2),
    )

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == [date(2026, 7, 30)]
    assert injected.height == panel.height  # 行基数不变
    assert injected.filter(pl.col("date") == date(2026, 7, 30)).height == 2
    # 注入值 = 末行 (n_rows=2 → datetime 09:16/09:20, keep="last" = 09:20 行值)
    a0730 = injected.filter(
        (pl.col("symbol") == "000001") & (pl.col("date") == date(2026, 7, 30))
    )
    assert a0730.height == 1
    assert a0730.select("auction_amount").item() == 42500.0


# ================================================================
# Task 2 — 等价性属性测试 (BT-02 核心验收): 向量化分母与单日版逐值一致
# ================================================================


def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available, source="fake", probed_at=None, detail="available",
    )


def _patch_probe(monkeypatch, verdict) -> None:
    from app.services import auction_columns
    monkeypatch.setattr(auction_columns, "resolve_auction_probe", lambda: verdict)


def _seed_enriched_cache(repo, symbols=("000001", "600000"), days: int = 139,
                         start: date | None = None) -> pl.DataFrame:
    """直接 seed ``repo._enriched_history_cache`` (与 get_enriched_range 快路径同源, RESEARCH §2.1.3)。

    默认 2026-03-20..2026-08-05 (139 连续自然日) —— 覆盖 ``get_enriched_history``
    的 132 自然日 warmup-start 校验 ((6+60)×2, repository.py:945-948): 07-30 − 132 自然日
    = 03-20 = cache_min (边界恰好通过)。volume 确定性: 100000 × (1 + (day_index % 7) × 0.1)
    → 前导均量可手算。
    """
    from datetime import timedelta
    start = start or date(2026, 3, 20)
    rows = []
    for i in range(days):
        d = start + timedelta(days=i)
        vol = 100000.0 * (1 + (i % 7) * 0.1)
        for sym in symbols:
            rows.append({
                "symbol": sym,
                "date": d,
                "open": 10.0 if sym == "000001" else 20.0,
                "close": 10.5 if sym == "000001" else 20.5,
                "high": 10.6 if sym == "000001" else 20.6,
                "low": 9.9 if sym == "000001" else 19.9,
                "volume": vol,
                "amount": vol * 10.0,
                "open_gap": 0.01,
                "change_pct": 0.02,
                "vol_ratio_5d": 1.0,
            })
    repo._enriched_history_cache = pl.DataFrame(rows)
    return repo._enriched_history_cache


def _five_day_partitions(data_dir, start: date = date(2026, 7, 30)) -> list[date]:
    """07-30..08-03 五日分区, 双 symbol, 逐日递增竞价量 (确定性)。"""
    dates = [start + timedelta(days=i) for i in range(5)]
    for i, d in enumerate(dates):
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {
                "000001": (8000.0 + 100.0 * i, 42000.0 + 500.0 * i),
                "600000": (9000.0 + 100.0 * i, 48000.0 + 500.0 * i),
            }),
        )
    return dates


def test_range_ratio_equivalent_to_single_day(repo_env, monkeypatch):
    """每个 enabled 日 (≥5 前导行, 全面板输入, W2) 向量化 ratio 与单日版逐值一致 <1e-9。"""
    from app.services.auction_columns import attach_auction_columns, attach_auction_columns_range

    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())  # 仅单日路径消费 probe

    full_panel = _seed_enriched_cache(repo)  # 140 日 2026-03-20..2026-08-05
    dates = _five_day_partitions(data_dir)   # 07-30..08-03 全量分区
    start, end = dates[0], dates[-1]

    ranged_df, enabled_dates = attach_auction_columns_range(
        full_panel, start=start, end=end, repo=repo,
    )
    assert enabled_dates == dates  # 全 5 日 enabled

    for d in enabled_dates:
        # 单日分母契约 (repository.py:951-957): get_enriched_history 以**整缓存**
        # trading_dates[-(lookback+1)] 为切片锚点, 只有 T ∈ {cache_max−1, cache_max}
        # 时切片才等于「T 前 6 个交易日」→ tail(5) = T 前 5 行。逐日把缓存裁剪到 ≤ d
        # (缓存与面板同源同前导行 —— W2 前提), 则每个 enabled 日均可逐值比较。
        repo._enriched_history_cache = full_panel.filter(pl.col("date") <= d)
        panel_d = full_panel.filter(pl.col("date") == d)
        single = attach_auction_columns(panel_d, d, repo)
        assert "auction_volume_ratio" in single.columns  # 缓存覆盖 → 单日有 ratio

        ranged_d = ranged_df.filter(pl.col("date") == d)
        assert ranged_d.height == panel_d.height == 2
        merged = single.join(
            ranged_d.select(["symbol", "date", "auction_volume_ratio"]),
            on=["symbol", "date"], how="inner", suffix="_ranged",
        )
        assert merged.height == 2
        for row in merged.to_dicts():
            assert abs(row["auction_volume_ratio"] - row["auction_volume_ratio_ranged"]) < 1e-9, (
                f"ratio mismatch on {d} {row['symbol']}: "
                f"single={row['auction_volume_ratio']} ranged={row['auction_volume_ratio_ranged']}"
            )


def test_range_leading_no_history_honest_null(repo_env, monkeypatch):
    """面板首日 (组内无前导行): 单日路径 prior 空 → ratio 列缺席; 向量化路径 ratio
    列存在但值为 null —— 二者均不产生真实比率值且不崩 (诚实 null ≈ 诚实缺列,
    该行真实分支 filter 不命中)。有意差异注释见 RESEARCH §2.1.3。"""
    from app.services.auction_columns import attach_auction_columns, attach_auction_columns_range

    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())

    # 短缓存自 07-30 起: get_enriched_history 132 日 warmup 闸门不满足 → 单日 prior 空
    panel = _seed_enriched_cache(repo, days=5, start=date(2026, 7, 30))
    _write_auction_partition(
        data_dir, date(2026, 7, 30),
        _auction_rows(date(2026, 7, 30), {"000001": (8000.0, 42000.0), "600000": (9000.0, 48000.0)}),
    )
    _write_auction_partition(
        data_dir, date(2026, 7, 31),
        _auction_rows(date(2026, 7, 31), {"000001": (8100.0, 42500.0), "600000": (9100.0, 48500.0)}),
    )

    # 向量化路径: ratio 列存在; 组内首日 (07-30) null; 07-31 (1 前导) 有真实比率 (手算)
    ranged_df, enabled = attach_auction_columns_range(
        panel, start=date(2026, 7, 30), end=date(2026, 7, 31), repo=repo,
    )
    assert enabled == [date(2026, 7, 30), date(2026, 7, 31)]
    assert "auction_volume_ratio" in ranged_df.columns
    d0730 = ranged_df.filter(pl.col("date") == date(2026, 7, 30))
    assert d0730.select(pl.col("auction_volume_ratio").null_count()).item() == 2
    d0731 = ranged_df.filter(pl.col("date") == date(2026, 7, 31))
    assert d0731.select(pl.col("auction_volume_ratio").null_count()).item() == 0
    # 07-31 前导 = 07-30 volume = 100000 (day_index 0) → 8100/100000
    assert (
        d0731.filter(pl.col("symbol") == "000001").select("auction_volume_ratio").item()
        == pytest.approx(8100.0 / 100000.0, rel=1e-9)
    )

    # 单日路径: prior 空 (get_enriched_history None) → ratio 列缺席, 不崩
    single = attach_auction_columns(
        panel.filter(pl.col("date") == date(2026, 7, 30)), date(2026, 7, 30), repo,
    )
    assert "auction_volume_ratio" not in single.columns


def test_range_warmup_contract_full_denominator(repo_env):
    """面板含 start 前 5 个交易日行 → 首个 enabled 日 ratio = 竞价量 ÷ 手算前 5 日均量。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    full_panel = _seed_enriched_cache(repo)  # 07-30 前有 127 前导日 (≥5)
    start = date(2026, 7, 30)
    _write_auction_partition(
        data_dir, start,
        _auction_rows(start, {"000001": (8000.0, 42000.0), "600000": (9000.0, 48000.0)}),
    )

    ranged_df, enabled = attach_auction_columns_range(
        full_panel, start=start, end=start, repo=repo,
    )
    assert enabled == [start]

    for sym, av in (("000001", 8000.0), ("600000", 9000.0)):
        prior_vols = full_panel.filter(
            (pl.col("symbol") == sym) & (pl.col("date") < start)
        ).tail(5)["volume"].to_list()
        assert len(prior_vols) == 5
        expected = av / (sum(prior_vols) / 5.0)
        row = ranged_df.filter((pl.col("symbol") == sym) & (pl.col("date") == start))
        assert row.select("auction_volume_ratio").item() == pytest.approx(expected, rel=1e-9)


def test_range_no_warmup_leading_null_honest(repo_env):
    """面板裁剪掉 warmup (df 从 start 起) → 前导日 ratio null, 不崩 (RESEARCH §2.1.4 降级)。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    full_panel = _seed_enriched_cache(repo)
    panel_no_warmup = full_panel.filter(pl.col("date") >= date(2026, 7, 30))
    start = date(2026, 7, 30)
    _write_auction_partition(
        data_dir, start,
        _auction_rows(start, {"000001": (8000.0, 42000.0), "600000": (9000.0, 48000.0)}),
    )

    ranged_df, enabled = attach_auction_columns_range(
        panel_no_warmup, start=start, end=date(2026, 7, 31), repo=repo,
    )
    assert enabled == [start]
    d0730 = ranged_df.filter(pl.col("date") == start)
    assert d0730.select(pl.col("auction_volume_ratio").null_count()).item() == 2
    # 07-31 无分区 → auction_volume null → ratio null (诚实), 不崩
    assert ranged_df.filter(pl.col("date") == date(2026, 7, 31)).select(
        pl.col("auction_volume_ratio").null_count()
    ).item() == 2


# ================================================================
# Task 3 — 边界健壮性: 空分区 / 坏目录名 / fan-out 去重 / 按标的缺席 / 派生列
# ================================================================


def test_range_bad_dir_and_empty_partition_skipped(repo_env):
    """date=bad 目录 + 空分区 (0 行) → 跳过, 不进 enabled_dates, 其余分区正常注入。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    # 坏目录名: date=bad (解析失败跳过, T-29-01-01)
    bad = data_dir / "kline_auction" / "date=bad"
    bad.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"symbol": ["X"]}).write_parquet(bad / "part.parquet")

    # 空分区: date=2026-07-29 (0 行, 镜像单日版 :119-121 跳过)
    empty = data_dir / "kline_auction" / "date=2026-07-29"
    empty.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(schema={
        "symbol": pl.Utf8, "datetime": pl.Datetime, "auction_volume": pl.Float64,
        "auction_amount": pl.Float64,
    }).write_parquet(empty / "part.parquet")

    # 正常分区: date=2026-07-30
    _write_auction_partition(
        data_dir, date(2026, 7, 30),
        _auction_rows(date(2026, 7, 30), {"000001": (8100.0, 42500.0), "600000": (9100.0, 48500.0)}),
    )

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == [date(2026, 7, 30)]  # bad + empty 均不在 enabled_dates
    assert injected.height == panel.height
    d0730 = injected.filter(pl.col("date") == date(2026, 7, 30))
    assert d0730.select("auction_volume").null_count().item() == 0  # 正常分区照常注入


def test_range_fanout_dedup_keeps_last_row(repo_env):
    """单日分区 3 行同 symbol 不同窗口 (09:16/09:20/09:25) → 注入后单行, 值 = 末行 (09:25)。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    # 每窗口行带不同值 → 可断言 keep="last" 取 09:25 (T-29-01-04)
    rows = pl.DataFrame({
        "symbol": ["000001", "000001", "000001", "600000"],
        "datetime": [
            datetime(2026, 7, 30, 9, 16),
            datetime(2026, 7, 30, 9, 20),
            datetime(2026, 7, 30, 9, 25),
            datetime(2026, 7, 30, 9, 25),
        ],
        "auction_volume": [100.0, 200.0, 300.0, 400.0],
        "auction_amount": [1000.0, 2000.0, 3000.0, 4000.0],
    })
    _write_auction_partition(data_dir, date(2026, 7, 30), rows)

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == [date(2026, 7, 30)]
    assert injected.height == panel.height  # 行基数不变
    d0730 = injected.filter(pl.col("date") == date(2026, 7, 30))
    assert d0730.height == 2  # 每 symbol 仅 1 行
    a = d0730.filter(pl.col("symbol") == "000001")
    assert a.height == 1
    assert a.select("auction_volume").item() == 300.0   # 09:25 最终撮合
    assert a.select("auction_amount").item() == 3000.0
    b = d0730.filter(pl.col("symbol") == "600000")
    assert b.select("auction_volume").item() == 400.0


def test_range_per_symbol_absence_honest_null(repo_env):
    """分区含 A 无 B → B 行 auction_volume/amount/ratio 全 null (诚实按标的缺席)。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    _write_auction_partition(
        data_dir, date(2026, 7, 30),
        _auction_rows(date(2026, 7, 30), {"000001": (8100.0, 42500.0)}),  # 仅 A
    )

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == [date(2026, 7, 30)]
    d0730 = injected.filter(pl.col("date") == date(2026, 7, 30))
    b = d0730.filter(pl.col("symbol") == "600000")
    assert b.height == 1
    for col in ("auction_volume", "auction_amount", "auction_volume_ratio"):
        assert b.select(pl.col(col).null_count()).item() == 1  # B 缺席 → null
    a = d0730.filter(pl.col("symbol") == "000001")
    assert a.select("auction_volume").item() == 8100.0  # A 正常注入 (非整日 null-as-present)


def test_range_derived_unmatched_amount_injected_when_inputs_present(repo_env):
    """分区含委托量输入列 → 注入 auction_unmatched_amount == 量×价; 无输入列 → 不注入。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    # 6 列新分区 (4 真实 + 2 委托量输入): 5000 股 × 12.5 元 = 62500 元
    rows = pl.DataFrame({
        "symbol": ["000001", "600000"],
        "datetime": [datetime(2026, 7, 30, 9, 25), datetime(2026, 7, 30, 9, 25)],
        "auction_volume": [8100.0, 9100.0],
        "auction_amount": [42500.0, 48500.0],
        "auction_unmatched_volume": [5000.0, 6000.0],
        "auction_virtual_price": [12.5, 13.0],
    })
    _write_auction_partition(data_dir, date(2026, 7, 30), rows)

    injected, _ = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )
    assert "auction_unmatched_amount" in injected.columns
    a = injected.filter(
        (pl.col("symbol") == "000001") & (pl.col("date") == date(2026, 7, 30))
    )
    assert a.select("auction_unmatched_amount").item() == pytest.approx(5000.0 * 12.5, rel=1e-9)

    # 4 列旧分区 (无输入列) → 不注入派生列 (诚实缺列, 绝不 0 填)
    _write_auction_partition(
        data_dir, date(2026, 7, 31),
        _auction_rows(date(2026, 7, 31), {"000001": (8200.0, 43000.0), "600000": (9200.0, 49000.0)}),
    )
    injected2, _ = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )
    assert "auction_unmatched_amount" in injected2.columns  # 07-30 有输入列分区, 列仍在
    # 07-31 该行派生列为 null (诚实按日无输入), 而非 0 填
    b0731 = injected2.filter(
        (pl.col("symbol") == "000001") & (pl.col("date") == date(2026, 7, 31))
    )
    assert b0731.select(pl.col("auction_unmatched_amount").null_count()).item() == 1


def test_range_no_warmup_no_crash(repo_env):
    """df 从 start 起 (无前导行) → 前导日 ratio null, 无异常 (RESEARCH §2.1.4 降级)。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)  # 07-29 无前导
    _write_auction_partition(
        data_dir, date(2026, 7, 29),
        _auction_rows(date(2026, 7, 29), {"000001": (8000.0, 42000.0), "600000": (9000.0, 48000.0)}),
    )
    _write_auction_partition(
        data_dir, date(2026, 7, 30),
        _auction_rows(date(2026, 7, 30), {"000001": (8100.0, 42500.0), "600000": (9100.0, 48500.0)}),
    )

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == [date(2026, 7, 29), date(2026, 7, 30)]
    d0729 = injected.filter(pl.col("date") == date(2026, 7, 29))
    assert d0729.select(pl.col("auction_volume_ratio").null_count()).item() == 2  # 组内首行 null
    d0730 = injected.filter(pl.col("date") == date(2026, 7, 30))
    # 07-30: 1 前导 (07-29) → 有真实比率 (hand-computed); 07-31 无分区 → ratio null
    assert d0730.select(pl.col("auction_volume_ratio").null_count()).item() == 0
    a0730 = d0730.filter(pl.col("symbol") == "000001")
    assert a0730.select("auction_volume_ratio").item() == pytest.approx(8100.0 / 100000.0, rel=1e-9)
