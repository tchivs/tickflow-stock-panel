"""MIN-01 分钟历史回填 operator CLI (manual-only) — 直接调 backfill_minute_history, 零 API 面。

镜像 scripts/auction_backfill.py 的 CLI 惯例: argparse + DATA_DIR env 覆盖 +
终态 dict JSON 落盘 + 进度 stdout + 退出码。

- 全量宇宙: ``--all`` (kline_daily DISTINCT 运行期动态解析, 绝不硬编码)。
- 幂等续跑: 逐 symbol latest 判定, 已覆盖 → skipped (重跑 --all → 全 skipped, exit 0)。
- 增量窗口: 部分覆盖只拉 ``[latest+1day, end]`` 缺口; 空响应 → 0 行不落盘不伪 skip。
- 调度纪律: 与 EOD run_all 共享 kline_minute 写缝 (merge-upsert last-rename-wins),
  请避开 EOD 窗口运行; 服务端 120/min 硬限, rpm 缺省 120。
- 诚实覆盖声明: 实际覆盖 = 源插件深度。本环境实测源封顶 (Tushare stk_mins 1 次/小时、
  腾讯 ≈3 日深度、TDX 无 09:30) —— 端到端覆盖由 42-03 的源插件 seam + checkpoint 门
  声明, 本 CLI 绝不虚报端到端时长或覆盖 (46min 全量回填在本环境不可达)。
- 源身份 (MIN-03): ``--source-label`` (MINUTE_SOURCE_PROFILES 键之一) 透传
  backfill_minute_history → 完成日志/台账含通道身份; 缺省 None 不声明
  (湖无 provenance 列铁律, 报告 digest 诚实默认 unknown)。
- 退出码: 0 = 正常完成 (含全 skipped 的幂等续跑); 2 = fetch/运行异常
  (stderr traceback, fail-closed —— 绝不伪装「该窗口无数据」)。

用法:
    python scripts/backfill_minute_driver.py [--all|--symbols s1,s2] [--start YYYY-MM-DD]
                                             [--end YYYY-MM-DD] [--rpm N] [--batch-size N]
                                             [--limit N] [--out PATH] [--source-label KEY]
    DATA_DIR=/path/to/data python scripts/backfill_minute_driver.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))  # backend/ — app 包根

from app.services.kline_sync import (  # noqa: E402
    _resolve_minute_universe,
    backfill_minute_history,
)


def _split_csv(raw: str | None) -> list[str] | None:
    """逗号分隔参数解析: ``None`` → ``None`` (服务层缺省 = 全量 universe);
    空串 → ``[]``; 否则按逗号拆分去空白。"""
    if raw is None:
        return None
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _default_date_range(repo, data_dir: Path) -> tuple[date | None, date | None]:
    """无 --start/--end 时的缺省窗口 = kline_daily [min, max] 日期。

    首选 DuckDB 视图; 视图缺失 → kline_daily/date=* 物理分区目录兜底。
    湖空 → (None, None) fail-closed (绝不凭空造窗口)。
    """
    try:
        row = repo.execute_one("SELECT min(date), max(date) FROM kline_daily")
        if row and row[0] is not None:
            return row[0], row[1]
    except Exception:  # noqa: BLE001
        pass
    base = data_dir / "kline_daily"
    if base.is_dir():
        days = sorted(
            d.name.removeprefix("date=") for d in base.iterdir()
            if d.is_dir() and d.name.startswith("date=")
        )
        if days:
            return date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    return None, None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="backfill_minute_driver",
        description="分钟历史回填 operator CLI (MIN-01) — 直接调 backfill_minute_history, 零 API 面",
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
        default=120,
        help="每分钟请求数, >=1 (缺省 120; 对齐服务端 minute 档位)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="批大小, >=1 (缺省 200; provider 侧分块)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="调试: 只处理前 N 个 symbol (按 universe 排序)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="终态台账 JSON 路径 (缺省: 打印到 stdout)",
    )
    parser.add_argument(
        "--source-label",
        default=None,
        help="源插件 profile 键 (MINUTE_SOURCE_PROFILES: tushare-stk_mins / "
        "tencent-mkline / tdx-pytdx / canned-fixture); 透传进完成日志/台账 "
        "(覆盖 = 源插件深度, 缺省 None 不声明)",
    )
    args = parser.parse_args(argv)
    if args.rpm < 1:
        parser.error(f"--rpm 必须为 >=1 的整数, got {args.rpm}")
    if args.batch_size < 1:
        parser.error(f"--batch-size 必须为 >=1 的整数, got {args.batch_size}")
    if args.limit is not None and args.limit < 1:
        parser.error(f"--limit 必须为 >=1 的整数, got {args.limit}")
    return args


def _write_ledger(result: dict, out_path: Path | None) -> str:
    """终态台账 JSON 落盘 (tmp + rename 原子写) 或打印 stdout; 返回展示路径。"""
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if out_path is None:
        print(payload)
        return "<stdout>"
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(out_path)
    return str(out_path)


def main(argv: list[str] | None = None, _fetch=None) -> int:
    """回填驱动 CLI。``_fetch`` 为模块测试钩子 (canned 注入, 零网络); 缺省 = 真实 provider。"""
    args = _parse_args(argv)
    env_data = os.environ.get("DATA_DIR")
    data_dir = Path(env_data) if env_data else (Path(__file__).resolve().parents[2] / "data")

    try:
        from app.tickflow.repository import DataStore, KlineRepository

        store = DataStore(data_dir)
        repo = KlineRepository(store)
        try:
            if args.all or args.symbols is None:
                symbols = _resolve_minute_universe(repo)
            else:
                symbols = _split_csv(args.symbols) or []
            if args.limit is not None:
                symbols = symbols[: args.limit]
            if not symbols:
                raise ValueError("symbols 为空: universe 无 kline_daily 覆盖且未给 --symbols")

            start_date = date.fromisoformat(args.start) if args.start else None
            end_date = date.fromisoformat(args.end) if args.end else None
            if start_date is None or end_date is None:
                lo, hi = _default_date_range(repo, data_dir)
                start_date = start_date or lo
                end_date = end_date or hi
            if start_date is None or end_date is None:
                raise ValueError("kline_daily 湖空且未给 --start/--end, 无法确定回填窗口")

            started_at = datetime.now()
            t0 = time.monotonic()
            written, skipped = backfill_minute_history(
                symbols,
                start_date,
                end_date,
                repo,
                rpm=args.rpm,
                batch_size=args.batch_size,
                fetch=_fetch,
                on_symbol_done=lambda i, t: print(f"[{i}/{t}] symbols processed", flush=True),
                source_label=args.source_label,
            )
            elapsed = time.monotonic() - t0
            result = {
                "written": written,
                "skipped": len(skipped),
                "symbols_requested": len(symbols),
                "source": args.source_label,  # MIN-03: 通道身份进台账 (None → 诚实不声明)
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now().isoformat(),
            }
            ledger_path = _write_ledger(result, Path(args.out) if args.out else None)
            print("=== minute backfill summary ===")
            print(
                f"requested: {result['symbols_requested']}  written: {written}  "
                f"skipped: {result['skipped']}"
            )
            print(f"ledger: {ledger_path}  elapsed: {elapsed:.1f}s")
            return 0
        finally:
            store.db.close()
    except Exception:  # noqa: BLE001 — CLI 顶层错误 → stderr traceback + exit 2 (fail-closed)
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
