"""竞价复盘确定性装配服务 (REV-01/02/03) — 全验收单元测试。

Hermetic: 生产 import 放测试函数内 (仓库约定); ``kline_auction`` 分区 /
``premarket_results`` 预览由测试手工写盘; probe verdict 与 ``now`` 经注入点
固定 (确定性, 镜像 test_premarket_pool._fake_verdict 三态 + frozen now)。

覆盖 (Task 1-3 累计):
- REV-01: 无分区诚实 (no_auction_lake)、历史分区主闸门 (keep='last' 手算)、
  今日 probe×分区双闸门三态、probe 不参与历史闸门、JSON 可序列化。
- REV-02: Block 2 手算 (高开分布/均值/Top N)、pre_eod vs no_auction_lake
  判别 (注入 now × 管道调度)、窗口谓词回归锁 (09:31 连续竞价 bar 永不进面板)、
  render 确定性数据标记、enriched 缺失防御。
- REV-03: 族∩预览策略集 (custom 不入)、EOD 口径 join (R6 铁律) + n_missing、
  预览缺失 no_premarket_preview、display_limit 注记、pre-EOD change_pct 省略 +
  degraded 注记、resonance 聚合 + build_auction_slice 与 render 单源。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl
import pytest

FIXED_DATE = date(2026, 8, 6)


# ================================================================
# hermetic helpers (镜像 test_attach_auction_columns_range.py:24-47 +
# test_premarket_pool.py:_FakeRepo/_fake_verdict/_write_premarket_preview)
# ================================================================


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_attach_auction_columns_range:24-47)。"""
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


class _FakeRepo:
    """最小 repo 桩 (镜像 test_premarket_pool.py:61-107, 追加 get_enriched_range)。"""

    def __init__(self, data_dir, enriched=None, latest=None, instruments=None, range_panel=None):
        from types import SimpleNamespace

        self.store = SimpleNamespace(data_dir=data_dir)
        self._enriched = enriched
        self._latest = latest
        self._instruments = instruments if instruments is not None else pl.DataFrame()
        self._range_panel = range_panel

    def get_enriched_latest_asset(self, asset_type):
        return self._enriched, self._latest

    def get_instruments_asset(self, asset_type):
        return self._instruments

    def get_enriched_history(self, target_date, lookback_days):
        return None

    def get_enriched_range(self, start, end, symbols=None, columns=None):
        df = self._range_panel
        if df is None:
            return None
        df = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        return df.sort(["symbol", "date"])


def _make_enriched(symbols, open_gaps, as_of=FIXED_DATE):
    """enriched 帧 (open_gap 直接列; 读时计算语义由 fixture 预置, 镜像 _multi_day_panel)。"""
    rows = []
    for sym, gap in zip(symbols, open_gaps):
        rows.append({
            "symbol": sym,
            "name": f"名称{sym}",
            "date": as_of,
            "open": 10.0 * (1 + gap),
            "close": 10.0 * (1 + gap) + 0.1,
            "prev_close": 10.0,
            "volume": 100000.0,
            "amount": 1_000_000.0,
            "open_gap": gap,
            "change_pct": 0.02,
        })
    return pl.DataFrame(rows)


def _eod_frame(as_of=FIXED_DATE):
    """EOD enriched 帧 (change_pct/close/open 手算口径; open_gap 与预览同源)。"""
    return pl.DataFrame({
        "symbol": ["000001", "600000", "000002"],
        "name": ["平安银行", "浦发银行", "万科A"],
        "date": [as_of] * 3,
        "open": [10.0, 20.0, 30.0],
        "close": [10.6, 20.2, 29.5],
        "prev_close": [10.0, 20.0, 30.0],
        "volume": [100000.0, 200000.0, 300000.0],
        "amount": [1e6, 2e6, 3e6],
        "open_gap": [0.05, 0.02, 0.01],
        "change_pct": [0.06, 0.01, -0.017],
    })


def _multi_day_panel(start: date, days: int = 6) -> pl.DataFrame:
    """多日 enriched 面板: 2 symbols × 连续自然日, 确定性 volume (镜像 :89-130)。"""
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


def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    """手工写盘 kline_auction/date=YYYY-MM-DD/part.parquet (镜像 :42-58)。"""
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _auction_rows(trade_date, symbol_volume, n_rows=1, extra=None):
    """canonical 分区行: 09:16/09:20/09:25 窗口行 + extra 09:31 行变体。

    ``symbol_volume``: {symbol: (auction_volume, auction_amount)}; ``n_rows`` > 1 时
    同一 symbol 写多窗口行, 末行 = 09:25 最终撮合 (keep='last' 语义)。
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
    if extra:
        rows.extend(extra)
    return pl.DataFrame(rows)


def _fake_verdict(status: str, source: str | None = None) -> dict:
    """构造 AuctionProbeVerdict.to_dict 同形 dict (hermetic, 逐字镜像 test_premarket_pool.py:123-130)。"""
    return {
        "status": status,
        "source": source,
        "probed_at": "2026-08-06T09:26:00+00:00",
        "window": "09:15-09:25",
        "fallback": "open_gap",
        "detail": "hermetic verdict",
    }


def _write_premarket_preview(data_dir, today, payload):
    """经 persist_premarket_snapshot 写盘 (镜像 test_premarket_pool.py:476-490)。"""
    from app.services.premarket_snapshot import persist_premarket_snapshot

    persist_premarket_snapshot(data_dir, today.isoformat(), payload)


def _preview_payload(today):
    """可持久化的盘前预览 payload — 2 竞价族策略 + 1 非族策略 (REV-03 验收 1)。"""
    return {
        "as_of": today.isoformat(),
        "available": True,
        "window": "pre_open",
        "computed_at": "2026-08-06T09:26:00",
        "provisional": True,
        "degraded": False,
        "probe": _fake_verdict("available"),
        "strategy_version": "fingerprint-abc",
        "results": {
            "auction_bullish": {
                "total": 2,
                "as_of": today.isoformat(),
                "rows": [
                    {"symbol": "000001", "name": "平安银行", "open_gap": 0.05, "change_pct": 0.051,
                     "hit_factors": ["竞价多头", "盘前强势"]},
                    {"symbol": "600000", "name": "浦发银行", "open_gap": 0.02, "change_pct": 0.021,
                     "hit_factors": ["竞价多头"]},
                ],
            },
            "golden_230": {
                "total": 1,
                "as_of": today.isoformat(),
                "rows": [
                    {"symbol": "000002", "name": "万科A", "open_gap": 0.01, "change_pct": 0.012,
                     "hit_factors": ["金色两点半"]},
                ],
            },
            "custom_a": {
                "total": 1,
                "as_of": today.isoformat(),
                "rows": [
                    {"symbol": "300001", "name": "创业板票", "open_gap": 0.03, "change_pct": 0.031,
                     "hit_factors": ["自定义"]},
                ],
            },
        },
    }


# ================================================================
# Task 1 — REV-01/02 垂直切片: 无分区诚实 / Block 2 手算 / pre_eod / render / 防御 / probe
# ================================================================


def test_no_auction_partition_omits_block(repo_env):
    """REV-01: 无湖分区 → real 块缺席 + no_auction_lake + 全 JSON 可序列化。"""
    import json

    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    enriched = _make_enriched(["000001", "600000", "000002", "300001"], [0.01, 0.02, 0.05, 0.03])
    repo = _FakeRepo(data_dir, enriched=enriched, latest=FIXED_DATE)
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    result = build_auction_recap(repo, FIXED_DATE, now=now)
    assert result["as_of"] == FIXED_DATE.isoformat()
    assert result["data_completeness"] == "no_auction_lake"
    # 无湖 → real 块 present:false + 中文 note 含「湖」 (诚实省略, 非缺键伪造)
    blk = result["blocks"]["real_auction_activity"]
    assert blk["present"] is False
    assert "湖" in blk["note"]
    assert result["blocks"]["open_gap_snapshot"]["present"] is True
    json.dumps(result)  # 不抛 = 全 JSON 可序列化


def test_open_gap_snapshot_hand_computed(repo_env):
    """REV-02: Block 2 手算 — 高开分布 (≥2%/≥5%)、均值、Top N 带 name。"""
    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    enriched = _make_enriched(["000001", "600000", "000002", "300001"], [0.01, 0.02, 0.05, 0.03])
    repo = _FakeRepo(data_dir, enriched=enriched, latest=FIXED_DATE)
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    result = build_auction_recap(repo, FIXED_DATE, now=now)
    blk = result["blocks"]["open_gap_snapshot"]
    assert blk["present"] is True
    dist = blk["distribution"]
    assert dist["ge2_count"] == 3
    assert dist["ge2_pct"] == pytest.approx(0.75)
    assert dist["ge5_count"] == 1
    assert dist["ge5_pct"] == pytest.approx(0.25)
    assert blk["high_open_count"] == 3
    assert blk["mean_open_gap"] == pytest.approx(0.0275)
    assert [t["open_gap"] for t in blk["top_n"][:2]] == pytest.approx([0.05, 0.03])
    assert all(t.get("name") for t in blk["top_n"])
    assert "kline_daily_enriched" in blk["source"]


def test_pre_eod_vs_no_auction_lake_discrimination(repo_env):
    """REV-02: pre_eod 判别 — 今日早于管道调度 vs 已过同步点 vs 历史日永不 pre_eod。"""
    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    enriched = _make_enriched(["000001", "600000"], [0.01, 0.02])
    repo = _FakeRepo(data_dir, enriched=enriched, latest=FIXED_DATE)

    # 今日 15:00 (< 15:30 管道调度) + 无分区 → pre_eod
    now_pre = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 15, 0)
    assert build_auction_recap(repo, FIXED_DATE, now=now_pre)["data_completeness"] == "pre_eod"

    # 今日 15:40 (已过同步点) + 无分区 → no_auction_lake
    now_post = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 15, 40)
    assert build_auction_recap(repo, FIXED_DATE, now=now_post)["data_completeness"] == "no_auction_lake"

    # 历史日 + 15:00 → 永不 pre_eod (只有 no_auction_lake)
    hist = FIXED_DATE - timedelta(days=1)
    repo_hist = _FakeRepo(data_dir, enriched=_make_enriched(["000001"], [0.01]), latest=hist)
    now_hist = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 15, 0)
    assert build_auction_recap(repo_hist, hist, now=now_hist)["data_completeness"] == "no_auction_lake"


def test_render_markdown_contains_deterministic_marker(repo_env):
    """REV-02: render 纯函数含「确定性数据，非 AI 生成」标记; 任意缺块 panel 不抛。"""
    from app.services.auction_recap import build_auction_recap, render_auction_recap_markdown

    _repo, data_dir = repo_env
    enriched = _make_enriched(["000001", "600000"], [0.01, 0.05])
    repo = _FakeRepo(data_dir, enriched=enriched, latest=FIXED_DATE)
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    panel = build_auction_recap(repo, FIXED_DATE, now=now)
    md = render_auction_recap_markdown(panel)
    assert "确定性数据，非 AI 生成" in md
    assert "开盘涨幅快照" in md
    assert "数据来源:冻结资产" in md

    # 任意缺块 panel 不抛 (纯函数)
    md2 = render_auction_recap_markdown({"as_of": "2026-08-06", "blocks": {}})
    assert isinstance(md2, str) and md2


def test_enriched_missing_defensive(repo_env):
    """REV-02: enriched 空帧 → open_gap_snapshot present:false + 显式 note (防御分支)。"""
    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    repo = _FakeRepo(data_dir, enriched=pl.DataFrame(), latest=FIXED_DATE)
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    result = build_auction_recap(repo, FIXED_DATE, now=now)
    blk = result["blocks"]["open_gap_snapshot"]
    assert blk["present"] is False
    assert blk["note"]
    assert blk["source"]


def test_probe_does_not_affect_history_gate(repo_env):
    """REV-01: 历史 as_of 下 probe 状态不影响闸门与块内容 (probe 仅 provenance)。"""
    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    hist = FIXED_DATE - timedelta(days=1)
    repo = _FakeRepo(data_dir, enriched=_make_enriched(["000001"], [0.01]), latest=hist)
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    r_avail = build_auction_recap(repo, hist, now=now, probe_resolver=lambda: _fake_verdict("available"))
    r_not = build_auction_recap(repo, hist, now=now, probe_resolver=lambda: _fake_verdict("not_configured"))
    assert r_avail["data_completeness"] == r_not["data_completeness"] == "no_auction_lake"
    assert r_avail["blocks"]["open_gap_snapshot"] == r_not["blocks"]["open_gap_snapshot"]


# ================================================================
# Task 2 — Block 1 real_auction_activity: 湖分区读 + 窗口谓词回归锁 + 双闸门 + 量比
# ================================================================


def test_history_partition_block_present(repo_env):
    """REV-01: 历史分区 → 块 present; keep='last' 手算 (总额 = 09:25 行之和, 非全窗口)。"""
    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    hist = FIXED_DATE - timedelta(days=1)
    enriched = _make_enriched(["000001", "600000"], [0.01, 0.02], as_of=hist)
    instruments = pl.DataFrame({
        "symbol": ["000001", "600000"],
        "name": ["平安银行", "浦发银行"],
    })
    repo = _FakeRepo(data_dir, enriched=enriched, latest=hist, instruments=instruments)
    _write_auction_partition(
        data_dir, hist,
        _auction_rows(hist, {"000001": (8000.0, 42000.0), "600000": (9000.0, 48000.0)}, n_rows=3),
    )
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    result = build_auction_recap(repo, hist, now=now)
    blk = result["blocks"]["real_auction_activity"]
    assert blk["present"] is True
    assert blk["n_symbols"] == 2
    # keep='last' 语义: 两 symbol 09:25 行金额之和 (非 6 窗口行之和)
    assert blk["total_amount"] == pytest.approx(42000.0 + 48000.0)
    assert blk["top_n"][0]["symbol"] == "600000"
    assert blk["top_n"][0]["name"] == "浦发银行"
    assert blk["source"] == "kline_auction"


def test_window_predicate_excludes_0931_continuous_bar(repo_env):
    """REV-02 验收 2: 09:31 连续竞价 bar 永不进竞价列 (读侧窗口谓词回归锁)。"""
    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    hist = FIXED_DATE - timedelta(days=1)
    enriched = _make_enriched(["000001", "600000"], [0.01, 0.02], as_of=hist)
    instruments = pl.DataFrame({
        "symbol": ["000001", "600000"],
        "name": ["平安银行", "浦发银行"],
    })
    repo = _FakeRepo(data_dir, enriched=enriched, latest=hist, instruments=instruments)
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    # A: 09:16/09:25 窗口行; B: 09:31 连续竞价 bar → A 入块 (取 09:25 值), B 缺席
    rows = pl.DataFrame({
        "symbol": ["000001", "000001", "600000"],
        "datetime": [
            datetime(hist.year, hist.month, hist.day, 9, 16),
            datetime(hist.year, hist.month, hist.day, 9, 25),
            datetime(hist.year, hist.month, hist.day, 9, 31),
        ],
        "auction_volume": [100.0, 200.0, 50.0],
        "auction_amount": [100.0, 200.0, 999.0],
    })
    _write_auction_partition(data_dir, hist, rows)
    blk = build_auction_recap(repo, hist, now=now)["blocks"]["real_auction_activity"]
    assert blk["present"] is True
    assert blk["n_symbols"] == 1
    assert blk["top_n"][0]["symbol"] == "000001"
    assert blk["top_n"][0]["auction_amount"] == pytest.approx(200.0)

    # 仅含 09:31 行的分区变体 → 窗口内零行 → 块诚实空 (present:false)
    rows_0931 = pl.DataFrame({
        "symbol": ["600000"],
        "datetime": [datetime(hist.year, hist.month, hist.day, 9, 31)],
        "auction_volume": [50.0],
        "auction_amount": [999.0],
    })
    _write_auction_partition(data_dir, hist, rows_0931)
    blk2 = build_auction_recap(repo, hist, now=now)["blocks"]["real_auction_activity"]
    assert blk2["present"] is False
    assert blk2["note"]


def test_today_double_gate_probe_x_partition(repo_env):
    """REV-01: 今日 as_of → probe×分区双闸门三态。"""
    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    enriched = _make_enriched(["000001"], [0.01])
    repo = _FakeRepo(data_dir, enriched=enriched, latest=FIXED_DATE)
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    # (a) probe available + 分区存在 → present
    _write_auction_partition(data_dir, FIXED_DATE, _auction_rows(FIXED_DATE, {"000001": (300.0, 500.0)}))
    blk_a = build_auction_recap(
        repo, FIXED_DATE, now=now, probe_resolver=lambda: _fake_verdict("available"),
    )["blocks"]["real_auction_activity"]
    assert blk_a["present"] is True
    assert "probe" in blk_a  # 今日透传 provenance

    # (b) probe 非 available + 分区存在 → present:false (镜像 attach_auction_columns :105-108)
    blk_b = build_auction_recap(
        repo, FIXED_DATE, now=now, probe_resolver=lambda: _fake_verdict("not_configured"),
    )["blocks"]["real_auction_activity"]
    assert blk_b["present"] is False

    # (c) probe available + 分区缺失 → present:false + 头标签 no_auction_lake
    fresh_dir = data_dir.parent / "fresh"
    fresh_dir.mkdir(parents=True, exist_ok=True)
    repo_c = _FakeRepo(fresh_dir, enriched=enriched, latest=FIXED_DATE)
    result_c = build_auction_recap(
        repo_c, FIXED_DATE, now=now, probe_resolver=lambda: _fake_verdict("available"),
    )
    assert result_c["blocks"]["real_auction_activity"]["present"] is False
    assert result_c["data_completeness"] == "no_auction_lake"


def test_ratio_subblock_reuses_attach_columns_range(repo_env):
    """R11 优先路径: 量比分母复用 attach_auction_columns_range (手算 300/120000)。"""
    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    enriched = _make_enriched(["000001", "600000"], [0.01, 0.02])
    instruments = pl.DataFrame({
        "symbol": ["000001", "600000"],
        "name": ["平安银行", "浦发银行"],
    })
    range_panel = _multi_day_panel(FIXED_DATE - timedelta(days=5), days=6)
    repo = _FakeRepo(
        data_dir, enriched=enriched, latest=FIXED_DATE,
        instruments=instruments, range_panel=range_panel,
    )
    _write_auction_partition(
        data_dir, FIXED_DATE,
        _auction_rows(FIXED_DATE, {"000001": (300.0, 150000.0), "600000": (200.0, 100000.0)}, n_rows=3),
    )
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    blk = build_auction_recap(
        repo, FIXED_DATE, now=now, probe_resolver=lambda: _fake_verdict("available"),
    )["blocks"]["real_auction_activity"]
    ratio = blk["ratio_subblock"]
    assert ratio["present"] is True
    assert ratio["values"]
    # 前 5 日均量: (100000+110000+120000+130000+140000)/5 = 120000 → 300/120000
    assert blk["top_n"][0]["auction_volume_ratio"] == pytest.approx(300.0 / 120000.0)

    # 分母不可得 (get_enriched_range None) → 子块省略 + 注记, 绝不 0 填
    repo_no_range = _FakeRepo(data_dir, enriched=enriched, latest=FIXED_DATE, instruments=instruments)
    blk2 = build_auction_recap(
        repo_no_range, FIXED_DATE, now=now, probe_resolver=lambda: _fake_verdict("available"),
    )["blocks"]["real_auction_activity"]
    assert blk2["ratio_subblock"]["present"] is False
    assert "分母" in blk2["ratio_subblock"]["note"]


def test_json_safe_nan_auction_amount(repo_env):
    """JSON 安全: 分区含 NaN auction_amount → json.dumps 不抛且序列化为 null。"""
    import json

    from app.services.auction_recap import build_auction_recap

    _repo, data_dir = repo_env
    hist = FIXED_DATE - timedelta(days=1)
    enriched = _make_enriched(["000001"], [0.01], as_of=hist)
    repo = _FakeRepo(data_dir, enriched=enriched, latest=hist)
    rows = pl.DataFrame({
        "symbol": ["000001"],
        "datetime": [datetime(hist.year, hist.month, hist.day, 9, 25)],
        "auction_volume": [300.0],
        "auction_amount": [float("nan")],
    })
    _write_auction_partition(data_dir, hist, rows)
    now = datetime(FIXED_DATE.year, FIXED_DATE.month, FIXED_DATE.day, 16, 0)

    result = build_auction_recap(repo, hist, now=now)
    blk = result["blocks"]["real_auction_activity"]
    assert blk["present"] is True
    assert blk["total_amount"] is None
    assert blk["top_n"][0]["auction_amount"] is None
    json.dumps(result)  # 不抛
