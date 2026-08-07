"""BT-07 竞价回测 operator CLI (manual-only) — 竞价族策略全量回测触发面 (O1)。

直接调 ``app.services.auction_backtest.run_full_backtest``, 零 API 面 —— 研究查询
端点 (GET /api/research/backtest) 保持 GET-only, 写触发独立于本脚本, 守卫面不破。

- 参数恒 META 默认 (O2): 本 CLI 不接受策略参数覆盖 (无 user overrides, 无运行时
  缓存读取); 策略定义变化由 strategy_version 指纹记入 manifest, 跨日可比性由
  META 默认保证。
- 只写 ``backtest_results/`` (E2 根隔离): 所有落盘由 run_full_backtest 原子持久化
  到 ``data/backtest_results/run_id={确定性哈希}/`` (part.parquet + manifest.json);
  同参数重跑幂等 (fingerprint 相同 → reused, 不重写)。
- 全量窗口装载: 启动先装载 kline_daily_enriched 全分区历史 (含指标) 到 repo 缓存
  (仓库默认只缓存最近 300 自然日, 覆盖不了 ``--range 248``) —— 回测覆盖边界 =
  全量 enriched 交易日。
- 186 天 guard 不适用 (D-06): 本回测是单面板向量化扫描, 覆盖由 enriched 缓存
  边界决定, 窗口回夹 + requested/effective 双字段回显。
- 分钟限制注解 (BT-10): kline_minute 历史 CLOSED, 逐行 minute_confirm="not_applied",
  auction_intraday_confirm minute 确认恒空 (其日线初筛仅消费 open_gap, 不消费竞价列) ——
  确认维度诚实受限, 本 CLI 不假装生效。
- ``--rpm`` 为保留参数 (当前无操作): 本地向量化单面板回测无需限速 (与竞价回填
  CLI 对称, 诚实不假装生效)。

用法:
    python scripts/auction_backtest.py [--strategies id1,id2] [--range 248|START,END]
                                       [--symbols s1,s2] [--rpm N]
    DATA_DIR=/path/to/data python scripts/auction_backtest.py
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import date
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))  # backend/ — app 包根

from app.services.auction_backtest import run_full_backtest  # noqa: E402


def _split_csv(raw: str | None) -> list[str] | None:
    """逗号分隔参数解析: ``None`` → ``None`` (服务层缺省 = 9 竞价族/全市场);
    空串 → ``[]``; 否则按逗号拆分去空白。"""
    if raw is None:
        return None
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _enriched_dates(data_dir: Path) -> list[date]:
    """enriched 交易日列表 (扫 kline_daily_enriched/date=* 目录, 解析失败跳过)。

    语义镜像 run_full_backtest 的 _enriched_coverage 回退路径 —— 供 --range N 形
    把「最近 N 个 enriched 交易日」解析为显式窗口; 服务层随后回夹兜底。"""
    base = data_dir / "kline_daily_enriched"
    dates: list[date] = []
    if base.exists():
        for part in base.glob("date=*"):
            name = part.name
            if not name.startswith("date="):
                continue
            try:
                dates.append(date.fromisoformat(name[len("date="):]))
            except ValueError:
                continue
    return sorted(dates)


def _parse_range(raw: str, cache_dates: list[date]) -> tuple[date | None, date | None]:
    """--range 解析 (两种形):

    - ``N`` (缺省 248): 最近 N 个 enriched 交易日 → start = 倒数第 N 日, end = 最新;
    - ``START,END``: 显式 ISO 日期对。

    解析失败抛 ValueError (CLI 捕获 → exit 1); 服务层回夹兜底。"""
    if "," in raw:
        start_s, end_s = (part.strip() for part in raw.split(",", 1))
        return date.fromisoformat(start_s), date.fromisoformat(end_s)
    n = int(raw)
    if n <= 0:
        raise ValueError(f"invalid --range N: {raw!r} (must be >= 1)")
    if not cache_dates:
        return None, None
    start = cache_dates[-n] if n <= len(cache_dates) else cache_dates[0]
    return start, cache_dates[-1]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="auction_backtest",
        description="竞价族策略全量回测 operator CLI (BT-07) — 直接调 run_full_backtest, 零 API 面",
    )
    parser.add_argument(
        "--strategies",
        default=None,
        help="逗号分隔策略 id; 缺省 = 9 个竞价族全部 (服务层 None 语义)",
    )
    parser.add_argument(
        "--range",
        default="248",
        help="N (最近 N 个 enriched 交易日, 缺省 248) 或 START,END (ISO 日期对)",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="逗号分隔标的 (全限定, 如 000001.SZ); 缺省 = 全市场",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=None,
        help="保留参数 (无操作): 本地向量化单面板回测无需限速 — 接受但当前不生效 (诚实注)",
    )
    return parser.parse_args(argv)


def _preload_full_enriched(repo) -> None:
    """装载全量 enriched 历史到 repo 内存缓存 (kline_daily_enriched 全分区, 含指标)。

    run_full_backtest 的覆盖边界 = repo 内存缓存 (34-01 契约: 窗口回夹到缓存覆盖);
    仓库默认 ``_refresh_enriched`` 只读最近 300 自然日 (~205 交易日), 覆盖不了
    ``--range 248`` 全量窗口。本 CLI 镜像 repository._refresh_enriched 的装配形
    (scan_enriched_parquet → compute_indicators → compute_signals →
    compute_limit_signals), 窗口 = 全分区 → 回测窗口可解析到全量 enriched 交易日。
    """
    from app.indicators.pipeline import compute_indicators, compute_limit_signals, compute_signals
    from app.parquet import scan_enriched_parquet

    lf = scan_enriched_parquet(repo._enriched_glob).sort(["symbol", "date"])
    read_cols = [c for c in ["symbol", "date", "open", "high", "low", "close",
                             "volume", "amount", "raw_close", "raw_high", "raw_low"]
                 if c in lf.collect_schema().names()]
    df_hist = lf.select(read_cols).collect()
    if df_hist.is_empty():
        return
    df_full = compute_indicators(df_hist)
    df_full = compute_signals(df_full)
    instruments = repo.get_instruments_asset("stock")
    if instruments is not None and not instruments.is_empty():
        df_full = compute_limit_signals(df_full, instruments)
    repo._enriched_history_cache = df_full
    repo._enriched_history_start = df_full["date"].min()


def _print_summary(result: dict, elapsed: float) -> None:
    """终态摘要 (人类可读, 诚实覆盖): run_id/wrote|reused/窗口/每策略行/
    coverage.symbols/落盘路径/耗时/BT-10 注。"""
    status = result.get("status")
    if status in ("no_enriched", "no_dates_in_window"):
        print(f"backtest: {status} ({result.get('empty_reason')}) — 无产物, 诚实空态")
        return
    print("=== auction backtest summary ===")
    print(
        f"run_id: {result['run_id']}  status: {status}  "
        f"wrote: {result['wrote']}  reused: {result['reused']}"
    )
    print(f"strategy_version: {result['strategy_version']}  origin: {result['origin']}")
    window = result["window"]
    print(
        f"window: requested {window['requested_start']}..{window['requested_end']} | "
        f"effective {window['effective_start']}..{window['effective_end']}"
    )
    for s in result["strategies"]:
        print(
            f"  {s['id']} branch={s['branch']} dates={s['n_dates']} hits={s['n_hits']} "
            f"sym_covered={s['n_symbols_covered']} sym_hit={s['n_symbols_hit']} "
            f"missing={s['n_missing_outcomes']}"
        )
    if result.get("skipped_ids"):
        print(f"  skipped_ids: {result['skipped_ids']}")
    syms = result["coverage"]["symbols"]
    print(
        f"coverage: auction_symbols={syms['auction_symbol_count']} "
        f"enriched_symbols={syms['enriched_symbol_count']} "
        f"ratio={syms['symbol_coverage_ratio']:.2%} "
        f"rows_present={syms['auction_rows_present']}/{syms['auction_rows_expected']}"
    )
    if any(s["id"] == "auction_intraday_confirm" for s in result["strategies"]):
        print(
            "note: auction_intraday_confirm branch=real 但日线初筛仅消费 open_gap "
            "(enriched 派生列) — hits 不随湖覆盖增长 (52,591 恒定), BT-10 注"
        )
    print(f"path: {result['path']}  rows: {result['rows'].height}")
    print("BT-10: minute_confirm=not_applied — kline_minute 历史 CLOSED (确认维度诚实受限)")
    print(f"elapsed: {elapsed:.1f}s")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    env_data = os.environ.get("DATA_DIR")
    data_dir = Path(env_data) if env_data else (Path(__file__).resolve().parents[2] / "data")

    try:
        from app.services.screener import ScreenerService
        from app.strategy.engine import StrategyEngine
        from app.tickflow.repository import DataStore, KlineRepository

        store = DataStore(data_dir)
        repo = KlineRepository(store)
        # 引擎构造镜像 main.py:551-565 (enriched 快路径 loader, 不传 minute_loader —
        # BT-10: 分钟确认维度不接线)
        _screener_svc = ScreenerService(repo)
        engine = StrategyEngine(
            enriched_loader=_screener_svc._load_enriched_for_date,
            enriched_history_loader=_screener_svc._load_enriched_history,
            strategy_dirs=[
                _SCRIPT_DIR.parent / "app" / "strategy" / "builtin",
                data_dir / "strategies" / "custom",
                data_dir / "strategies" / "ai",
            ],
        )

        # 全量 enriched 缓存装载 (248 交易日, 含指标) — run_full_backtest 覆盖边界
        print("[progress] preload: full enriched history", flush=True)
        _preload_full_enriched(repo)

        start, end = _parse_range(args.range, _enriched_dates(data_dir))
        strategy_ids = _split_csv(args.strategies)
        symbols = _split_csv(args.symbols)

        t0 = time.monotonic()
        result = run_full_backtest(
            repo,
            engine,
            start=start,
            end=end,
            strategy_ids=strategy_ids,
            symbols=symbols,
            on_progress=lambda m: print(f"[progress] {m}"),
        )
        elapsed = time.monotonic() - t0
        _print_summary(result, elapsed)
        return 0 if result.get("status") in ("ok", "reused") else 1
    except Exception:  # noqa: BLE001 — CLI 顶层错误 → stderr traceback + exit 1
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
