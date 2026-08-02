"""Rank-average 集成 (WFWD-03) — 对已验证策略的逐日横截面 _rank 做加权平均。

知道: 对多个已验证 (wf_validated_strategies.passed_gate=1) 策略的链信号做
      per-(symbol, date) 的 _rank 加权平均 (纯 Polars, 无 scipy / 手写 rank 循环),
      输出 [symbol, date, ensemble_rank, ensemble_zscore]; 校验通过门禁
      (validation_record_ids 必须解析为 passed_gate=1 的裁决行, 任一策略无
      passed_gate=1 记录则 fail-closed ValueError); 产物经
      EvaluationArtifactService 写入不可变命名空间 (O_EXCL + fsync + sha256),
      wf_ensembles 行绑定 input_snapshot_sha256 (strategy_ids, weights,
      validation_record_ids, membership_fingerprint) 与 output_sha256 /
      artifact_relative_path。
不知道: 因子计算 (FactorSignalChain 黑盒)、walk-forward 折叠几何、策略回测、
      仓储/迁移内部实现。集成权重默认等权 1/n (discretion, 冻结进输入快照)。

rank-average 语义 (13-RESEARCH.md `## Rank-Average Ensembling`):
  mean_rank(symbol, date) = Σ_s w_s x _rank_s(symbol, date)
  ensemble_rank  = mean_rank 按日期二次 rank (method="max") — 即"逐日对秩均值
                   再排序"的秩。method="max" 使平局保留平局高度 (均值 2.0 →
                   ensemble_rank 2.0, 满足脚手架契约); 若用 method="average"
                   平局会塌缩为 1.5 而违背契约 (13-04-SUMMARY 记录)。
  ensemble_zscore = (mean_rank - mean(mean_rank).over(date)) / std(mean_rank).over(date)
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import polars as pl

from app.research.repository import ResearchRepository

# 门禁查询最大行数 (单个 ensemble 的验证裁决数远小于此)。
_LIST_CAP = 100_000


@dataclass(frozen=True, slots=True)
class EnsembleConfig:
    """一次 rank-average 集成的输入契约 (冻结, slots)。

    - ``strategy_ids``: 参与集成的策略 id (调用方保证排序以确定性复用)。
    - ``weights``: 每策略权重; 缺省 (None) = 等权 1/n。
    - ``validation_record_ids``: wf_validated_strategies 裁决行 id, 全部须
      passed_gate=1 — 这是 WFWD-03 门禁的入参。
    """

    strategy_ids: tuple[str, ...]
    weights: Mapping[str, float] | None = None
    validation_record_ids: tuple[str, ...] = ()


def build_ensemble(
    *,
    config: EnsembleConfig,
    signals: Mapping[str, pl.DataFrame],
    universe: str,
    start: Any,
    end: Any,
    horizon: int,
    repo: ResearchRepository,
) -> pl.DataFrame:
    """对已验证策略的 ``_rank`` 信号做 per-(symbol, date) 加权平均集成。

    1. 门禁 (validated-only): 每个 validation_record_id 必须解析为
       passed_gate=1 裁决行; 任一 strategy_id 无 passed_gate=1 记录 → ValueError
       (fail-closed, WFWD-03)。repo 为必填 — 缺省即跳过门禁等于放开门禁, 禁止。
    2. 权重: config.weights 缺省时等权 1/n; 显式给出时须覆盖全部 strategy_id。
    3. rank-average: 各策略帧纵向堆叠后 group_by(symbol, date) 计算加权秩均值;
       输出 [symbol, date, ensemble_rank, ensemble_zscore], 窗口裁剪到
       [start, end]。

    ``universe`` / ``horizon`` 是 Phase 14 消费接口的求值元数据, 本纯秩平均
    数学不直接使用 (链帧的 _rank 已由上游按 horizon 生成)。
    """
    weights = _effective_weights(config)
    _validate_gate(config, repo)

    pieces: list[pl.DataFrame] = []
    lo = _to_date(start)
    hi = _to_date(end)
    for sid in config.strategy_ids:
        frame = signals.get(sid)
        if frame is None:
            raise ValueError(f"strategy {sid} has no signal frame")
        missing = {"symbol", "date", "_rank"} - set(frame.columns)
        if missing:
            raise ValueError(f"strategy {sid} frame is missing columns: {sorted(missing)}")
        frame = frame.select(["symbol", "date", "_rank"])
        # IN-03: 用 pl.Date 字面量比较, 而不是字符串词法比较 — 链的 Date 列与测试的
        # Utf8 列都能正确处理; Datetime 列也会先 cast 到 Date 再比较 (字符串比较对
        # Datetime 序列化 "2026-07-01 00:00:00" 会失败)。
        frame = frame.filter(
            (pl.col("date").cast(pl.Date) >= pl.lit(lo, dtype=pl.Date))
            & (pl.col("date").cast(pl.Date) <= pl.lit(hi, dtype=pl.Date))
        )
        pieces.append(frame.with_columns(pl.lit(weights[sid], dtype=pl.Float64).alias("_w")))
    if not pieces:
        raise ValueError("ensemble requires at least one strategy signal frame")

    long = pl.concat(pieces, how="vertical")
    mean_rank = (
        long.group_by(["symbol", "date"])
        .agg(
            (pl.col("_rank").cast(pl.Float64) * pl.col("_w")).sum().alias("_wsum"),
            pl.col("_w").sum().alias("_wtotal"),
        )
        .with_columns((pl.col("_wsum") / pl.col("_wtotal")).alias("_mean_rank"))
    )
    out = mean_rank.with_columns(
        pl.col("_mean_rank")
        .rank(method="max")
        .over("date")
        .cast(pl.Float64)
        .alias("ensemble_rank"),
        (
            (pl.col("_mean_rank") - pl.col("_mean_rank").mean().over("date"))
            / pl.col("_mean_rank").std().over("date")
        )
        .fill_nan(0.0)
        .fill_null(0.0)
        .alias("ensemble_zscore"),
    )
    return out.select(["symbol", "date", "ensemble_rank", "ensemble_zscore"]).sort(["date", "symbol"])


def save_ensemble(
    *,
    config: EnsembleConfig,
    frame: pl.DataFrame,
    artifact_service: Any,
    repo: ResearchRepository,
    name: str = "wf-ensemble-v1",
    membership_fingerprint: str | None = None,
) -> dict[str, Any]:
    """把集成帧持久化为 checksum 校验的不可变产物 + append-only wf_ensembles 行。

    - 门禁同 ``build_ensemble`` (fail-closed)。
    - ``input_snapshot_sha256`` = 规范化 JSON (sorted strategy_ids, weights,
      validation_record_ids, membership_fingerprint) 的 sha256; fingerprint
      缺省时由帧的 (symbol, date) 成员集派生。
    - 产物经 ``EvaluationArtifactService.write_bundle`` 写入 (O_EXCL + fsync +
      sha256), 命名空间 run_id 由 name 确定性派生 — 同名换输入必碰撞而失败,
      绝不覆盖已留存的证据。
    - 幂等: 同名且 input_snapshot_sha256 相同的已存行直接返回; 同名不同输入则
      ValueError (O_EXCL 语义)。
    """
    weights = _effective_weights(config)
    _validate_gate(config, repo)
    fingerprint = membership_fingerprint or _frame_membership_fingerprint(frame)
    snapshot = _input_snapshot_sha256(config, weights, fingerprint)

    for existing in repo.list_wf_ensembles(limit=_LIST_CAP):
        if existing["name"] != name:
            continue
        if existing["input_snapshot_sha256"] == snapshot:
            return {"row": existing, "descriptor": None, "input_snapshot_sha256": snapshot, "idempotent": True}
        raise ValueError(f"ensemble '{name}' already persisted with a different input snapshot")

    run_id = hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]
    rows = [
        {
            "symbol": str(row["symbol"]),
            "date": str(row["date"]),
            "ensemble_rank": float(row["ensemble_rank"]),
            "ensemble_zscore": float(row["ensemble_zscore"]),
        }
        for row in frame.sort(["date", "symbol"]).iter_rows(named=True)
    ]
    descriptors = artifact_service.write_bundle(
        run_id,
        signals=rows,
        metric_series=[],
        result={
            "ensemble_output": "signals.json",
            "columns": ["symbol", "date", "ensemble_rank", "ensemble_zscore"],
            "input_snapshot_sha256": snapshot,
        },
    )
    signals_desc = next(desc for desc in descriptors if desc.relative_path.endswith("signals.json"))
    row = repo.record_wf_ensemble(
        name=name,
        strategy_ids=list(config.strategy_ids),
        weights=weights,
        validation_record_ids=list(config.validation_record_ids),
        input_snapshot_sha256=snapshot,
        output_sha256=signals_desc.checksum_sha256,
        artifact_relative_path=signals_desc.relative_path,
    )
    return {"row": row, "descriptor": signals_desc.as_dict(), "input_snapshot_sha256": snapshot, "idempotent": False}


# ================================================================
# 门禁 / 权重 / 快照工具
# ================================================================


def _validate_gate(config: EnsembleConfig, repo: ResearchRepository) -> None:
    """Validated-only 门禁: 每个策略须有 passed_gate=1 裁决, 每个记录 id 须可解析。"""
    passed_ids: set[str] = set()
    for sid in config.strategy_ids:
        rows = repo.list_validated_strategies(strategy_id=sid, passed_gate=True, limit=_LIST_CAP)
        if not rows:
            raise ValueError(f"strategy {sid} is not validated (no passed_gate=1 verdict)")
        passed_ids.update(row["id"] for row in rows)
    for rid in config.validation_record_ids:
        if rid not in passed_ids:
            raise ValueError(f"validation record {rid} is not validated (no passed_gate=1 verdict)")


def _effective_weights(config: EnsembleConfig) -> dict[str, float]:
    """解析权重: 缺省等权 1/n; 显式时须覆盖全部策略且为正。"""
    if config.weights is None:
        count = len(config.strategy_ids)
        if count == 0:
            raise ValueError("ensemble requires at least one strategy")
        return {sid: 1.0 / count for sid in config.strategy_ids}
    weights = dict(config.weights)
    missing = [sid for sid in config.strategy_ids if sid not in weights]
    if missing:
        raise ValueError(f"missing weights for strategies: {', '.join(missing)}")
    for sid, weight in weights.items():
        if weight <= 0:
            raise ValueError(f"strategy {sid} weight must be positive")
    return weights


def _frame_membership_fingerprint(frame: pl.DataFrame) -> str:
    """帧的 (symbol, date) 成员集 sha256 — 与 conftest._membership_fingerprint 同构。"""
    ordered = frame.select(["symbol", "date"]).unique().sort(["symbol", "date"])
    payload = "|".join(f"{row['symbol']}:{row['date']}" for row in ordered.iter_rows(named=True))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _input_snapshot_sha256(
    config: EnsembleConfig, weights: Mapping[str, float], fingerprint: str
) -> str:
    """输入快照 = (sorted strategy_ids, weights, validation_record_ids, fingerprint)。"""
    payload = json.dumps(
        {
            "strategy_ids": sorted(config.strategy_ids),
            "weights": {sid: weights[sid] for sid in sorted(weights)},
            "validation_record_ids": sorted(config.validation_record_ids),
            "membership_fingerprint": fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _iso(value: Any) -> str:
    """``date``/``datetime``/``str`` → ISO 字符串 (窗口比较用)。"""
    iso = getattr(value, "isoformat", None)
    return iso() if iso is not None else str(value)


def _to_date(value: Any) -> object:
    """``date``/``datetime``/``str`` → 归一化 ``date`` (pl.Date 字面量用, IN-03)。"""
    from datetime import date as _date

    if isinstance(value, _date):
        return value
    if isinstance(value, str):
        return _date.fromisoformat(value[:10])
    iso = getattr(value, "isoformat", None)
    return _date.fromisoformat(iso()[:10]) if iso is not None else value
