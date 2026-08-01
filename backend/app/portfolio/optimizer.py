"""Phase 11 最小波动率/最大夏普 QP + PSD fail-closed gate + run_optimization 编排器.

职责: 在 cvxpy 1.9.2 (Clarabel 默认 + OSQP solver_path 回退) 上求解 long-only
最小波动率/最大夏普 QP, 施加完整约束栈 (单标的 cap / 最低现金 / 凸换手惩罚);
记录 solver name/version/options/status 全量审计 (solver_path 按实际运行的
solver 记录 name/version); PSD 修复溯源缺失时 fail-closed; run_optimization
编排器把快照 → 协方差+PSD → 求解 → 不可变 run 记录 (含 HRP 基线) 串成一条
端到端路径。max_sharpe 显式非默认: 仅当 render_baselines=True 才可到达, 且
每次 max_sharpe 运行都记录 min-vol + HRP 双基线 (pitfall 2)。

不知道: 样本协方差如何构建 (risk.py)、策略常量 (constraints.py)、工件存储
(artifacts.py)、运行记录 (repository.py)。
"""
from __future__ import annotations

import importlib.metadata
import json
import sqlite3
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
    TURNOVER_REFERENCE_EQUAL_WEIGHT,
    TURNOVER_REFERENCE_RUN_ID,
)
from app.portfolio.hrp import hrp_portfolio, hrp_weights, render_baseline
from app.portfolio.repository import PortfolioRepository
from app.portfolio.risk import check_psd, repair_psd, sample_covariance
from app.portfolio.snapshot import SnapshotBindingError, load_composite_snapshot
from app.research.repository import ResearchRepository

# 策略 options dict 原样记录进 solver_options_json (PFOL-04): solver_path 声明
# CLARABEL 默认 + OSQP 回退面, eps_abs/eps_rel 是策略容差口径。cvxpy 1.9.2 不允许
# 'solver' 与 'solver_path' 同时传给 solve(), 且 CLARABEL 拒绝 OSQP 风格
# eps_abs/eps_rel (TypeError) —— 实际 solve 调用经 _solve_kwargs 适配, 记录 dict
# 保持原样。
DEFAULT_SOLVER_OPTIONS: dict[str, Any] = {
    "solver": "CLARABEL",
    "solver_path": ["CLARABEL", "OSQP"],
    "eps_abs": 1e-8,
    "eps_rel": 1e-8,
    "max_iter": 20000,
}


# solver 包名 → 发行版名固定映射 (scs/highspy 的 distribution 名与 solver 名不同)。
_SOLVER_DISTRIBUTION = {
    "CLARABEL": "clarabel",
    "OSQP": "osqp",
    "SCS": "scs",
    "HIGHS": "highspy",
}


def _solve_kwargs(options: dict[str, Any], solver: str) -> dict[str, Any]:
    """从记录的 options dict 构造单个 solver 的 solve() kwargs。

    cvxpy 1.9.2 禁止 'solver' 与 'solver_path' 同时出现; 且 CLARABEL 拒绝
    OSQP 风格 eps_abs/eps_rel (TypeError, Wave 0 发现), OSQP 拒绝 CLARABEL 风格
    tol_gap_abs/tol_gap_rel。记录的 options dict 是策略原文; 这里去掉
    solver_path、固定当前 solver, 并把容差键映射到该 solver 的命名空间。

    Args:
        options: 记录的 options dict (含 solver / solver_path / 容差键)。
        solver: 当前尝试的 solver 名 (如 "CLARABEL")。

    Returns:
        可传给 problem.solve(**kwargs) 的 dict。
    """
    kwargs = dict(options)
    kwargs.pop("solver_path", None)
    kwargs["solver"] = solver
    if solver == "CLARABEL":
        if "eps_abs" in kwargs:
            kwargs["tol_gap_abs"] = kwargs.pop("eps_abs")
        if "eps_rel" in kwargs:
            kwargs["tol_gap_rel"] = kwargs.pop("eps_rel")
        kwargs.pop("polish", None)
    else:
        kwargs.pop("tol_gap_abs", None)
        kwargs.pop("tol_gap_rel", None)
    return kwargs


def _solve_problem(problem: cp.Problem, options: dict[str, Any]) -> str:
    """按 solver_path 依次求解, 返回实际运行的 solver 名。

    solver_path=["CLARABEL", "OSQP"]: 先 CLARABEL; 仅当 CLARABEL 抛出
    SolverError (求解器崩溃) 时才回退 OSQP。任一 solver 返回状态 (optimal /
    optimal_inaccurate / infeasible / unbounded / user_limit) 即记录该诚实状态 ——
    绝不在 non-optimal status 上继续 (pitfall 4: 状态原样记录, 不提升; infeasible
    是真实答案)。cvxpy 原生 solver_path 会在所有 solver 都返回 non-optimal 时抛
    SolverError, 破坏诚实状态契约, 因此这里手动回退。

    Args:
        problem: 已构造的 cp.Problem。
        options: 记录的 options dict (含 solver_path / 容差键)。

    Returns:
        实际求解成功的 solver 名。

    Raises:
        cp.error.SolverError: 路径上所有 solver 都崩溃时。
    """
    path = options.get("solver_path") or [options.get("solver", "CLARABEL")]
    last_error: Exception | None = None
    for solver in path:
        try:
            problem.solve(**_solve_kwargs(options, solver))
            return problem.solver_stats.solver_name
        except cp.error.SolverError as error:
            last_error = error
    if last_error is not None:
        raise last_error
    raise cp.error.SolverError(f"All solvers failed: {path}")


def _solver_version(solver_name: str) -> str:
    """把 solver 包名解析到发行版版本 (solver_path 下实际运行的 solver).

    solver 包名 → 发行版名固定映射, 经 importlib.metadata.version 取版本; 包未
    安装/名字未知时回退 "unknown" (PFOL-04 pitfall 6: solver 版本进审计记录)。
    """
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
    if min_eig < -epsilon and (
        not provenance or "eigenvalues_before" not in provenance or "eigenvalues_after" not in provenance
    ):
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
    # 记录 dict 保持策略原文 (含 solver_path); _solve_problem 手动回退, 使
    # non-optimal 状态 (如 infeasible) 原样记录 (pitfall 4)。
    solver_name = _solve_problem(problem, options)
    return _finalize_result(problem, w, symbols, min_cash, options, solver_name)


def solve_max_sharpe(
    mu: np.ndarray,
    cov: np.ndarray,
    symbols: list[str],
    *,
    per_instrument_cap: float = PER_INSTRUMENT_CAP_DEFAULT,
    min_cash: float = MIN_CASH_DEFAULT,
    turnover_coef: float = TURNOVER_COEF_DEFAULT,
    w_prev: np.ndarray,
    risk_aversion: float = MAX_SHARPE_RISK_AVERSION,
    solver_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Solve the long-only max-Sharpe QP under the same constraint stack (PFOL-02).

    w = cp.Variable(n, nonneg=True); 同一约束栈 (预算等式 sum(w)==1-min_cash,
    单标的 cap); objective = mu @ w - (risk_aversion/2) * quad_form(w, cov)
    + turnover_coef * norm1(w - w_prev)。max_sharpe 显式非默认: 仅当
    render_baselines=True 时才可达 (pitfall 2), 且每次运行都记录 min-vol + HRP
    双基线。风险厌恶系数 = MAX_SHARPE_RISK_AVERSION (1.0, 策略常量)。

    Args:
        mu: 期望收益向量 (composite cross-section, 与 symbols 对齐)。
        cov: PSD 协方差 (必须已通过 ensure_psd_provenance gate)。
        symbols: 标的列表 (与 cov/mu 行对齐)。
        per_instrument_cap: 单标的权重上限。
        min_cash: 最低现金 (地板)。
        turnover_coef: 换手惩罚系数。
        w_prev: 上一期权重向量 (与 symbols 对齐)。
        risk_aversion: 风险厌恶系数 (策略常量 MAX_SHARPE_RISK_AVERSION = 1.0)。
        solver_options: 覆盖默认的 solve() 选项 (白名单外键会被 solve 拒绝)。

    Returns:
        dict: status / solver_name / solve_time / num_iters / options /
        cvxpy_version / solver_version / weights (dict[symbol, float])。
    """
    n = len(symbols)
    w = cp.Variable(n, nonneg=True)
    constraints = [cp.sum(w) == 1.0 - min_cash, w <= per_instrument_cap]
    objective = cp.Maximize(
        mu @ w - (risk_aversion / 2.0) * cp.quad_form(w, cov) - turnover_coef * cp.norm1(w - w_prev)
    )
    problem = cp.Problem(objective, constraints)
    options = dict(DEFAULT_SOLVER_OPTIONS)
    if solver_options:
        options.update(solver_options)
    solver_name = _solve_problem(problem, options)
    return _finalize_result(problem, w, symbols, min_cash, options, solver_name)


def _finalize_result(
    problem: cp.Problem,
    w: cp.Variable,
    symbols: list[str],
    min_cash: float,
    options: dict[str, Any],
    solver_name: str,
) -> dict[str, Any]:
    """从求解后的 problem 提取全量审计结果 (min-vol / max-sharpe 共用).

    Args:
        problem: 已求解的 cp.Problem。
        w: 权重变量。
        symbols: 标的列表。
        min_cash: 最低现金 (预算舍入修正)。
        options: 记录的 options dict (原样进 solver_options_json)。
        solver_name: 实际运行的 solver 名。

    Returns:
        dict: status / solver_name / solve_time / num_iters / options /
        cvxpy_version / solver_version / weights (dict[symbol, float])。
    """
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
        weights = dict(zip(symbols, rounded.tolist(), strict=True))
    else:
        weights = {}
    return {
        "status": problem.status,
        "solver_name": solver_name,
        "solve_time": problem.solver_stats.solve_time,
        "num_iters": problem.solver_stats.num_iters,
        "options": options,
        "cvxpy_version": cp.__version__,
        "solver_version": _solver_version(solver_name),
        "weights": weights,
    }


def _resolve_w_prev(
    request: Any,
    symbols: list[str],
    repository: PortfolioRepository,
    artifact_service_root: Path,
) -> tuple[np.ndarray, str, str]:
    """Resolve the turnover reference anchor (PFOL-03).

    Returns ``(w_prev, turnover_reference, turnover_reference_detail)``:

    - ``turnover_reference == "equal_weight"`` (默认): 首次运行用等权 1/n 锚,
      detail 为 ``"equal_weight"``。
    - ``turnover_reference == "run_id"``: 引用先前 run 的校验和绑定权重工件,
      按当前 symbols 对齐 (缺失 symbol → 0.0, 多余 → 丢弃), detail 为
      ``"run_id:<w_prev_run_id>"``。先前 run 不存在/无权重工件时 fail closed
      (ValueError, 由编排器记录为 failed run)。

    Args:
        request: OptimizationRequest (或等价 dict)。
        symbols: 当前 run 的标的列表。
        repository: PortfolioRepository (先前 run 的 append-only 访问面)。
        artifact_service_root: 工件根目录 (校验先前 run 的权重工件 checksum)。

    Returns:
        (w_prev, turnover_reference, turnover_reference_detail)。

    Raises:
        ValueError: run_id 引用缺失/无权重工件时 (fail closed)。
    """
    n = len(symbols)
    reference = getattr(request, "turnover_reference", TURNOVER_REFERENCE_EQUAL_WEIGHT)
    if reference == TURNOVER_REFERENCE_EQUAL_WEIGHT:
        return np.full(n, 1.0 / n), TURNOVER_REFERENCE_EQUAL_WEIGHT, TURNOVER_REFERENCE_EQUAL_WEIGHT
    run_id = getattr(request, "w_prev_run_id", None)
    if not run_id:
        raise ValueError("w_prev_run_id is required when turnover_reference is run_id")
    prior = repository.get_optimization_run(run_id)
    if prior is None:
        raise ValueError(f"prior run not found: {run_id}")
    relative_path = prior.get("weights_artifact_relative_path")
    output_sha256 = prior.get("output_sha256")
    if not relative_path or not output_sha256:
        raise ValueError(f"prior run has no weights artifact: {run_id}")
    # 校验和绑定读取: 工件内容必须与 run 行的 output_sha256 一致 (checksum gate)。
    artifact_service = PortfolioArtifactService(artifact_service_root)
    payload = artifact_service.read_artifact(relative_path, checksum_sha256=output_sha256)
    prior_weights = json.loads(payload.decode("utf-8"))
    aligned = np.array([float(prior_weights.get(symbol, 0.0)) for symbol in symbols])
    return aligned, TURNOVER_REFERENCE_RUN_ID, f"run_id:{run_id}"


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

    12 标的 x 20 观测: 全秩、协方差数值 PSD (无需修复), 使 12x0.10=1.20 ≥ 0.95
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
    mu: np.ndarray | None = None,
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
        mu: (n_assets,) 期望收益向量 (max_sharpe 必填, 与 symbols 对齐; 快照绑定
            在 11-05 落位, 此前由调用方提供)。
        snapshot: 预解析快照 dict ({"model_id", "input_snapshot_sha256",
            "composite_snapshot_id", 可选 "symbols"/"mu"}) —— 11-01 tracer 的
            fixture 身份接缝; None 且 expected_return_method ==
            composite-zscore-v1 时由 catalog 接缝解析 (生产路径, 11-05)。
        catalog / data_dir: 生产 catalog 接缝 (11-05): catalog.get_composite_model
            → checksum 验证 artifact → as_of 横截面; 提供时 snapshot 参数被忽略
            (真实接缝优先, 绝不 live module hand-off)。

    Returns:
        与 get_optimization_run 同构的 run 记录 (JSON 列已展开)。
    """
    from app.portfolio.schemas import OptimizationRequest

    req = request if isinstance(request, OptimizationRequest) else OptimizationRequest(**request)
    run_id = uuid.uuid4().hex
    created_at = "2026-08-01T00:00:00Z"

    # ---- fail-closed 入口守卫 (11-05/11-06): 编排器包裹 ENTIRE run, 任何
    # SnapshotBindingError / ValueError / 求解器失败都记录为 failed run 并携带
    # failure_reason (PFOL-04) —— 绝不静默中断。求解器崩溃 (cp.error.SolverError)
    # 也并入: _solve_problem 在路径上所有 solver 都抛 SolverError 时抛出。
    try:
        return _run_optimization_impl(
            req,
            run_id=run_id,
            created_at=created_at,
            repository=repository,
            artifact_service_root=artifact_service_root,
            returns=returns,
            symbols=symbols,
            mu=mu,
            snapshot=snapshot,
            catalog=catalog,
            data_dir=data_dir,
        )
    except (SnapshotBindingError, ValueError, RuntimeError, cp.error.SolverError) as error:
        return _record_failed_run(
            repository,
            run_id=run_id,
            req=req,
            created_at=created_at,
            failure_reason=str(error),
        )


def _record_failed_run(
    repository: PortfolioRepository,
    *,
    run_id: str,
    req: Any,
    created_at: str,
    failure_reason: str,
) -> dict[str, Any]:
    """Persist a failed run row with the failure reason (PFOL-04).

    模型缺失 (快照绑定 "model not found") 时, run 行的 model_id FK 无法引用一个
    不存在的模型定义 —— 此时降级为 expected_return_method="none" 且 model_id=None,
    由 failure_reason 保留完整事实 (该 run 从未消费任何复合快照)。
    """
    constraint_stack = {
        "cap": req.per_instrument_cap,
        "min_cash": req.min_cash,
        "turnover_coef": req.turnover_coef,
        "turnover_reference": TURNOVER_REFERENCE_EQUAL_WEIGHT,
        "turnover_reference_detail": TURNOVER_REFERENCE_EQUAL_WEIGHT,
        "industry_cap": getattr(req, "industry_cap", None),
        "policy_version": "phase-11-policy-v1",
    }
    risk_model_json = {"risk_model": "sample_covariance_v1", "psd_repair": None}
    fields: dict[str, Any] = {
        "id": run_id,
        "objective": req.objective,
        "as_of": req.as_of.isoformat(),
        "universe": req.universe,
        "model_id": req.model_id,
        "composite_snapshot_id": None,
        "input_snapshot_sha256": "f" * 64,
        "expected_return_method": req.expected_return_method,
        "risk_model": "sample_covariance_v1",
        "risk_model_json": risk_model_json,
        "constraint_stack_json": constraint_stack,
        "solver_name": "n/a",
        "solver_version": "n/a",
        "solver_options_json": {},
        "problem_status": "failed",
        "failure_reason": failure_reason,
        "output_weights_json": None,
        "output_sha256": None,
        "weights_artifact_relative_path": None,
        "baseline_weights_json": None,
        "created_at": created_at,
    }
    try:
        return repository.record_optimization_run(**fields)
    except sqlite3.IntegrityError:
        # 模型不存在 (FK): 降级记录, failure_reason 保留完整事实。
        fields["model_id"] = None
        fields["expected_return_method"] = "none"
        return repository.record_optimization_run(**fields)


def _run_optimization_impl(
    req: Any,
    *,
    run_id: str,
    created_at: str,
    repository: PortfolioRepository,
    artifact_service_root: Path,
    returns: np.ndarray | None,
    symbols: list[str] | None,
    mu: np.ndarray | None,
    snapshot: dict[str, Any] | None,
    catalog: Any,
    data_dir: Path | None,
) -> dict[str, Any]:
    """run_optimization 的主体 (由 fail-closed 包装器调用)。"""
    if symbols is None:
        symbols = [f"SYM{i:03d}" for i in range(12)]
    if returns is None:
        returns = _fixture_returns()

    # 快照解析: 生产 catalog 接缝优先 (catalog + data_dir), 否则退回预解析
    # snapshot dict (tracer fixture 接缝)。两者都缺失且需要 composite 时
    # 保持 11-01 的 fixture 身份路径 (现有测试兼容), 由 research 仓库登记。
    if catalog is not None and data_dir is not None and req.expected_return_method == "composite-zscore-v1":
        loaded = load_composite_snapshot(
            catalog,
            model_id=req.model_id,  # type: ignore[arg-type]
            as_of=req.as_of,
            data_dir=data_dir,
        )
        input_snapshot_sha256 = loaded["input_snapshot_sha256"]
        composite_snapshot_id = loaded["composite_snapshot_id"]
        # 快照横截面定义 run 的标的宇宙 (与 expected-return 向量 mu 对齐);
        # 风险面板 (returns) 必须由调用方按同一宇宙提供, 绝不与快照错位。
        symbols = list(loaded["symbols"])
        snapshot = loaded
    elif snapshot is not None:
        input_snapshot_sha256 = snapshot.get("input_snapshot_sha256", "f" * 64)
        composite_snapshot_id = snapshot.get("composite_snapshot_id")
        snapshot_symbols = snapshot.get("symbols")
        if snapshot_symbols is not None:
            symbols = list(snapshot_symbols)
    else:
        input_snapshot_sha256 = "f" * 64
        composite_snapshot_id = None

    # 快照的 mu 横截面 (max_sharpe 期望收益): catalog 接缝解析时把快照 dict 的
    # symbols/mu 对齐到 run 的 symbols。快照横截面标的与收益率面板标的不一致
    # (复合覆盖与风险面板窗口不同) 时 fail closed —— 绝不静默错位。
    snapshot_mu = snapshot.get("mu") if snapshot is not None else None
    if snapshot_mu is not None:
        if len(snapshot_mu) != len(symbols):
            raise ValueError("snapshot mu length must match symbols")
        mu = np.asarray(snapshot_mu, dtype=float)

    risk_block = _build_risk_model(returns, window=(req.as_of.isoformat(), req.as_of.isoformat()))
    cov = risk_block["covariance"]
    risk_model_json = risk_block["risk_model_json"]
    ensure_psd_provenance(cov, risk_model_json["psd_repair"], epsilon=PSD_EPSILON_DEFAULT)

    # 先决条件: model_id 必须存在于 factor_model_models (FK), 且 composite-zscore-v1
    # 必须绑定一个快照身份。调用方若已提供 composite_snapshot_id (来自快照接缝) 则
    # 直接记录; 否则在 research 仓库侧登记定义 + 快照 (仅当尚未存在), 使 run 行
    # FK 成立。生产 catalog 接缝由 11-05 替换。
    if req.expected_return_method == "composite-zscore-v1" and composite_snapshot_id is None:
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
        composite = research.insert_model_composite(
            model_id=req.model_id,  # type: ignore[arg-type]
            output_sha256=input_snapshot_sha256,
            artifact_relative_path="research_artifacts/00000000000000000000000000000000/signals.json",
            input_snapshot_sha256=input_snapshot_sha256,
        )
        composite_snapshot_id = composite["id"]

    # objective="hrp" 一等目标: 无求解器参与 (solver_name/solver_version="n/a",
    # solver_options_json={}), 但 run 记录仍不可变、可审计 (PFOL-02/04)。
    # PSD gate 已在上面跑过 (ensure_psd_provenance), hrp_portfolio 内部再挡一道
    # 负对角线 (pitfall 9)。HRP 输出本身就是渲染后的基线。
    if req.objective == "hrp":
        hrp_result = hrp_portfolio(cov, min_cash=req.min_cash, symbols=symbols)
        weights = hrp_result["weights"]
        baseline_weights = weights
        status = hrp_result["status"]
        solver_name = hrp_result["solver_name"]
        solver_version = "n/a"
        options: dict[str, Any] = {}

        # HRP 无换手基准 (无求解器, 无 w_prev 参与): 引用语义记录为 equal_weight。
        turnover_reference = TURNOVER_REFERENCE_EQUAL_WEIGHT
        turnover_reference_detail = TURNOVER_REFERENCE_EQUAL_WEIGHT

        artifact_service = PortfolioArtifactService(artifact_service_root)
        descriptors = artifact_service.write_bundle(
            run_id=run_id,
            weights=weights,
            baseline_weights=baseline_weights,
            covariance=cov,
        )
        weights_descriptor = next(d for d in descriptors if d.relative_path.endswith("weights.json"))

        return repository.record_optimization_run(
            id=run_id,
            objective="hrp",
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
                "turnover_reference_detail": turnover_reference_detail,
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

    w_prev, turnover_reference, turnover_reference_detail = _resolve_w_prev(
        req, symbols, repository, artifact_service_root
    )

    # max_sharpe 显式非默认: 仅当 render_baselines=True 才可到达 (pitfall 2 ——
    # PyPortfolioOpt μ-不确定警告)。否则 ValueError, 绝不静默跳过。
    if req.objective == "max_sharpe" and not req.render_baselines:
        raise ValueError("max_sharpe requires render_baselines=True (baselines are mandatory)")

    # mu: composite cross-section 期望收益 (快照绑定在 11-05 落位; 此前由调用方
    # 提供, 与 symbols 对齐)。
    if req.objective == "max_sharpe":
        if mu is None:
            raise ValueError("max_sharpe requires an expected-returns vector (mu)")
        if len(mu) != len(symbols):
            raise ValueError("expected returns length must match symbols")

    try:
        if req.objective == "max_sharpe":
            result = solve_max_sharpe(
                np.asarray(mu, dtype=float),
                cov,
                symbols,
                per_instrument_cap=req.per_instrument_cap,
                min_cash=req.min_cash,
                turnover_coef=req.turnover_coef,
                w_prev=w_prev,
            )
        else:
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
                "turnover_reference_detail": turnover_reference_detail,
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

    # 成功路径 (optimal / optimal_inaccurate): 渲染基线。max_sharpe 运行时 ALWAYS
    # 记录 min-vol + HRP 双基线 (pitfall 2); min_volatility 运行时记录 HRP 基线
    # (与 11-01/11-03 契约一致)。min-vol 基线在同一协方差/约束栈下求解 (换手惩罚
    # 同 w_prev), 使审计面完全一致。
    baseline_full = hrp_weights(cov)
    baseline_scaled = render_baseline(baseline_full, min_cash=req.min_cash)
    hrp_weights_rendered = dict(
        zip(symbols, np.asarray(baseline_scaled, dtype=float).round(8), strict=True)
    )
    if req.objective == "max_sharpe":
        min_vol_result = solve_min_vol(
            cov,
            symbols,
            per_instrument_cap=req.per_instrument_cap,
            min_cash=req.min_cash,
            turnover_coef=req.turnover_coef,
            w_prev=w_prev,
        )
        baseline_weights = {
            "min_volatility": min_vol_result["weights"],
            "hrp": hrp_weights_rendered,
        }
    else:
        baseline_weights = hrp_weights_rendered

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
            "turnover_reference_detail": turnover_reference_detail,
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
