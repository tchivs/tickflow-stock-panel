"""概念 PIT 历史归档 — CONCEPT-01..07。

写 data/ext_history/{gn_ths|hy_ths}/date={as_of}/part.parquet + manifest.json
(平台自有根, 与 EOD screener_results / premarket_results 物理分离)。

铁律:
- 原子写: temp + os.replace (镜像 pool_snapshot.persist_point_snapshot)。
- _DATE_RE fullmatch + date.fromisoformat 双重校验后才拼路径 (防路径穿越)。
- 同 as_of 幂等重写, 无 .tmp 残留。
- 本模块不 import 运行时缓存与执行族模块 — 写权限/缓存隔离由
  tests/test_concept_history.py AST 守卫 (E1/E3 形) 锁定。
- 零新增外部运行时依赖 (stdlib + polars)。
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

import polars as pl

from app.services.ext_data import ExtConfigStore, cast_df_to_schema
from app.services.market_overview_builder import _dimension_field

logger = logging.getLogger(__name__)

# 历史归档湖根目录 (相对 data_dir) — 平台自有根, 绝不进 ext_data (CONCEPT-05)
_HISTORY_ROOT = "ext_history"
# 归档表: 概念 + 行业同建 (orchestrator 决策 c)
_KINDS = ("gn_ths", "hy_ths")
# 归档表 → 当前 ext 配置 id
_KIND_CONFIG = {"gn_ths": "ext_gn_ths", "hy_ths": "ext_hy_ths"}
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


def _partition_dir(data_dir: Path, kind: str, as_of: str) -> Path:
    """返回分区目录 ``data_dir/ext_history/{kind}/date={as_of}`` (拼路径前必须校验)。"""
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        raise ValueError(f"invalid as_of: {as_of!r}")
    date.fromisoformat(as_of)  # 双重校验 (镜像 api/pool.py)
    return data_dir / _HISTORY_ROOT / kind / f"date={as_of}"


def _partition_path(data_dir: Path, kind: str, as_of: str) -> Path:
    return _partition_dir(data_dir, kind, as_of) / "part.parquet"


def _manifest_path(data_dir: Path, kind: str, as_of: str) -> Path:
    return _partition_dir(data_dir, kind, as_of) / "manifest.json"


def _sha256_file(path: Path) -> str | None:
    """文件内容 sha256; 读取失败 → None (探针/幂等判定共用)。"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception as e:  # noqa: BLE001
        logger.warning("计算分区哈希失败: %s", e)
        return None


def _current_rows(data_dir: Path, config) -> list[dict]:
    """读当前 ext 快照全行 (data/ext_data/{id}/part.parquet); 缺失/解析失败 → []。"""
    path = data_dir / "ext_data" / config.id / "part.parquet"
    if not path.exists():
        return []
    try:
        return pl.read_parquet(str(path)).to_dicts()
    except Exception as e:  # noqa: BLE001
        logger.warning("读取 ext 快照失败 (%s): %s", config.id, e)
        return []


def _resolve_fetched_at(data_dir: Path, config) -> str:
    """当前快照数据实际产生时刻 (CONCEPT-07): config.pull.last_run → part mtime → ''。"""
    if config.pull is not None and config.pull.last_run:
        return config.pull.last_run
    try:
        p = data_dir / "ext_data" / config.id / "part.parquet"
        if p.exists():
            return datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _write_partition(
    data_dir: Path,
    kind: str,
    as_of: str,
    rows: list[dict],
    *,
    source_url: str,
    fetched_at: str,
    captured_at: str,
    dimension_field: str,
) -> Path | None:
    """原子写单个 hive 分区 + manifest (temp + os.replace)。

    - 非法 as_of → ValueError (防路径穿越, T-28-01-01)。
    - 同 as_of 幂等重写; 无 .tmp 残留。
    - 写失败 → logger.warning 非致命, 返回 None (由调用方诚实 skip)。
    - 写路径只经 ``_HISTORY_ROOT == "ext_history"`` 派生 (CONCEPT-05 E2 形)。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        raise ValueError(f"invalid as_of: {as_of!r}")
    date.fromisoformat(as_of)  # 双重校验 (镜像 api/pool.py)

    part_dir = data_dir / _HISTORY_ROOT / kind / f"date={as_of}"
    part_path = part_dir / "part.parquet"
    manifest_path = part_dir / "manifest.json"
    tmp: Path | None = None
    tmp_manifest: Path | None = None
    try:
        part_dir.mkdir(parents=True, exist_ok=True)
        df = pl.DataFrame(rows)
        config = ExtConfigStore(data_dir).get(_KIND_CONFIG[kind])
        if config is not None:
            field_names = [f.name for f in config.fields]
            if dimension_field in field_names:
                df = cast_df_to_schema(df, config.fields)  # 列序稳定 (对齐 ext schema)
        tmp = part_path.with_name(part_path.name + ".tmp")
        df.write_parquet(tmp)
        os.replace(tmp, part_path)

        manifest = {
            "as_of": as_of,
            "kind": kind,
            "dimension_field": dimension_field,
            "source_url": source_url,
            "fetched_at": fetched_at,
            "captured_at": captured_at,
            "rows": len(rows),
            "schema_version": _SCHEMA_VERSION,
            "sha256": _sha256_file(part_path),
        }
        tmp_manifest = manifest_path.with_name(manifest_path.name + ".tmp")
        tmp_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        os.replace(tmp_manifest, manifest_path)
        logger.info("概念分区已写入: %s/%s (%d 行)", kind, as_of, len(rows))
        return part_path
    except Exception as e:  # noqa: BLE001
        logger.warning("写入概念分区失败: %s", e)
        for leftover in (tmp, tmp_manifest):
            if leftover is not None and leftover.exists():
                try:
                    leftover.unlink()
                except Exception:  # noqa: BLE001
                    pass
        return None


def capture(data_dir: Path, as_of: str) -> dict:
    """主路径 (离线, 零网络): 读当前 ext_gn_ths / ext_hy_ths 快照 → 前向归档分区。

    - 非法 as_of → ValueError (防路径穿越)。
    - 快照缺失/0 行/写失败 → 该 kind 诚实 skip (不写任何文件)。
    - 返回 ``{"as_of", "gn_ths": {written, rows}, "hy_ths": {written, rows}}``。
    - 写失败仅记 warning, 绝不阻断调用方 (EOD 钩子 try/except 兜底)。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        raise ValueError(f"invalid as_of: {as_of!r}")
    date.fromisoformat(as_of)

    out: dict[str, Any] = {"as_of": as_of}
    store = ExtConfigStore(data_dir)
    for kind in _KINDS:
        config = store.get(_KIND_CONFIG[kind])
        if config is None:
            out[kind] = {"written": False, "rows": 0, "reason": "no config"}
            continue
        rows = _current_rows(data_dir, config)
        if not rows:
            out[kind] = {"written": False, "rows": 0, "reason": "empty snapshot"}
            continue
        dimension_field = _dimension_field(config, "concept" if kind == "gn_ths" else "industry")
        if not dimension_field:
            dimension_field = config.fields[0].name  # 兜底 (自描述字段缺失)
        captured_at = datetime.now().astimezone().isoformat()
        fetched_at = _resolve_fetched_at(data_dir, config) or captured_at
        source_url = config.pull.url if config.pull is not None and config.pull.url else ""
        part_path = _write_partition(
            data_dir,
            kind,
            as_of,
            rows,
            source_url=source_url,
            fetched_at=fetched_at,
            captured_at=captured_at,
            dimension_field=dimension_field,
        )
        if part_path is not None:
            out[kind] = {"written": True, "rows": len(rows)}
        else:
            out[kind] = {"written": False, "rows": 0, "reason": "write failed"}
    return out


def capture_from_upstream(data_dir: Path, as_of: str) -> dict:
    """OQ-3 探针专用: 独立测量上游 (同步 httpx.Client, 与 capture 只差抓取源)。

    - 抓取失败/0 行 → logger.warning + skip, 不抛。
    - 非法 as_of → ValueError (防路径穿越)。
    - 与 ``capture`` 共用 ``_write_partition`` 写路径 (切换成本 = 一个调用点)。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        raise ValueError(f"invalid as_of: {as_of!r}")
    date.fromisoformat(as_of)

    import httpx
    from app.services.ext_presets import _flatten_concept_rows, _flatten_industry_rows

    out: dict[str, Any] = {"as_of": as_of}
    store = ExtConfigStore(data_dir)
    for kind in _KINDS:
        config = store.get(_KIND_CONFIG[kind])
        if config is None or config.pull is None or not config.pull.url:
            out[kind] = {"written": False, "rows": 0, "reason": "no config"}
            continue
        flatten = _flatten_concept_rows if kind == "gn_ths" else _flatten_industry_rows
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(config.pull.url)
                resp.raise_for_status()
                raw = resp.json()
            if not isinstance(raw, list):
                raise ValueError(f"接口返回不是数组: {type(raw)}")
            rows = flatten(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("上游抓取失败 (%s): %s", kind, e)
            out[kind] = {"written": False, "rows": 0, "reason": "fetch failed"}
            continue
        if not rows:
            out[kind] = {"written": False, "rows": 0, "reason": "empty snapshot"}
            continue
        dimension_field = _dimension_field(config, "concept" if kind == "gn_ths" else "industry")
        if not dimension_field:
            dimension_field = config.fields[0].name
        captured_at = datetime.now().astimezone().isoformat()
        part_path = _write_partition(
            data_dir,
            kind,
            as_of,
            rows,
            source_url=config.pull.url,
            fetched_at=captured_at,
            captured_at=captured_at,
            dimension_field=dimension_field,
        )
        if part_path is not None:
            out[kind] = {"written": True, "rows": len(rows)}
        else:
            out[kind] = {"written": False, "rows": 0, "reason": "write failed"}
    return out


def read_partition(data_dir: Path, kind: str, as_of: str) -> dict | None:
    """防御读 hive 分区 → ``{"rows": list[dict], "manifest": dict}``; 缺失/非法 → None。

    - 非法 as_of → None (不抛)。
    - 分区存在性判定优先 (不做 parquet date 列字符串比较 — Date dtype 陷阱)。
    - manifest 缺失 → 合成缺省 ``{"as_of", "kind"}`` (不抛)。
    - 解析异常 → logger.warning + None (镜像 load_point_snapshot 防御语义)。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        return None
    part_path = _partition_path(data_dir, kind, as_of)
    if not part_path.exists():
        return None
    try:
        df = pl.read_parquet(str(part_path))
        rows = df.to_dicts()
    except Exception as e:  # noqa: BLE001
        logger.warning("读取概念分区失败: %s", e)
        return None
    manifest: dict[str, Any] = {"as_of": as_of, "kind": kind}
    manifest_path = _manifest_path(data_dir, kind, as_of)
    if manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                manifest = raw
        except Exception as e:  # noqa: BLE001
            logger.warning("读取 manifest 失败 (合成缺省): %s", e)
    return {"rows": rows, "manifest": manifest}


def list_partition_dates(data_dir: Path, kind: str) -> list[str]:
    """列出含 part.parquet 的分区日期, ISO desc; root 缺失 → [] (镜像 list_snapshot_dates)。"""
    root = data_dir / _HISTORY_ROOT / kind
    if not root.exists():
        return []
    return sorted(
        (d.name[5:] for d in root.glob("date=*") if (d / "part.parquet").exists()),
        reverse=True,
    )


def partition_sha256(data_dir: Path, kind: str, as_of: str) -> str | None:
    """分区 part.parquet 内容 sha256; 分区缺失/非法 as_of → None (探针/幂等判定用)。"""
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        return None
    part_path = _partition_path(data_dir, kind, as_of)
    if not part_path.exists():
        return None
    return _sha256_file(part_path)
