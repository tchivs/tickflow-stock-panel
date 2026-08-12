"""43-01 采集契约测试 (hermetic, 零网络, canned tick 夹具注入).

契约面 (43-01-PLAN):
- 端到端: 单 symbol 采集 → tick_staging/date={T}/part.parquet (10 列 TickBar 全保留) + manifest.json。
- 完整性 fail-closed 三拒: 昨日归属日 (Pitfall 3) / 缺 09:25 撮合行 / 窗口 <40 行 → 不落分区。
- 全失败 → 无 date= 分区 (绝不写半成品); 部分失败 → ok/failed 计数诚实 + manifest symbols_failed。
- 采集池 (A2): 配置白名单优先默认自选池; ≤200 硬 cap + 截断注记; 归一失败进 failed (不猜)。
- get_ticks 请求必带 date=T (Pitfall 3); 单次 GET 全窗口 (fetch-on-miss 语义, 无盘中轮询面)。

所有生产 import 延迟到测试函数内 (repo 约定: 集合期不碰 DuckDB 单例)。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

_FIXTURES = Path(__file__).parent / "fixtures" / "ticks"
_FIXTURE = "sh600519_20260807_window.json"

# staging 10 列 = TickBar 全字段保留 (顺序冻结, 与 auction_capture._STAGING_COLS 一致)
_STAGING_COLS = [
    "symbol", "trade_date", "time", "price", "vol_hand", "num_trades",
    "buyorsell", "source", "fetched_at", "ingested_at",
]


def _load_fixture(name: str = _FIXTURE) -> dict:
    """读夹具 JSON (冻结 2026-08-07 live 实测体)。"""
    with open(_FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


class _FakeTickProvider:
    """按 symbol 返回窗口子集; 记录 (symbol, trade_date) 调用 (断言请求必带 date=T)。"""

    def __init__(self, subsets: dict[str, str] | None = None, default: str = "window"):
        self._fixture = _load_fixture()
        self._subsets = subsets or {}
        self._default = default
        self.calls: list[tuple[str, date]] = []

    def get_ticks(self, symbol: str, trade_date: date):
        self.calls.append((symbol, trade_date))
        key = self._subsets.get(symbol, self._default)
        if key == "empty":
            return []
        return list(self._fixture[key])


@pytest.fixture
def capture_env(tmp_path, monkeypatch):
    """隔离的 data_dir (monkeypatch settings.data_dir) — 池解析/偏好种子共用。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    return data_dir


def _seed_whitelist(symbols: list[str]) -> None:
    from app.services import preferences
    preferences.save({"auction_sidecar_symbols": list(symbols)})


def _seed_watchlist(data_dir: Path, symbols: list[str]) -> None:
    """写 data/user_data/watchlist.parquet (自选池, 后缀形态)。"""
    path = data_dir / "user_data" / "watchlist.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"symbol": list(symbols), "as_of": ["2026-08-07"] * len(symbols)}).write_parquet(path)


def _manifest(data_dir: Path, trade_date: str = "2026-08-07") -> dict:
    p = data_dir / "tick_staging" / f"date={trade_date}" / "manifest.json"
    assert p.exists(), f"manifest missing: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


# ============================================================
# Task 1: 端到端 staging 10 列 + manifest / 完整性三拒
# ============================================================


def test_capture_single_symbol_writes_staging(capture_env):
    from app.services.auction_capture import capture_auction_window

    fake = _FakeTickProvider()
    result = capture_auction_window(fake, ["SH600519"], date(2026, 8, 7), capture_env)
    assert result == {"requested": 1, "ok": 1, "failed": []}
    assert fake.calls == [("SH600519", date(2026, 8, 7))]  # 请求必带 date=T (Pitfall 3)

    part = capture_env / "tick_staging" / "date=2026-08-07" / "part.parquet"
    assert part.exists()
    df = pl.read_parquet(part)
    assert df.columns == _STAGING_COLS  # 10 列 TickBar 全保留
    assert df.height == 87  # 全窗口逐条保留 (85 窗口 + 回显 + 重复撮合)
    m = df.filter(pl.col("time") == "09:25:00")
    assert len(m) == 1
    assert m["price"][0] == pytest.approx(1308.66)
    assert m["vol_hand"][0] == 173
    assert m["num_trades"][0] == 120
    assert m["buyorsell"][0] == 2
    assert m["symbol"][0] == "SH600519"

    manifest = _manifest(capture_env)
    for key in ("trade_date", "captured_at", "pool_size", "symbols_ok",
                "symbols_failed", "completeness"):
        assert key in manifest
    assert manifest["trade_date"] == "2026-08-07"
    assert manifest["pool_size"] == 1
    assert manifest["symbols_ok"] == ["SH600519"]
    assert manifest["completeness"]["ok"] is True


def test_validate_window_ok_metrics():
    from app.services.auction_capture import _validate_tick_window

    fixture = _load_fixture()
    check = _validate_tick_window(fixture["window"], "20260807")
    assert check["ok"] is True
    assert check["window_rows"] >= 40
    assert check["match_rows"] >= 1


def test_validate_window_rejects_wrong_trade_date():
    """归属日 != T fail-closed (Pitfall 3: 09:15 前请求回退上一交易日)。"""
    from app.services.auction_capture import _validate_tick_window

    fixture = _load_fixture()
    check = _validate_tick_window(fixture["yesterday"], "20260807")
    assert check["ok"] is False


def test_validate_window_rejects_missing_match_row():
    """窗口行齐全但无 09:25:00 num_trades>0 行 (全虚拟快照) → fail-closed。"""
    from app.services.auction_capture import _validate_tick_window

    fixture = _load_fixture()
    check = _validate_tick_window(fixture["no_match"], "20260807")
    assert check["ok"] is False


def test_validate_window_rejects_short_window():
    """窗口行数 < 40 → fail-closed (3s 快照级覆盖不足)。"""
    from app.services.auction_capture import _validate_tick_window

    fixture = _load_fixture()
    check = _validate_tick_window(fixture["short_window"], "20260807")
    assert check["ok"] is False


def test_validate_window_accepts_iso_trade_date():
    """服务端实测 ISO 形态 trade_date (``2026-08-07T00:00:00+08:00``) → 归属日==T 通过。

    回归: stockdb_provider.get_ticks 返回原始 JSON 未归一化, trade_date 为 ISO 带时区
    形态; 旧实现 ``str(...).startswith("YYYYMMDD")`` 恒 False → 采集必 0/6 (capture_all_failed),
    tick_staging 永不落盘。本测试锁定 ISO 形态可正常通过完整性校验。
    """
    from app.services.auction_capture import _validate_tick_window

    fixture = _load_fixture()
    rows = [dict(r, trade_date="2026-08-07T00:00:00+08:00") for r in fixture["window"]]
    check = _validate_tick_window(rows, "20260807")
    assert check["ok"] is True


def test_validate_window_rejects_iso_wrong_trade_date():
    """ISO 形态但归属日 != T → fail-closed (镜像 compact 语义, Pitfall 3)。"""
    from app.services.auction_capture import _validate_tick_window

    fixture = _load_fixture()
    rows = [dict(r, trade_date="2026-08-06T00:00:00+08:00") for r in fixture["window"]]
    check = _validate_tick_window(rows, "20260807")
    assert check["ok"] is False


def test_validate_window_rejects_mixed_trade_date_formats():
    """ISO/compact 混合形态同归属日 → 全部通过; 混入他日 → fail-closed。"""
    from app.services.auction_capture import _validate_tick_window

    fixture = _load_fixture()
    rows = [dict(r, trade_date="2026-08-07T00:00:00+08:00") for r in fixture["window"]]
    rows[0] = dict(rows[0], trade_date="20260807")
    check = _validate_tick_window(rows, "20260807")
    assert check["ok"] is True

    bad = list(rows)
    bad[1] = dict(bad[1], trade_date="2026-08-08T00:00:00+08:00")
    check_bad = _validate_tick_window(bad, "20260807")
    assert check_bad["ok"] is False


# ============================================================
# Task 2: 采集池解析 (白名单 ≤200 默认自选池) + 失败语义
# ============================================================


def test_resolve_pool_whitelist_wins(capture_env):
    from app.services.auction_capture import resolve_sidecar_pool

    _seed_whitelist(["600519.SH", "600000.SH"])
    pool = resolve_sidecar_pool()
    assert pool["symbols"] == ["SH600519", "SH600000"]  # suffix → prefix 归一
    assert pool["failed"] == []
    assert pool["truncated"] is False
    assert pool["pool_size"] == 2


def test_resolve_pool_default_watchlist(capture_env):
    from app.services.auction_capture import resolve_sidecar_pool

    _seed_whitelist([])
    _seed_watchlist(capture_env, ["600519.SH", "600000.SH", "000001.SZ"])
    pool = resolve_sidecar_pool()
    assert pool["symbols"] == ["SH600519", "SH600000", "SZ000001"]


def test_resolve_pool_caps_at_200(capture_env, caplog):
    from app.services.auction_capture import resolve_sidecar_pool

    _seed_whitelist([f"SH6{i:05d}" for i in range(250)])
    with caplog.at_level("WARNING", logger="app.services.auction_capture"):
        pool = resolve_sidecar_pool()
    assert len(pool["symbols"]) == 200  # pool-gated 硬 cap (5537 全量 descope, A2)
    assert pool["truncated"] is True
    assert pool["pool_size"] == 250  # 池总数含截断前
    assert "truncated" in caplog.text


def test_resolve_pool_unparsable_symbol_failed(capture_env):
    from app.services.auction_capture import resolve_sidecar_pool

    _seed_whitelist(["600519.SH", "WATCH-01"])
    pool = resolve_sidecar_pool()
    assert pool["symbols"] == ["SH600519"]
    assert {"symbol": "WATCH-01", "reason": "unparsable_symbol"} in pool["failed"]


def test_capture_partial_failure_semantics(capture_env):
    """2 symbol (一完整一短窗口) → ok=1 failed=1; 分区只含成功 symbol 行。"""
    from app.services.auction_capture import capture_auction_window

    fake = _FakeTickProvider(subsets={"SH600519": "window", "SH600000": "short_window"})
    result = capture_auction_window(fake, ["SH600519", "SH600000"], date(2026, 8, 7), capture_env)
    assert result["requested"] == 2 and result["ok"] == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["symbol"] == "SH600000"
    assert result["failed"][0]["reason"].startswith("incomplete:")

    df = pl.read_parquet(capture_env / "tick_staging" / "date=2026-08-07" / "part.parquet")
    assert set(df["symbol"].unique().to_list()) == {"SH600519"}

    manifest = _manifest(capture_env)
    assert len(manifest["symbols_failed"]) == 1
    assert manifest["symbols_failed"][0]["reason"].startswith("incomplete:")
    assert manifest["completeness"]["ok"] is False


def test_capture_all_failed_no_partition(capture_env):
    """全不完整 → 无 date= 分区目录 (fail-closed, 绝不写半成品)。"""
    from app.services.auction_capture import capture_auction_window

    fake = _FakeTickProvider(subsets={"SH600519": "short_window", "SH600000": "empty"})
    result = capture_auction_window(fake, ["SH600519", "SH600000"], date(2026, 8, 7), capture_env)
    assert result["requested"] == 2 and result["ok"] == 0 and len(result["failed"]) == 2
    assert not (capture_env / "tick_staging" / "date=2026-08-07").exists()


def test_capture_pool_resolution_merges_unparsable(capture_env):
    """symbols=None → 池解析; 归一失败合并进 failed; manifest pool_size=池总数 (含截断前)。"""
    from app.services.auction_capture import capture_auction_window

    _seed_whitelist(["600519.SH", "WATCH-01"])
    fake = _FakeTickProvider(subsets={"SH600519": "window"})
    result = capture_auction_window(fake, None, date(2026, 8, 7), capture_env)
    assert result == {
        "requested": 1, "ok": 1,
        "failed": [{"symbol": "WATCH-01", "reason": "unparsable_symbol"}],
    }
    manifest = _manifest(capture_env)
    assert manifest["pool_size"] == 2  # 池总数含归一失败
    assert manifest["symbols_failed"][0]["reason"] == "unparsable_symbol"
