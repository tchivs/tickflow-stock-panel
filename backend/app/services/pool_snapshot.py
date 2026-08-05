"""冻结式点快照服务 — POOL-04/05。

点快照 = 当次 ``run_all`` 的 ``results`` 行集 (``{sid: {total, as_of, rows}}``) 的
冻结持久化, 原子写 ``screener_results/date={as_of}/part.json`` (temp + os.replace)。

铁律 (POOL-04):
- 快照只落当次 ``results``, **绝不落** ``today_ever_rows`` / ``today_ever_matched``
  union 键 (运行时缓存 strategy_cache 的并集语义与点快照严格分离)。
- 携带 ``as_of`` / ``computed_at`` / ``strategy_version`` / ``snapshot_type:"point"`` /
  ``schema_version:1``。
- total=0 空策略保留 (无行 → 卡片不消失)。
- 同 as_of 幂等重写, 无 .tmp 残留。

本模块不 import 运行时缓存 (strategy_cache) — 缓存隔离由 tests/test_pool_hub.py
AST 守卫 E3 锁定。零新增运行时依赖 (stdlib json/os/hashlib/re/pathlib)。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 快照湖根目录 (相对 data_dir) — 与 repository.py 建目录占位的 hive 分区布局一致
_SNAPSHOT_ROOT = "screener_results"
# as_of 严格校验: ^\d{4}-\d{2}-\d{2}$ (防路径穿越; 拼路径前必须 fullmatch)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SCHEMA_VERSION = 1


def _json_default(obj: Any) -> Any:
    """处理 date/datetime 等 JSON 不认识的类型 (镜像 strategy_cache._json_default)。"""
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _snapshot_path(data_dir: Path, as_of: str) -> Path:
    return data_dir / _SNAPSHOT_ROOT / f"date={as_of}" / "part.json"


def persist_point_snapshot(
    data_dir: Path,
    as_of: str,
    results: dict,
    strategy_version: str,
    computed_at: str,
) -> Path:
    """原子写冻结式点快照到 ``screener_results/date={as_of}/part.json``。

    - 非法 as_of (不匹配 ``^\\d{4}-\\d{2}-\\d{2}$``) → 抛 ValueError (防路径穿越)。
    - payload 只含当次 ``results`` 与元数据, 结构上无 union 键 (T-22-02)。
    - temp + ``os.replace`` 原子替换; 异常吞掉记 warning (非致命语义, 不阻塞请求)。

    Args:
        data_dir: 数据根目录。
        as_of: 交易日 (``YYYY-MM-DD``, 分区键)。
        results: 当次 run_all 行集 ``{sid: {total, as_of, rows}}``。
        strategy_version: 策略集指纹 (strategy_fingerprint 输出)。
        computed_at: 计算完成时刻 (ISO8601 字符串)。

    Returns:
        写入的 part.json 路径。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        raise ValueError(f"invalid as_of: {as_of!r}")

    part_dir = data_dir / _SNAPSHOT_ROOT / f"date={as_of}"
    part_dir.mkdir(parents=True, exist_ok=True)
    path = part_dir / "part.json"

    payload = {
        "as_of": as_of,
        "computed_at": computed_at,
        "strategy_version": strategy_version,
        "snapshot_type": "point",
        "schema_version": _SCHEMA_VERSION,
        "results": results,
    }
    try:
        # 原子写: 先写临时文件再 os.replace, 避免读侧读到半写的 JSON
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        logger.info("点快照已写入: %s (%d 策略)", as_of, len(results))
    except Exception as e:  # noqa: BLE001
        logger.warning("写入点快照失败: %s", e)
    return path


def load_point_snapshot(data_dir: Path, as_of: str) -> dict | None:
    """读取点快照 (全量 payload dict, 含 ``results``)。

    非法 as_of (非 str / 不匹配日期格式) → 防御性返回 None (不抛 TypeError);
    文件不存在 / 解析失败 → None。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        return None
    path = _snapshot_path(data_dir, as_of)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("读取点快照失败: %s", e)
        return None


def list_snapshot_dates(data_dir: Path) -> list[str]:
    """列出含 ``part.json`` 的快照日期, ISO desc (新日期在前)。

    source of truth = ``screener_results/date=*`` 分区 glob (daily_pipeline 既有模式);
    无 ``part.json`` 的 date=* 目录被排除; root 不存在返回 ``[]``。
    """
    root = data_dir / _SNAPSHOT_ROOT
    if not root.exists():
        return []
    return sorted(
        (d.name[5:] for d in root.glob("date=*") if (d / "part.json").exists()),
        reverse=True,
    )


def strategy_fingerprint(engine) -> str:
    """策略集指纹: 排序后的策略声明 meta + 各策略源文件内容的 sha256[:16]。

    同一策略集 + 同一代码 → 同指纹; meta 声明或源码任何变化 → 新指纹, 历史快照
    不被静默重解释 (22-RESEARCH RQ1 骨架)。
    """
    meta_blob = json.dumps(
        sorted(engine.list_strategies(), key=lambda m: m["id"]),
        sort_keys=True,
        default=str,
    )
    file_blob = b""
    for s in engine._strategies.values():
        fp = getattr(s, "file_path", None)
        if not fp:
            continue
        p = Path(fp)
        if p.exists():
            file_blob += hashlib.sha256(p.read_bytes()).digest()
    return hashlib.sha256(meta_blob.encode() + file_blob).hexdigest()[:16]
