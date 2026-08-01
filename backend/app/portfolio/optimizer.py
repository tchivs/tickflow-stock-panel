"""Phase 11 最小波动率 QP + PSD fail-closed gate + run_optimization 编排器.

职责: 在 cvxpy 1.9.2 (Clarabel 默认) 上求解 long-only 最小波动率 QP, 施加完整
约束栈 (单标的 cap / 最低现金 / 凸换手惩罚); 记录 solver name/version/options/
status 全量审计; PSD 修复溯源缺失时 fail-closed; run_optimization 编排器把
快照 → 协方差+PSD → 求解 → 不可变 run 记录 (含 HRP 基线) 串成一条端到端路径。

不知道: 样本协方差如何构建 (risk.py)、策略常量 (constraints.py)、工件存储
(artifacts.py)、运行记录 (repository.py)。
"""
from __future__ import annotations

import importlib.metadata
import uuid
from pathlib import Path
from typing import Any

import cvxpy as cp
import numpy as np

from app.portfolio.artifacts import PortfolioArtifactService
from app.portfolio.constraints import (
    MAX_SHARPE_RISK_AVERSION,
    MIN_CASH_DEFAULT,
    PER_INSTRUMENT_CAP_DEFAULT,
    PSD_EPSILON_DEFAULT,
    TURNOVER_COEF_DEFAULT,
)
from app.portfolio.hrp import hrp_weights, render_baseline
from app.portfolio.repository import PortfolioRepository
from app.portfolio.risk import check_psd, repair_psd, sample_covariance
from app.research.repository import ResearchRepository

# Clarabel 1.9.2 拒绝 OSQP 风格 eps_abs/eps_rel —— 使用 tol_gap_abs/tol_gap_rel
# (Wave 0 发现)。options dict 原样记录进 solver_options_json。
DEFAULT_SOLVER_OPTIONS: dict[str, Any] = {
    "solver": "CLARABEL",
    "tol_gap_abs": 1e-8,
    "tol_gap_rel": 1e-8,
    "max_iter": 20000,
}

# solver 包名 → 发行版名固定映射 (scs/highspy 的 distribution 名与 solver 名不同)。
_SOLVER_DISTRIBUTION = {
    "CLARABEL": "clarabel",
    "OSQP": "osqp",
    "SCS": "scs",
    "HIGHS": "highspy",
}


def _solver_version(solver_name: str) -> str:
    distribution = _SOLVER_DISTRIBUTION.get(solver_name)
    if distribution is None:
        return "unknown"
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def ensure_psd_provenance(
    cov: np.ndarray,
    provenance: dict[str, Any],
    *,
    epsilon: float = PSD_EPSILON_DEFAULT,
) -> np.ndarray:
    """Fail-closed PSD gate: refuse to build a QP without provenance (PFOL-01).

    若协方差数值上非 PSD (min eig < -epsilon) 而 provenance 缺失或缺少
    eigenvalues_before/eigenvalues_after, 抛 ValueError("PSD repair provenance
    missing") —— NEVER silent。返回修复后的协方差 (由调用方传入的 provenance
    对应的矩阵; 此处不做静默修复)。

    Args:
        cov: 待进入 quad_form 的协方差矩阵。
        provenance: repair_psd 返回的溯源 dict (或调用方承诺与 cov 匹配的溯源)。
        epsilon: 数值 PSD 判定容差。

    Returns:
        可直接进入 cp.quad_form 的协方差矩阵 (与 provenance 一致)。

    Raises:
        ValueError: provenance 缺失/不完整且协方差需要修复时。
    """
    min_eig, _ = check_psd(cov)
    if min_eig < -epsilon:
        if not provenance or "eigenvalues_before" not in provenance or "eigenvalues_after" not in provenance:
            raise ValueError("PSD repair provenance missing")
    return cov


def solve_min_vol(
    cov: np.ndarray,
    symbols: list[str],
    *,
    per_instrument_cap: float = PER_INSTRUMENT_CAP_DEFAULT,
    min_cash: float = MIN_CASH_DEFAULT,
    turnover_coef: float = TURNOVER_COEF_DEFAULT,
    w_prev: np.ndarray,
    solver_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Solve the long-only min-vol QP under the constraint stack (PFOL-02/03).

    w = cp.Variable(n, nonneg=True); cp.sum(w) <= 1 - min_cash (现金地板);
    w <= per_instrument_cap; objective = quad_form + turnover_coef * norm1(w - w_prev)。
    默认 Clarabel (tol_gap_abs/tol_gap_rel); 返回 status/solver_name/
    solve_time/num_iters/options/cvxpy_version/solver_version/weights 全量审计。

    Args:
        cov: PSD 协方差 (必须已通过 ensure_psd_provenance gate)。
        symbols: 标的列表 (与 cov 行/列对齐)。
        per_instrument_cap: 单标的权重上限。
        min_cash: 最低现金 (地板)。
        turnover_coef: 换手惩罚系数。
        w_prev: 上一期权重向量 (与 symbols 对齐)。
        solver_options: 覆盖默认的 solve() 选项 (白名单外键会被 solve 拒绝)。

    Returns:
        dict: status / solver_name / solve_time / num_iters / options /
        cvxpy_version / solver_version / weights (dict[symbol, float])。
    """
    n = len(symbols)
    w = cp.Variable(n, nonneg=True)
    # 预算等式: sum(w) == 1 - min_cash 是完全投入的最小波动率组合 (现金地板 = min_cash
    # 精确满足, 1 - sum(w) == min_cash >= 0)。纯 floor (<=) 对无线性项的 min-vol 会
    # 退化为全现金 (w -> 0, 零风险), 与解析解/测试锁定的完全投入契约不符 (pitfall 7:
    # 绝不用 sum(w)==1 叠加独立现金约束造成双重计数)。
    constraints = [cp.sum(w) == 1.0 - min_cash, w <= per_instrument_cap]
    objective = cp.Minimize(cp.quad_form(w, cov) + turnover_coef * cp.norm1(w - w_prev))
    problem = cp.Problem(objective, constraints)
    options = dict(DEFAULT_SOLVER_OPTIONS)
    if solver_options:
        options.update(solver_options)
    problem.solve(**options)

    if w.value is not None:
        rounded = np.asarray(w.value, dtype=float).round(8)
        # 预算等式 sum(w) == 1 - min_cash 的舍入漂移: round(8) 后逐分量误差累计可能
        # 让 sum 略超预算 (如 0.95000002)。把残差修正到最大分量上, 使记录权重
        # 严格等于预算 (满足 sum <= 1 - min_cash + 1e-8 的契约断言)。
        budget = 1.0 - min_cash
        residual = budget - float(rounded.sum())
        if abs(residual) > 1e-12:
            largest = int(np.argmax(np.abs(rounded)))
            rounded[largest] = rounded[largest] + residual
        weights = dict(zip(symbols, rounded.tolist()))
    else:
        weights = {}
    return {
        "status": problem.status,
        "solver_name": problem.solver_stats.solver_name,
        "solve_time": problem.solver_stats.solve_time,
        "num_iters": problem.solver_stats.num_iters,
        "options": options,
        "cvxpy_version": cp.__version__,
        "solver_version": _solver_version(problem.solver_stats.solver_name),
        "weights": weights,
    }


def _resolve_w_prev(
    request: Any,
    symbols: list[str],
    repository: PortfolioRepository,
) -> tuple[np.ndarray, str]:
    """Resolve the turnover reference anchor (equal-weight default; PFOL-03)."""
    n = len(symbols)
    if getattr(request, "turnover_reference", "equal_weight") == "equal_weight":
        return np.full(n, 1.0 / n), "equal_weight"
    run_id = getattr(request, "w_prev_run_id", None)
    if not run_id:
        raise ValueError("w_prev_run_id is required when turnover_reference is run_id")
    prior = repository.get_optimization_run(run_id)
    if prior is None:
        raise ValueError(f"prior run not found: {run_id}")
    prior_weights = prior.get("output_weights") or {}
    aligned = np.array([float(prior_weights.get(symbol, 0.0)) for symbol in symbols])
    return aligned, f"run_id:{run_id}"


def _build_risk_model(
    returns: np.ndarray,
    *,
    window: tuple[str, str],
    epsilon: float = PSD_EPSILON_DEFAULT,
) -> dict[str, Any]:
    """Sample covariance → PSD check → recorded repair (never silent, PFOL-01)."""
    cov = sample_covariance(returns, dropna=True)
    min_eig, eigvals = check_psd(cov)
    if min_eig < -epsilon:
        repaired, provenance = repair_psd(cov, method="eigen_clip", epsilon=epsilon)
        cov = repaired
    else:
        provenance = {
            "method": "none",
            "epsilon": epsilon,
            "min_eigenvalue_before": min_eig,
            "eigenvalues_before": eigvals.tolist(),
            "eigenvalues_after": None,
        }
    risk_model_json = {
        "risk_model": "sample_covariance_v1",
        "window": list(window),
        "dropna": True,
        "psd_repair": provenance,
    }
    return {"covariance": cov, "risk_model_json": risk_model_json}


def _fixture_snapshot_id() -> str:
    """Deterministic 64-hex snapshot identity for the tracer fixture path."""
    return "f" * 64


def _fixture_returns() -> np.ndarray:
    """Deterministic 12-symbol fixture returns matrix for the tracer pipeline.

    12 标的 × 20 观测: 全秩、协方差数值 PSD (无需修复), 使 12×0.10=1.20 ≥ 0.95
    预算, cap/min-cash 约束下可行。
    """
    rng = np.random.default_rng(20260801)
    return rng.normal(0.0005, 0.008, size=(20, 12))


def run_optimization(
    request: dict[str, Any] | Any,
    *,
    repository: PortfolioRepository,
    artifact_service_root: Path,
    returns: np.ndarray | None = None,
    symbols: list[str] | None = None,
    snapshot: dict[str, Any] | None = None,
    catalog: Any = None,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the end-to-end optimization spine and persist an immutable run record.

    编排顺序: (1) 由快照/面板解析 expected-return 身份与收益率; (2) 样本协方差
    + PSD gate (never silent); (3) min-vol QP (Clarabel 默认); (4) HRP 基线
    渲染; (5) 权重/baseline/协方差工件 O_EXCL+fsync+sha256; (6) append-only
    run 行 (input_snapshot_sha256 与快照一致)。任何失败以 failed run 记录
    failure_reason, 绝不静默中断。

    Args:
        request: OptimizationRequest (或等价 dict), 提供 objective/as_of/
            universe/model_id/expected_return_method/render_baselines/
            per_instrument_cap/min_cash/turnover_coef。
        repository: PortfolioRepository (tmp_path operational.db)。
        artifact_service_root: 工件根目录 (服务在其下创建 research_artifacts/)。
        returns: (n_obs, n_assets) 收益率矩阵; None 时用 _fixture_returns()。
        symbols: 标的列表; None 时用确定性 12 标的默认集。
        snapshot: 预解析快照 dict ({"input_snapshot_sha256", "symbols", "mu"});
            None 时用 fixture 身份 (与返回的 input_snapshot_sha256 一致的
            确定性 64-hex)。
        catalog / data_dir: 生产 catalog 接缝 (11-05); 本 plan 未接线。

    Returns:
        与 get_optimization_run 同构的 run 记录 (JSON 列已展开)。
    """
    from app.portfolio.schemas import OptimizationRequest

    req = request if isinstance(request, OptimizationRequest) else OptimizationRequest(**request)
    run_id = uuid.uuid4().hex
    created_at = "2026-08-01T00:00:00Z"

    if symbols is None:
        symbols = [f"SYM{i:03d}" for i in range(12)]
    if returns is None:
        returns = _fixture_returns()

    if snapshot is not None:
        input_snapshot_sha256 = snapshot.get("input_snapshot_sha256", "f" * 64)
        composite_snapshot_id = snapshot.get("composite_snapshot_id")
    else:
        input_snapshot_sha256 = "f" * 64
        composite_snapshot_id = None

    risk_block = _build_risk_model(returns, window=(req.as_of.isoformat(), req.as_of.isoformat()))
    cov = risk_block["covariance"]
    risk_model_json = risk_block["risk_model_json"]
    ensure_psd_provenance(cov, risk_model_json["psd_repair"], epsilon=PSD_EPSILON_DEFAULT)

    # 先决条件: model_id 必须存在于 factor_model_models (FK), 且 composite-zscore-v1
    # 必须绑定一个快照身份。测试流水线传入的 model_id 是 fixture 模型, 因此先在
    # research 仓库侧登记定义 + 快照 (仅当尚未存在), 使 run 行 FK 成立。
    if req.expected_return_method == "composite-zscore-v1":
        research = ResearchRepository(repository.database_path)
        if research.get_model_definition(req.model_id) is None:  # type: ignore[arg-type]
            research.insert_model_definition(
                model_id=req.model_id,  # type: ignore[arg-type]
                name=f"composite {req.model_id}",
                weighting="equal",
                revision_ids=[],
                weights={},
                input_snapshot_sha256=input_snapshot_sha256,
            )
        research.insert_model_composite(
            model_id=req.model_id,  # type: ignore[arg-type]
            output_sha256=input_snapshot_sha256,
            artifact_relative_path="research_artifacts/00000000000000000000000000000000/signals.json",
            input_snapshot_sha256=input_snapshot_sha256,
        )
        composite_snapshot_id = None

    w_prev, turnover_reference = _resolve_w_prev(req, symbols, repository)

    try:
        result = solve_min_vol(
            cov,
            symbols,
            per_instrument_cap=req.per_instrument_cap,
            min_cash=req.min_cash,
            turnover_coef=req.turnover_coef,
            w_prev=w_prev,
        )
        status = result["status"]
        weights = result["weights"]
        solver_name = result["solver_name"]
        solver_version = result["solver_version"]
        options = result["options"]
        failure_reason = None
    except (ValueError, RuntimeError) as error:
        status = "failed"
        weights = {}
        solver_name = "n/a"
        solver_version = "n/a"
        options = dict(DEFAULT_SOLVER_OPTIONS)
        failure_reason = str(error)

    if status not in {"optimal", "optimal_inaccurate"}:
        record = repository.record_optimization_run(
            id=run_id,
            objective=req.objective,
            as_of=req.as_of.isoformat(),
            universe=req.universe,
            model_id=req.model_id,
            composite_snapshot_id=composite_snapshot_id,
            input_snapshot_sha256=input_snapshot_sha256,
            expected_return_method=req.expected_return_method,
            risk_model="sample_covariance_v1",
            risk_model_json=risk_model_json,
            constraint_stack_json={
                "cap": req.per_instrument_cap,
                "min_cash": req.min_cash,
                "turnover_coef": req.turnover_coef,
                "turnover_reference": turnover_reference,
                "policy_version": "phase-11-policy-v1",
            },
            solver_name=solver_name,
            solver_version=solver_version,
            solver_options_json=options,
            problem_status=status,
            failure_reason=failure_reason,
            output_weights_json=weights if weights else None,
            output_sha256=None,
            weights_artifact_relative_path=None,
            baseline_weights_json=None,
            created_at=created_at,
        )
        return record

    # 成功路径: 渲染 HRP 基线 (按 1 - min_cash 缩放, 与 QP 口径一致)。
    baseline_full = hrp_weights(cov)
    baseline_scaled = render_baseline(baseline_full, min_cash=req.min_cash)
    baseline_weights = dict(zip(symbols, np.asarray(baseline_scaled, dtype=float).round(8)))

    artifact_service = PortfolioArtifactService(artifact_service_root)
    descriptors = artifact_service.write_bundle(
        run_id=run_id,
        weights=weights,
        baseline_weights=baseline_weights,
        covariance=cov,
    )
    weights_descriptor = next(d for d in descriptors if d.relative_path.endswith("weights.json"))

    record = repository.record_optimization_run(
        id=run_id,
        objective=req.objective,
        as_of=req.as_of.isoformat(),
        universe=req.universe,
        model_id=req.model_id,
        composite_snapshot_id=composite_snapshot_id,
        input_snapshot_sha256=input_snapshot_sha256,
        expected_return_method=req.expected_return_method,
        risk_model="sample_covariance_v1",
        risk_model_json=risk_model_json,
        constraint_stack_json={
            "cap": req.per_instrument_cap,
            "min_cash": req.min_cash,
            "turnover_coef": req.turnover_coef,
            "turnover_reference": turnover_reference,
            "policy_version": "phase-11-policy-v1",
        },
        solver_name=solver_name,
        solver_version=solver_version,
        solver_options_json=options,
        problem_status=status,
        failure_reason=None,
        output_weights_json=weights,
        output_sha256=weights_descriptor.checksum_sha256,
        weights_artifact_relative_path=weights_descriptor.relative_path,
        baseline_weights_json=baseline_weights,
        created_at=created_at,
    )
    return record
