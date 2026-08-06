"""盘前预览独立存储 — PM-01 (D3)。

盘前 09:26 预览 job 生成的股池写入独立 ``premarket_results/date={as_of}/part.json``
(与 EOD ``screener_results/date=*`` 物理分离, 绝不写 ``strategy_cache`` single-as_of
指针 / 绝不写 ``screener_results`` EOD 语义)。

铁律 (PM-01):
- 原子写: temp + ``os.replace`` (镜像 pool_snapshot.persist_point_snapshot)。
- ``_DATE_RE`` fullmatch 后才拼路径 (防路径穿越, T-27-01-02)。
- payload 由调用方构造 (含 window/provisional/degraded/probe), 本模块不重包。
- 同 as_of 幂等重写, 无 .tmp 残留。

本模块不 import 运行时缓存 (strategy_cache) 与执行族模块 — 缓存隔离由
tests/test_pool_hub.py AST 守卫 E3 形锁定。零新增运行时依赖 (stdlib json/os/re/pathlib)。
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 盘前预览湖根目录 (相对 data_dir) — 与 EOD _SNAPSHOT_ROOT="screener_results" 物理分离 (D3)
_PREMARKET_ROOT = "premarket_results"
# as_of 严格校验: ^\d{4}-\d{2}-\d{2}$ (防路径穿越; 拼路径前必须 fullmatch)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SCHEMA_VERSION = 1


def _json_default(obj: Any) -> Any:
    """处理 date/datetime 等 JSON 不认识的类型 (镜像 pool_snapshot._json_default)。"""
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _premarket_path(data_dir: Path, as_of: str) -> Path:
    return data_dir / _PREMARKET_ROOT / f"date={as_of}" / "part.json"


def persist_premarket_snapshot(data_dir: Path, as_of: str, payload: dict) -> Path:
    """原子写盘前预览到 ``premarket_results/date={as_of}/part.json``。

    - 非法 as_of (不匹配 ``^\\d{4}-\\d{2}-\\d{2}$``) → 抛 ValueError (防路径穿越, T-27-01-02)。
    - payload 由调用方构造 (含 window/provisional/degraded/probe), 不在此处重包。
    - temp + ``os.replace`` 原子替换; 异常吞掉记 warning (非致命语义)。

    Args:
        data_dir: 数据根目录。
        as_of: 交易日 (``YYYY-MM-DD``, 分区键)。
        payload: 盘前预览 payload dict (含 results/window/provisional/degraded/probe)。

    Returns:
        写入的 part.json 路径。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        raise ValueError(f"invalid as_of: {as_of!r}")

    part_dir = data_dir / _PREMARKET_ROOT / f"date={as_of}"
    part_dir.mkdir(parents=True, exist_ok=True)
    path = part_dir / "part.json"
    try:
        # 原子写: 先写临时文件再 os.replace, 避免读侧读到半写的 JSON
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        logger.info("盘前预览已写入: %s", as_of)
    except Exception as e:  # noqa: BLE001
        logger.warning("写入盘前预览失败: %s", e)
    return path


def load_premarket_snapshot(data_dir: Path, as_of: str) -> dict | None:
    """读取盘前预览 (全量 payload dict, 含 ``results``)。

    非法 as_of (非 str / 不匹配日期格式) → 防御性返回 None (不抛 TypeError);
    文件不存在 / 解析失败 → None。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        return None
    path = _premarket_path(data_dir, as_of)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("读取盘前预览失败: %s", e)
        return None


def list_premarket_dates(data_dir: Path) -> list[str]:
    """列出含 ``part.json`` 的盘前预览日期, ISO desc (新日期在前)。

    镜像 pool_snapshot.list_snapshot_dates (:129-142); root 不存在返回 ``[]``。
    纯读 helper — 不枚举进 ``/api/pool/dates`` (DateNavigator 保持 EOD-only, PM-04)。
    """
    root = data_dir / _PREMARKET_ROOT
    if not root.exists():
        return []
    return sorted(
        (d.name[5:] for d in root.glob("date=*") if (d / "part.json").exists()),
        reverse=True,
    )
