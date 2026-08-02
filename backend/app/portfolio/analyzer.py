"""Phase 12 风险分析编排器 — run_attribution / run_drawdown (RSK-01/03).

职责: 加载 Phase 11 不可变 run 记录 → 按 risk_model_detail.covariance_sha256
对协方差工件做 checksum 校验读取 (绝不重算 live covariance) → 暴露度/边际贡献
归因 + 硬对账 → O_EXCL 分析工件 (write_analysis_artifact) → append-only 证据行。
run_drawdown 走同一编排: 组合收益率 = weights @ returns.T → 水下曲线 →
回撤区间 → 逐标的 × 逐段归因 (drawdown_attribution, 段恒等式 Σc_i == 段收益
rtol 1e-10 硬断言) → 完整报告工件 + 证据行。
分析器是只读层: 绝不修改 run 记录, 任何失败都抛异常 (证据只在成功后写入)。

不知道: 求解逻辑 (optimizer.py)、优化 run 的创建 (run_optimization)、
市场时间序列 (留在 lake)。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.portfolio.artifacts import PortfolioArtifactService
from app.portfolio.attribution import (
    attribution_report,
    reconcile_attribution,
)
from app.portfolio.drawdown import (
    DRAWDOWN_DEPTH_THRESHOLD,
    DRAWDOWN_MIN_OBS,
    drawdown_attribution,
    drawdown_periods,
    underwater_curve,
)
from app.portfolio.repository import PortfolioRepository


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_checksum_verified_covariance(
    run: dict[str, Any], *, artifact_service_root: Path
) -> np.ndarray:
    """Read the run's covariance ARTIFACT, checksum-verified (never recomputed)."""
    risk_model = run["risk_model_detail"]
    service = PortfolioArtifactService(artifact_service_root)
    content = service.read_artifact(
        risk_model["covariance_artifact_relative_path"],
        checksum_sha256=risk_model["covariance_sha256"],
    )
    matrix = np.asarray(json.loads(content.decode("utf-8")), dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("covariance artifact must decode to a square matrix")
    return matrix


def run_attribution(
    run_id: str,
    *,
    repository: PortfolioRepository,
    artifact_service_root: Path,
) -> dict[str, Any]:
    """Exposure + marginal-contribution attribution for one run, append-only evidence.

    跨模块完整性: 协方差来自 run 自己的工件字节 (covariance_sha256 校验), 归因在
    该字节上硬对账 sum(MC) == wᵀΣw (rtol 1e-12), 然后写 O_EXCL 工件 + 证据行。

    Args:
        run_id: portfolio_optimization_runs.id。
        repository: PortfolioRepository。
        artifact_service_root: PortfolioArtifactService 的工件根目录。

    Returns:
        record_attribution_evidence 返回的记录 (reconciliation 已展开)。

    Raises:
        ValueError: run 不存在或缺少 output_weights。
        ArtifactReadError: 协方差工件缺失 / checksum 不匹配。
        AssertionError: 对账失败 (hard, 绝不近似)。
    """
    run = repository.get_optimization_run(run_id)
    if run is None:
        raise ValueError(f"no optimization run with id {run_id}")
    weights_map = run.get("output_weights")
    if not weights_map:
        raise ValueError(f"run {run_id} has no output weights (problem_status must be optimal)")
    cov = _load_checksum_verified_covariance(run, artifact_service_root=artifact_service_root)

    symbols = list(weights_map.keys())
    weights = np.asarray(list(weights_map.values()), dtype=float)
    # 完整报告: 带符号暴露 + MC + 摘要 (top contributors / diversifiers)。
    # 负 MC = 分散化贡献, 绝不 abs (sum identity 依赖带符号分量)。
    report = attribution_report(weights, symbols, cov)
    variance = report["portfolio_variance"]
    exposure = report["exposure"]
    mc = report["marginal_contributions"]
    # 硬对账: sum(MC) == wᵀΣw (rtol 1e-12, 绝不近似)。传入报告记录的
    # 精确 MC 字典值 (与工件 payload 一致的带符号向量)。
    mc_vector = np.asarray(list(mc.values()), dtype=float)
    reconciliation = reconcile_attribution(weights, cov, mc_vector, variance, symbols=symbols)

    analysis_id = uuid.uuid4().hex
    descriptor = PortfolioArtifactService(artifact_service_root).write_analysis_artifact(
        run_id,
        subdir="attribution",
        filename=f"exposure_contribution-{analysis_id}.json",
        payload={
            "run_id": run_id,
            "as_of": run["as_of"],
            "symbols": symbols,
            "weights": weights.round(8).tolist(),
            "exposure": {key: round(value, 8) for key, value in exposure.items()},
            "marginal_contributions": mc,
            "portfolio_variance": variance,
            "reconciliation": {
                "sum_contributions": reconciliation["sum_contributions"],
                "max_abs_error": reconciliation["max_abs_error"],
            },
            "summary": report["summary"],
        },
    )
    return repository.record_attribution_evidence(
        id=analysis_id,
        attribution_type="exposure_contribution",
        run_id=run_id,
        risk_model=run["risk_model"],
        as_of=run["as_of"],
        output_sha256=descriptor.checksum_sha256,
        artifact_relative_path=descriptor.relative_path,
        reconciliation_json={
            "portfolio_variance": reconciliation["portfolio_variance"],
            "sum_contributions": reconciliation["sum_contributions"],
            "max_abs_error": reconciliation["max_abs_error"],
        },
        created_at=_now(),
    )


def run_drawdown(
    run_id: str,
    *,
    returns: np.ndarray,
    repository: PortfolioRepository,
    artifact_service_root: Path,
) -> dict[str, Any]:
    """水下曲线 + 回撤区间 + 逐标的 × 逐段归因, append-only 证据 (RSK-03)。

    完整报告 (12-06): 权重来自 run 行, 组合收益率 = weights @ returns.T,
    underwater_curve + drawdown_periods + drawdown_attribution (段恒等式
    Σc_i == 段收益 rtol 1e-10 硬断言 —— 写任何证据之前必须成立), 写
    drawdown.json (水下曲线 + 逐段归因表), 证据行 reconciliation 带
    period_count / max_depth / longest_period / segment_max_abs_error /
深度与最短持续阈值常量 (模块常量, 非魔法数字)。空 periods →
{"periods": [], "max_depth": 0.0, "longest_period": 0,
"segment_reconciliation_max_abs_error": 0.0} (恒等式 vacuous)。

    Args:
        run_id: portfolio_optimization_runs.id。
        returns: (n_obs, n_assets) 收益率面板 (列与 run 的 output_weights 对齐)。
        repository: PortfolioRepository。
        artifact_service_root: PortfolioArtifactService 的工件根目录。

    Returns:
        record_attribution_evidence 返回的记录 (reconciliation 已展开)。

    Raises:
        ValueError: run 不存在 / 无 output_weights / 收益率面板非有限或列数不齐。
        AssertionError: 段恒等式对账失败 (hard, 绝不近似 —— 不写任何证据)。
    """
    run = repository.get_optimization_run(run_id)
    if run is None:
        raise ValueError(f"no optimization run with id {run_id}")
    weights_map = run.get("output_weights")
    if not weights_map:
        raise ValueError(f"run {run_id} has no output weights (problem_status must be optimal)")
    panel = np.asarray(returns, dtype=float)
    if panel.ndim != 2:
        raise ValueError("returns must be a 2-D panel")
    if not np.all(np.isfinite(panel)):
        raise ValueError("returns must be finite")
    weights = np.asarray(list(weights_map.values()), dtype=float)
    if panel.shape[1] != weights.shape[0]:
        raise ValueError(
            "returns columns must align with the run's output_weights "
            f"(expected {weights.shape[0]}, got {panel.shape[1]})"
        )
    portfolio_returns = weights @ panel.T
    underwater = underwater_curve(portfolio_returns)
    periods = drawdown_periods(underwater)
    # 完整归因报告: 逐标的 × 逐段分解 + 摘要。段恒等式在写证据前硬断言。
    attribution = drawdown_attribution(
        weights, panel, periods, symbols=list(weights_map.keys())
    )
    max_depth = attribution["max_depth"]

    analysis_id = uuid.uuid4().hex
    descriptor = PortfolioArtifactService(artifact_service_root).write_analysis_artifact(
        run_id,
        subdir="attribution",
        filename=f"drawdown-{analysis_id}.json",
        payload={
            "run_id": run_id,
            "symbols": list(weights_map.keys()),
            "underwater": underwater.round(8).tolist(),
            "periods": attribution["periods"],
            "max_depth": max_depth,
            "longest_period": attribution["longest_period"],
            "segment_reconciliation_max_abs_error": attribution[
                "segment_reconciliation_max_abs_error"
            ],
            "depth_threshold": DRAWDOWN_DEPTH_THRESHOLD,
            "min_obs": DRAWDOWN_MIN_OBS,
        },
    )
    return repository.record_attribution_evidence(
        id=analysis_id,
        attribution_type="drawdown",
        run_id=run_id,
        risk_model=run["risk_model"],
        as_of=run["as_of"],
        output_sha256=descriptor.checksum_sha256,
        artifact_relative_path=descriptor.relative_path,
        reconciliation_json={
            "period_count": len(periods),
            "max_depth": max_depth,
            "longest_period": attribution["longest_period"],
            "segment_max_abs_error": attribution["segment_reconciliation_max_abs_error"],
            "depth_threshold": DRAWDOWN_DEPTH_THRESHOLD,
            "min_obs": DRAWDOWN_MIN_OBS,
        },
        created_at=_now(),
    )
