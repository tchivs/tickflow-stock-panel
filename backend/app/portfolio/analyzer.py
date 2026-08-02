"""Phase 12 风险分析编排器 — run_attribution / run_drawdown (RSK-01/03).

职责: 加载 Phase 11 不可变 run 记录 → 按 risk_model_detail.covariance_sha256
对协方差工件做 checksum 校验读取 (绝不重算 live covariance) → 暴露度/边际贡献
归因 + 硬对账 → O_EXCL 分析工件 (write_analysis_artifact) → append-only 证据行。
run_drawdown 走同一编排: 组合收益率 = weights @ returns.T → 水下曲线 →
回撤区间 → 逐标的 x 逐段归因 (drawdown_attribution, 段恒等式 Σc_i == 段收益
rtol 1e-10 硬断言) → 完整报告工件 + 证据行。
分析器是只读层: 绝不修改 run 记录, 任何失败都抛异常 (证据只在成功后写入)。

不知道: 求解逻辑 (optimizer.py)、优化 run 的创建 (run_optimization)、
市场时间序列 (留在 lake)。
"""

from __future__ import annotations

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
from app.portfolio.risk import load_covariance_artifact, make_risk_model_family

# IN-03: 四种 RSK-02 模型名的唯一权威来源是 schemas.RiskModel (Literal) 与
# repository._RISK_MODELS / _RISK_MODELS_PHASE12 (frozenset)。此处是第三个
# 定义点 — 三者必须同步 (新增第五个模型时 reconcile_all_models 才不会静默遗漏)。
# 备选: 从 schemas.RiskModel values 派生 (见 12-05/12-06 计划的 Phase 13 接缝)。
_RISK_MODEL_NAMES = (
    "sample_covariance_v1",
    "semi_covariance_v1",
    "ewma_covariance_v1",
    "ledoit_wolf_v1",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def run_attribution(
    run_id: str,
    *,
    repository: PortfolioRepository,
    artifact_service_root: Path,
    returns: np.ndarray | None = None,
    risk_model_name: str | None = None,
) -> dict[str, Any]:
    """Exposure + marginal-contribution attribution for one run, append-only evidence.

    跨模块完整性: 协方差只有两个允许来源 —— (1) 身份路径 (risk_model_name=None):
    run 自己的工件字节 (covariance_sha256 校验读取, 绝不重算); (2) 模型选择路径
    (risk_model_name + returns): 从调用方提供的收益率面板用 make_risk_model_family
    重算所选模型的协方差 (同一 PSD gate)。两条路径都在该协方差上硬对账
    sum(MC) == wᵀΣw (rtol 1e-12), 然后写 O_EXCL 工件 + 证据行。证据行的
    risk_model 记录实际使用的模型名 (选择路径可能不同于 run 行记录的模型)。

    Args:
        run_id: portfolio_optimization_runs.id。
        repository: PortfolioRepository。
        artifact_service_root: PortfolioArtifactService 的工件根目录。
        returns: 模型选择路径必需的收益率面板 (n_obs, n_assets), 列与 run 的
            output_weights 顺序对齐; 身份路径绝不读取。
        risk_model_name: 四种 RSK-02 模型名之一; None = 身份路径 (checksum 绑定
            工件字节)。

    Returns:
        record_attribution_evidence 返回的记录 (reconciliation 已展开)。

    Raises:
        ValueError: run 不存在或缺少 output_weights / 选择路径缺 returns 或
            面板与权重不对齐。
        ArtifactReadError: 身份路径协方差工件缺失 / checksum 不匹配。
        AssertionError: 对账失败 (hard, 绝不近似)。
    """
    run = repository.get_optimization_run(run_id)
    if run is None:
        raise ValueError(f"no optimization run with id {run_id}")
    weights_map = run.get("output_weights")
    if not weights_map:
        raise ValueError(f"run {run_id} has no output weights (problem_status must be optimal)")

    symbols = list(weights_map.keys())
    weights = np.asarray(list(weights_map.values()), dtype=float)
    if risk_model_name is None:
        if returns is not None:
            raise ValueError("returns are only used with risk_model_name (identity path reads the artifact)")
        cov = load_covariance_artifact(run, artifact_service_root=artifact_service_root)
        evidence_risk_model = run["risk_model"]
        # WR-03: 身份路径也记录协方差摘要 + 来源 ("artifact") —— 证据行自证绑定
        # 到 run 记录的 checksum 工件字节 (Phase 15 可独立核验)。
        covariance_sha256 = run["risk_model_detail"]["covariance_sha256"]
        covariance_source = "artifact"
    else:
        if returns is None:
            raise ValueError("returns are required when risk_model_name is selected")
        panel = np.asarray(returns, dtype=float)
        if panel.ndim != 2 or panel.shape[1] != weights.shape[0]:
            raise ValueError(
                "returns columns must align with the run's output_weights "
                f"(expected {weights.shape[0]}, got {panel.shape[1]})"
            )
        # 与 run_drawdown 相同的 fail-closed 契约: 非有限收益率绝不静默进入
        # 风险模型构建 (dropna 会收缩窗口, 产出看似有效的协方差与证据行)。
        if not np.all(np.isfinite(panel)):
            raise ValueError("returns must be finite")
        block = make_risk_model_family(panel, risk_model_name=risk_model_name)
        cov = block["covariance"]
        evidence_risk_model = risk_model_name
        # WR-03: 选择路径重算协方差 — 证据行记录协方差摘要与来源 ("recompute"),
        # 使 Phase 15 消费者能区分 checksum 绑定工件分析 vs 调用方 returns 重算。
        covariance_sha256 = block["risk_model_json"]["covariance_sha256"]
        covariance_source = "recompute"

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
            "risk_model": evidence_risk_model,
            "as_of": run["as_of"],
            "symbols": symbols,
            "weights": weights.round(8).tolist(),
            "exposure": {key: round(value, 8) for key, value in exposure.items()},
            "marginal_contributions": mc,
            "portfolio_variance": variance,
            "covariance_sha256": covariance_sha256,
            "covariance_source": covariance_source,
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
        risk_model=evidence_risk_model,
        as_of=run["as_of"],
        output_sha256=descriptor.checksum_sha256,
        artifact_relative_path=descriptor.relative_path,
        reconciliation_json={
            "portfolio_variance": reconciliation["portfolio_variance"],
            "sum_contributions": reconciliation["sum_contributions"],
            "max_abs_error": reconciliation["max_abs_error"],
            "covariance_sha256": covariance_sha256,
            "covariance_source": covariance_source,
        },
        created_at=_now(),
    )


def reconcile_all_models(
    run_id: str,
    *,
    returns: np.ndarray,
    repository: PortfolioRepository,
    artifact_service_root: Path,
) -> dict[str, Any]:
    """Cross-model reconciliation matrix — every RSK-02 model reconciles exactly.

    对四种风险模型各做一次归因并硬对账 (sum(MC) == wᵀΣw, rtol 1e-12), 返回
    model x variance x sum(MC) x max abs error 矩阵。run 自己记录的模型行
    (identity row) 走 checksum 绑定工件路径 (load_covariance_artifact), 其余
    模型行从 returns 重算 (make_risk_model_family)。任一模型对账失败抛
    AssertionError (hard abort —— 绝不返回部分成功矩阵)。不写证据 (integrity
    report, 不是一次新分析)。

    Args:
        run_id: portfolio_optimization_runs.id。
        returns: (n_obs, n_assets) 收益率面板, 列与 run 的 output_weights 对齐。
        repository: PortfolioRepository。
        artifact_service_root: PortfolioArtifactService 的工件根目录。

    Returns:
        {"run_id", "models": [{risk_model, portfolio_variance, sum_contributions,
        max_abs_error, reconciled}], "all_reconciled": bool}。

    Raises:
        ValueError: run 不存在或缺少 output_weights / 面板不对齐。
        ArtifactReadError: 身份路径协方差工件缺失 / checksum 不匹配。
        AssertionError: 任一模型对账失败 (hard)。
    """
    run = repository.get_optimization_run(run_id)
    if run is None:
        raise ValueError(f"no optimization run with id {run_id}")
    weights_map = run.get("output_weights")
    if not weights_map:
        raise ValueError(f"run {run_id} has no output weights (problem_status must be optimal)")
    symbols = list(weights_map.keys())
    weights = np.asarray(list(weights_map.values()), dtype=float)
    panel = np.asarray(returns, dtype=float)
    if panel.ndim != 2 or panel.shape[1] != weights.shape[0]:
        raise ValueError(
            "returns columns must align with the run's output_weights "
            f"(expected {weights.shape[0]}, got {panel.shape[1]})"
        )
    # 同 run_attribution 选择路径的 fail-closed 契约: 非有限收益率绝不静默
    # 进入四种模型重算 (dropna 收缩窗口会掩盖数据问题, all_reconciled 变假绿)。
    if not np.all(np.isfinite(panel)):
        raise ValueError("returns must be finite")

    models: list[dict[str, Any]] = []
    for name in _RISK_MODEL_NAMES:
        if name == run["risk_model"]:
            cov = load_covariance_artifact(run, artifact_service_root=artifact_service_root)
            covariance_sha256 = run["risk_model_detail"]["covariance_sha256"]
        else:
            block = make_risk_model_family(panel, risk_model_name=name)
            cov = block["covariance"]
            covariance_sha256 = block["risk_model_json"]["covariance_sha256"]
        report = attribution_report(weights, symbols, cov)  # 内部硬对账, 失败抛 AssertionError
        variance = report["portfolio_variance"]
        sum_contributions = report["sum_contributions"]
        max_abs_error = report["reconciliation_error"]
        reconciled = bool(max_abs_error <= 1e-12 * variance + 1e-15)
        models.append(
            {
                "risk_model": name,
                "portfolio_variance": variance,
                "sum_contributions": sum_contributions,
                "max_abs_error": max_abs_error,
                "reconciled": reconciled,
                "covariance_sha256": covariance_sha256,
            }
        )
    return {
        "run_id": run_id,
        "models": models,
        "all_reconciled": all(model["reconciled"] for model in models),
    }


def run_drawdown(
    run_id: str,
    *,
    returns: np.ndarray,
    repository: PortfolioRepository,
    artifact_service_root: Path,
) -> dict[str, Any]:
    """水下曲线 + 回撤区间 + 逐标的 x 逐段归因, append-only 证据 (RSK-03)。

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
    # 完整归因报告: 逐标的 x 逐段分解 + 摘要。段恒等式在写证据前硬断言。
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
