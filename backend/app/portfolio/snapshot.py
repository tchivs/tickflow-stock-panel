"""Phase 11 复合快照绑定 — catalog.get_composite_model → checksum 验证 artifact → as_of 横截面.

职责: 把 Phase 10 的复合模型按快照消费 (FACT-03 契约, 11-RESEARCH.md
`## Input Snapshot Binding`): (1) catalog.get_composite_model 解析模型记录;
(2) 读取 data_dir/artifact_relative_path 的 artifact 字节并校验
sha256 == output_sha256 (frozen_panel fail-closed 模式); (3) 解析
[symbol, date, composite] 行, 按 as_of 取当日横截面作为期望收益向量 mu;
(4) 可选 PIT 过滤 (universe_resolver.resolve_universe_daily 成员关系 inner
join)。任何失败路径 —— 模型缺失、无快照、artifact 缺失/篡改/校验和不匹配、
as_of 早于 artifact 数据覆盖 (lookahead) —— 都以 SnapshotBindingError 抛出,
由 run_optimization 编排器记录为 failed run (PFOL-04), 绝不静默中断。

不知道: 求解逻辑 (optimizer.py)、风险模型 (risk.py)、工件存储 (artifacts.py)、
build_composite 的调用路径 (本模块绝不调用 build_composite —— pitfall 5, 无
live module hand-off)。
"""
from __future__ import annotations

import json
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

class SnapshotBindingError(RuntimeError):
    """复合快照绑定失败 (fail-closed): 由 run_optimization 记录为 failed run。"""


def _as_date_string(value: Any) -> str:
    """把 artifact 行 / 成员关系帧里的 date 归一化为 ISO 字符串。"""
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def load_composite_snapshot(
    catalog: Any,
    *,
    model_id: str,
    as_of: date,
    data_dir: Path,
    universe_resolver: object | None = None,
    universe: str = "cn-a-share",
) -> dict[str, Any]:
    """Load the checksum-verified composite snapshot as the ``as_of`` cross-section.

    返回 dict:
        {
            "model_id": str,
            "composite_snapshot_id": str,       # factor_model_composites.id (审计根)
            "input_snapshot_sha256": str,        # == composite 行的 input_snapshot_sha256
            "as_of": str,                        # ISO 日期
            "symbols": list[str],                # 当日横截面的标的 (PIT 过滤后)
            "mu": list[float],                   # 与 symbols 对齐的 composite z-score
        }

    失败路径全部抛 SnapshotBindingError:
        - catalog.get_composite_model 返回 None      -> "model not found"
        - latest_composite is None                   -> "no composite snapshot recorded"
        - artifact 缺失 / 篡改 / 校验和不匹配          -> "composite artifact checksum mismatch"
        - as_of 早于 artifact 数据覆盖 (lookahead)     -> "as_of precedes composite snapshot coverage"
        - as_of 当日无横截面                           -> "no composite cross-section at as_of"

    Args:
        catalog: ExperimentCatalog (或等价 get_composite_model 接口)。
        model_id: 复合模型 id。
        as_of: 组合构建日期 (横截面取这一天的 composite 值)。
        data_dir: 应用数据根目录 (artifact_relative_path 是相对它的路径)。
        universe_resolver: 可选 PIT 解析器 (resolve_universe_daily); None 时不
            做成员过滤 (测试 fixture 路径)。
        universe: PIT 过滤使用的 universe 名。

    Returns:
        上面描述的快照 dict。
    """
    record = catalog.get_composite_model(model_id)
    if record is None:
        raise SnapshotBindingError("model not found")
    latest = record.latest_composite
    if latest is None:
        raise SnapshotBindingError("no composite snapshot recorded")

    artifact_relative_path = str(latest["artifact_relative_path"])
    artifact_path = Path(data_dir) / artifact_relative_path
    try:
        content = artifact_path.read_bytes()
    except OSError as error:
        raise SnapshotBindingError("composite artifact checksum mismatch") from error
    if sha256(content).hexdigest() != str(latest["output_sha256"]):
        raise SnapshotBindingError("composite artifact checksum mismatch")

    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotBindingError("composite artifact checksum mismatch") from error
    if not isinstance(payload, list):
        raise SnapshotBindingError("composite artifact checksum mismatch")

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        row_date = item.get("date")
        composite_value = item.get("composite")
        if symbol is None or row_date is None or composite_value is None:
            continue
        rows.append(
            {
                "symbol": str(symbol),
                "date": _as_date_string(row_date),
                "composite": float(composite_value),
            }
        )
    if not rows:
        raise SnapshotBindingError("composite artifact is empty")

    # Lookahead 守卫: as_of 不能早于 artifact 的数据覆盖 (面板窗口起点)。
    # 按数据覆盖而非 created_at 判定 —— 回测复合的 created_at 晚于数据日期
    # (RESEARCH.md "as_of precedes ... or the panel window" 的后者是生效条款)。
    earliest_date = min(row["date"] for row in rows)
    if as_of.isoformat() < earliest_date:
        raise SnapshotBindingError("as_of precedes composite snapshot coverage")

    # PIT 过滤: 成员关系帧 inner join (post-seam, signal_chain 同款)。
    if universe_resolver is not None:
        resolve = getattr(universe_resolver, "resolve_universe_daily", None)
        if resolve is not None:
            membership = resolve(
                universe_name=universe, start=as_of, end=as_of, asset_type="stock"
            )
            member_dates = {
                (str(symbol), _as_date_string(value))
                for symbol, value in zip(
                    membership["symbol"].to_list(), membership["date"].to_list(), strict=True
                )
            }
            rows = [
                row for row in rows if (row["symbol"], row["date"]) in member_dates
            ]

    cross_section = [row for row in rows if row["date"] == as_of.isoformat()]
    cross_section.sort(key=lambda row: row["symbol"])
    if not cross_section:
        raise SnapshotBindingError("no composite cross-section at as_of")

    return {
        "model_id": model_id,
        "composite_snapshot_id": str(latest["id"]),
        "input_snapshot_sha256": str(latest["input_snapshot_sha256"]),
        "as_of": as_of.isoformat(),
        "symbols": [row["symbol"] for row in cross_section],
        "mu": [row["composite"] for row in cross_section],
    }
