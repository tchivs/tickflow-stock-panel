"""竞价回测结果只读查询 (BT-09) — GET-only 读侧。

只读 ``GET /api/research/backtest`` (列运行) 与 ``GET /api/research/backtest/{run_id}``
(详情 + 谓词下推)。本模块只暴露 GET 端点: 零写面 (不落任何分区/文件)、零执行族
import、不 import 竞价同步/快照/回填/盘前快照/选股触发面模块、不引用「单 as_of
运行期缓存指针」「选股结果湖」字面量 —— 任何 mutating 路由、写路径 pattern 或禁
import 的引入都会触发 ``tests/test_research_backtest_guard.py`` 的 AST 守卫
(BT-09, 镜像 test_auction_validation.py POOL-03 六项 + E2 根隔离)。

- 湖面诚实 (与 vectorbt 平面文件共存): ``backtest_results/`` 下同时存在目录形
  research 运行 (``run_id={id}/manifest.json``) 与 vectorbt 平面文件
  (``run_id={id}.parquet``) —— 列运行端点只把含 manifest 的目录计入, 平面文件
  诚实跳过 (不报错不误读), run_id 空间天然不冲突 (sha1[:12] vs vectorbt id)。
- 空湖/坏 manifest/坏 parquet → 200 诚实空态 (runs:[] 或 stats 空), 绝不 404/500。
- run_id 严格 ``^[0-9a-f]{12}$`` 校验 → 坏格式 400, 不存在 → 404 (RESEARCH_BACKTEST)。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Request

from app.config import settings

router = APIRouter(prefix="/api/research", tags=["research"])

# run_id = sha1[:12] (16 进制小写, 34-01 确定性哈希); 路径穿越防线 (T-34-03-06)
_RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _bad_request(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "RESEARCH_BACKTEST", "message": str(error)})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "RESEARCH_BACKTEST", "message": message})


def _split_csv(raw: str | None) -> list[str] | None:
    """逗号分隔参数解析: ``None`` → ``None``; 空串 → ``[]``; 否则按逗号拆分去空白。"""
    if raw is None:
        return None
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _run_dirs() -> list[Path]:
    """backtest_results 下 ``run_id=*`` 目录 (vectorbt 平面 ``run_id={id}.parquet``
    是文件, is_dir 天然排除 —— 诚实跳过, 绝不误读)。"""
    root = settings.data_dir / "backtest_results"
    if not root.exists():
        return []
    return [p for p in root.glob("run_id=*") if p.is_dir()]


def _read_manifest(manifest_path: Path) -> dict | None:
    """严格 JSON 读 manifest; 坏 manifest → None (调用方跳过/诚实空, 绝不 500)。"""
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 只读统计 fail-open 跳过
        return None


def _manifest_strategy_ids(manifest: dict) -> set[str]:
    return {str(s.get("id", "")) for s in manifest.get("strategies", []) if isinstance(s, dict)}


def _manifest_strategy_branches(manifest: dict) -> set[str]:
    return {str(s.get("branch", "")) for s in manifest.get("strategies", []) if isinstance(s, dict)}


def _run_summary(manifest: dict) -> dict:
    """列运行条目: manifest 字段摘要 + n_hits (per_date 汇总) + coverage 透传。"""
    per_date = manifest.get("per_date", [])
    n_hits = sum(int(pd.get("n_hits", 0)) for pd in per_date if isinstance(pd, dict))
    return {
        "run_id": manifest.get("run_id"),
        "created_at": manifest.get("created_at"),
        "origin": manifest.get("origin"),
        "strategy_version": manifest.get("strategy_version"),
        "window": manifest.get("window"),
        "n_strategies": len(manifest.get("strategies", [])),
        "n_hits": n_hits,
        "coverage": manifest.get("coverage"),
    }


def _sort_key(created_at: object):
    """created_at (UTC ISO) 降序; 坏格式按 epoch 兜底 (诚实排序)。"""
    try:
        return datetime.fromisoformat(str(created_at))
    except (TypeError, ValueError):
        return datetime.min


def _scan_run_stats(
    part_path: Path,
    strategy: str | None,
    branch: str | None,
    as_of: date | None,
    symbol: str | None,
) -> tuple[dict, list[dict]]:
    """part.parquet 谓词下推 (polars scan 过滤) → 行统计 + 采样 (≤20 行)。

    - 缺列谓词 → 400 (RESEARCH_BACKTEST), 而非 500;
    - 空/坏 parquet → 诚实 200 空态 (stats 空 + sample 空), 绝不 500;
    - n_hits = 谓词后行数 (长格式行即命中行, 与 manifest per_date 汇总语义一致)。"""
    empty = {"n_rows": 0, "n_hits": 0, "per_date": [], "per_strategy": []}
    if not part_path.exists():
        return empty, []
    try:
        lf = pl.scan_parquet(part_path)
        schema = lf.collect_schema()
    except Exception:  # noqa: BLE001 — 坏 parquet 诚实空态
        return empty, []

    filters = []
    for param, column in ((strategy, "strategy"), (branch, "branch"), (as_of, "as_of"), (symbol, "symbol")):
        if param is None:
            continue
        if column not in schema:
            raise _bad_request(ValueError(f"column {column!r} not present in this run"))
        if column == "as_of":
            filters.append(pl.col(column) == param)
        else:
            filters.append(pl.col(column) == str(param))
    for f in filters:
        lf = lf.filter(f)

    try:
        df = lf.collect()
    except Exception:  # noqa: BLE001 — 读盘失败诚实空态
        return empty, []

    per_date = []
    if "as_of" in df.columns:
        grouped = df.group_by("as_of").len().sort("as_of")
        for row in grouped.iter_rows(named=True):
            d = row["as_of"]
            per_date.append({"date": d.isoformat() if hasattr(d, "isoformat") else str(d), "n_rows": int(row["len"])})
    per_strategy = []
    group_cols = [c for c in ("strategy", "branch") if c in df.columns]
    if group_cols:
        grouped = df.group_by(group_cols).len().sort(group_cols[0])
        for row in grouped.iter_rows(named=True):
            per_strategy.append(
                {c: row[c] for c in group_cols} | {"n_rows": int(row["len"])}
            )
    sample = []
    for row in df.head(20).to_dicts():
        sample.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()})
    return {"n_rows": df.height, "n_hits": df.height, "per_date": per_date, "per_strategy": per_strategy}, sample


@router.get("/backtest")
def list_backtest_runs(
    request: Request,
    strategy: str | None = Query(None, description="只留 manifest.strategies 含该策略 id 的运行"),
    branch: str | None = Query(None, description="只留 manifest.strategies 含该 branch 策略的运行 (real|derived|eod)"),
) -> dict:
    """列竞价回测运行 (BT-09): 扫 ``backtest_results/run_id=*`` 目录读 manifest。

    - 仅含 manifest.json 的目录计入 research 运行 (vectorbt 平面文件诚实跳过);
    - ``?strategy=`` / ``?branch=`` 按 manifest.strategies 过滤;
    - 按 created_at 降序; 空湖 → ``{runs: [], count: 0}`` (200 诚实空)。"""
    runs = []
    for run_dir in _run_dirs():
        manifest = _read_manifest(run_dir / "manifest.json")
        if manifest is None:
            continue
        if strategy is not None and strategy not in _manifest_strategy_ids(manifest):
            continue
        if branch is not None and branch not in _manifest_strategy_branches(manifest):
            continue
        runs.append(_run_summary(manifest))
    runs.sort(key=lambda r: _sort_key(r.get("created_at")), reverse=True)
    return {"runs": runs, "count": len(runs)}


@router.get("/backtest/{run_id}")
def get_backtest_run(
    run_id: str,
    request: Request,
    strategy: str | None = Query(None, description="谓词下推: 只留该策略 id 的命中行"),
    branch: str | None = Query(None, description="谓词下推: 只留该 branch 的命中行 (real|derived|eod)"),
    as_of: date | None = Query(None, description="谓词下推: 信号日 T (YYYY-MM-DD)"),
    symbol: str | None = Query(None, description="谓词下推: 标的 (全限定, 如 000001.SZ)"),
) -> dict:
    """竞价回测运行详情 (BT-09): manifest 全文 + part.parquet 行统计 + 采样。

    - run_id 非 ``^[0-9a-f]{12}$`` → 400 RESEARCH_BACKTEST (T-34-03-06);
    - 目录/manifest 不存在 → 404 ``{"code":"RESEARCH_BACKTEST","message":"run not found"}``;
    - ``?strategy=&branch=&as_of=&symbol=`` 谓词下推 (polars scan 过滤, 缺列 → 400);
    - 空/坏 parquet → 200 诚实空 stats (绝不 500)。"""
    if not _RUN_ID_RE.fullmatch(run_id):
        raise _bad_request(ValueError(f"invalid run_id: {run_id!r}"))
    run_dir = settings.data_dir / "backtest_results" / f"run_id={run_id}"
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise _not_found("run not found")
    manifest = _read_manifest(manifest_path)
    if manifest is None:
        raise _not_found("run manifest unreadable")

    stats, sample = _scan_run_stats(run_dir / "part.parquet", strategy, branch, as_of, symbol)
    return {"manifest": manifest, "stats": stats, "sample": sample}
