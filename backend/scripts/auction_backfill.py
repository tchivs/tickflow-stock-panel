"""FA-03 竞价历史全量回填 operator CLI (manual-only) — 直接调 run_auction_backfill, 零 API 面。

镜像 scripts/auction_backtest.py 的 CLI 惯例: argparse + DATA_DIR env 覆盖 +
终态 dict JSON 落盘 + 人类可读摘要 + exit 0/1。与 API 端点 (POST
/api/kline/auction/backfill) 完全独立: job_id=None → 不触任务注册表 (无单飞/
无超时回收/无 run 槽) —— 重启中断安全, 重跑幂等 (merge-upsert 同一写缝)。

- 全量宇宙: ``--all`` (缺省行为, kline_daily DISTINCT, 与 --symbols 互斥)。
- 断点续跑: ``--only-missing`` 覆盖预扫描, 只回填未全覆盖标的 (顶补稳定,
  连续两次 0 新增)。
- 诚实台账: 终态 dict (成功 8 键 / fail-closed +reason 9 键) 原子落盘 --out;
  BJ 号段上游恒空 → 逐 symbol ``empty_response`` 如实记录, 不预填、不假装覆盖。
- 退出码: 0 = 无 reason 键 (成功或部分成功含 BJ 失败 —— 台账诚实存在);
  1 = fail-closed (reason 键) 或未捕获异常 (stderr traceback)。
- 调度纪律: 回填与 EOD run_all 为跨进程无锁写缝 (last-rename-wins), 请避开
  EOD 窗口运行; 429 → 2s→4s 指数退避自动重试, rpm 1..60 (缺省 30)。

用法:
    python scripts/auction_backfill.py [--all|--symbols s1,s2] [--start YYYY-MM-DD]
                                       [--end YYYY-MM-DD] [--rpm N] [--only-missing]
                                       [--out PATH]
    DATA_DIR=/path/to/data python scripts/auction_backfill.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))  # backend/ — app 包根

from app.services.auction_backfill import run_auction_backfill  # noqa: E402


def _split_csv(raw: str | None) -> list[str] | None:
    """逗号分隔参数解析: ``None`` → ``None`` (服务层缺省 = 全量 universe);
    空串 → ``[]``; 否则按逗号拆分去空白。"""
    if raw is None:
        return None
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="auction_backfill",
        description="竞价历史全量回填 operator CLI (FA-03) — 直接调 run_auction_backfill, 零 API 面",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--symbols",
        default=None,
        help="逗号分隔标的 (全限定, 如 000001.SZ); 与 --all 互斥",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="全量 universe (kline_daily DISTINCT); 缺省行为 (两者都不给时)",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="起始日期 YYYY-MM-DD (可选; 缺省 = kline_daily 分区最早)",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="结束日期 YYYY-MM-DD (可选; 缺省 = kline_daily 分区最晚)",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=30,
        help="每分钟请求数, 1..60 (缺省 30; 镜像 API 校验)",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="仅回填未全覆盖标的 (覆盖预扫描, FA-02; 断点续跑/顶补)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="终态台账 JSON 路径 (缺省: CWD/auction-backfill-{YYYYMMDD-HHMMSS}.json)",
    )
    args = parser.parse_args(argv)
    if not (1 <= args.rpm <= 60):
        parser.error(f"--rpm 必须为 1~60 的整数, got {args.rpm}")
    if args.out is None:
        args.out = f"auction-backfill-{datetime.now():%Y%m%d-%H%M%S}.json"
    return args


def _print_summary(result: dict, elapsed: float, out_path: Path) -> None:
    """终态摘要 (人类可读, 诚实覆盖): requested/backfilled/rows/dates/failed/
    failed_symbols 数/rpm/台账路径/耗时; BJ ``empty_response`` 单列明示。"""
    if "reason" in result:
        print(f"backfill: fail-closed ({result['reason']}) — 0 写, 台账见 {out_path}")
        return
    print("=== auction backfill summary ===")
    print(
        f"requested: {result['requested']}  backfilled: {result['backfilled_symbols']}  "
        f"rows: {result['rows']}"
    )
    print(
        f"dates: {result['dates']}  failed: {result['failed']}  "
        f"rpm: {result['rpm']}"
    )
    failed_symbols = result["failed_symbols"]
    if failed_symbols:
        bj = sum(1 for f in failed_symbols if f.get("reason") == "empty_response")
        print(
            f"failed symbols: {len(failed_symbols)} "
            f"(empty_response/BJ 上游恒空: {bj})"
        )
    print(f"ledger: {out_path}  elapsed: {elapsed:.1f}s")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    env_data = os.environ.get("DATA_DIR")
    data_dir = Path(env_data) if env_data else (Path(__file__).resolve().parents[2] / "data")

    try:
        from app.tickflow.repository import DataStore, KlineRepository

        store = DataStore(data_dir)
        repo = KlineRepository(store)
        symbols = _split_csv(args.symbols)

        t0 = time.monotonic()
        result = run_auction_backfill(
            repo,
            symbols=symbols,
            start=args.start,
            end=args.end,
            rpm=args.rpm,
            only_missing=args.only_missing,
            on_progress=lambda stage, pct, msg, **kw: print(f"[progress] {msg}", flush=True),
            job_id=None,  # 零任务注册表: 无单飞/无超时回收/无 run 槽 (重启中断安全)
        )
        elapsed = time.monotonic() - t0
        out_path = Path(args.out)
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        _print_summary(result, elapsed, out_path)
        return 0 if "reason" not in result else 1
    except Exception:  # noqa: BLE001 — CLI 顶层错误 → stderr traceback + exit 1
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
