"""Phase 11/12 风险模型套件 + PSD 检查/修复 (PFOL-01 / RSK-02)。

职责: 从治理面板的收益率矩阵构建四种风险模型协方差 —— 样本协方差 (Phase 11)、
半协方差 (下行共同波动, below-mean benchmark, PyPortfolioOpt 契约为设计规格)、
指数加权 EWMA (RiskMetrics λ=0.94)、Ledoit-Wolf 收缩 (scikit-learn 1.8.0
惰性导入 —— 仅在模型边界函数体内 import, 绝无 module-top import; Phase 10
import-audit 契约); 检查对称矩阵是否半正定 (PSD); 必要时用 eigen_clip 修复并
返回完整溯源 (method/epsilon/eigenvalues before/after)。PSD 修复 NEVER silent ——
provenance 是 risk_model_json 的强制字段, optimizer 在缺少溯源时 fail-closed
(pitfall 1/3)。make_risk_model_family 是所有模型共用的单一 PSD-provenance
分派器, Phase 13 walk-forward 每折协方差复用它 (RSK-02 接缝)。

不知道: 求解逻辑 (optimizer.py)、约束栈 (constraints.py)、行业映射、
市场时间序列 (留在 lake)。
"""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np

from app.portfolio.artifacts import PortfolioArtifactService
from app.portfolio.constraints import PSD_EPSILON_DEFAULT


def sample_covariance(returns: np.ndarray, *, dropna: bool = True) -> np.ndarray:
    """Cross-sectional sample covariance on the common (all-finite) window.

    Args:
        returns: (n_obs, n_assets) 的收益率矩阵。
        dropna: 只保留所有资产都有限的观测行 (公共窗口)。

    Returns:
        (n_assets, n_assets) 样本协方差矩阵。
    """
    if dropna:
        returns = returns[np.all(np.isfinite(returns), axis=1)]
    return np.cov(returns, rowvar=False)


def semi_covariance(returns: np.ndarray, *, benchmark: str = "mean") -> np.ndarray:
    """Semi-covariance: downside co-movement below a per-observation benchmark.

    benchmark "mean" = row-wise cross-sectional mean per observation, "zero" =
    0.0. The below-benchmark co-movement is captured by truncating each row at
    the benchmark (min with 0 after subtraction) and forming the Gram matrix of
    the truncated panel, normalized by the observation count — the PyPortfolioOpt
    ``risk_models.semicovariance`` contract as design spec (never a runtime
    dependency). A degenerate subset (fewer observations than assets) still
    returns a finite covariance; the PSD gate downstream records any
    near-degeneracy repair with provenance.

    Args:
        returns: (n_obs, n_assets) 收益率矩阵。
        benchmark: "mean" (行均值) 或 "zero" (0.0)。

    Returns:
        (n_assets, n_assets) 半协方差矩阵 (Gram 矩阵, 数值上 PSD)。
    """
    finite = returns[np.all(np.isfinite(returns), axis=1)]
    if benchmark == "mean":
        target = finite.mean(axis=1, keepdims=True)
    elif benchmark == "zero":
        target = np.zeros_like(finite)
    else:
        raise ValueError(f"unknown benchmark: {benchmark}")
    drops = np.minimum(finite - target, 0.0)
    return drops.T @ drops / drops.shape[0]


def ewma_covariance(returns: np.ndarray, *, lam: float = 0.94, adjust: bool = True) -> np.ndarray:
    """Exponentially weighted moving-average covariance (RiskMetrics λ=0.94).

    Recursion ``Σ_t = lam * Σ_{t-1} + (1 - lam) * outer(r_t, r_t)`` starting from
    ``Σ_1 = outer(r_1, r_1)`` (the standard EWMA; pandas ``adjust=True``
    semantics — the first observation carries the full weight ``lam^{t-1}``, so
    the weights sum to 1 and no extra normalization is needed). ``adjust=False``
    gives the unadjusted recursion whose first observation also receives the
    ``(1 - lam)`` weight (weight sum ``1 - lam^t``). λ=0.94 is the RiskMetrics
    default. ``lam=1.0`` degenerates to the sample covariance on the common
    window (documented test contract — recovers ``np.cov`` on demeaned data).

    Args:
        returns: (n_obs, n_assets) 收益率矩阵。
        lam: 衰减因子 (RiskMetrics 标准 0.94)。
        adjust: True (默认) 时首观测权重为 1.0 (权重和自动为 1); False 时首观测
            也乘 (1 - lam) (未归一化递归, 权重和 1 - lam^t)。

    Returns:
        (n_assets, n_assets) EWMA 协方差矩阵。
    """
    finite = returns[np.all(np.isfinite(returns), axis=1)]
    n_obs, n_assets = finite.shape
    if n_obs == 0:
        return np.zeros((n_assets, n_assets))
    if lam == 1.0:
        # 文档化测试契约: λ=1.0 时 EWMA 退化为样本协方差 (demeaned 数据上等于 np.cov)。
        return np.cov(finite, rowvar=False)
    first_weight = 1.0 if adjust else (1.0 - lam)
    covariance = first_weight * np.outer(finite[0], finite[0])
    for t in range(2, n_obs + 1):
        covariance = lam * covariance + (1 - lam) * np.outer(finite[t - 1], finite[t - 1])
    return covariance


def ledoit_wolf_covariance(
    returns: np.ndarray, *, block_size: int | None = None
) -> tuple[np.ndarray, dict]:
    """Ledoit-Wolf shrinkage covariance via scikit-learn (lazy-import boundary).

    ``from sklearn.covariance import LedoitWolf`` lives INSIDE the function body
    only — Phase 10 import-audit contract: importing ``app.portfolio.risk`` must
    never load sklearn (subprocess gate in test_risk). Fits on the common finite
    window and returns the shrunk covariance plus its provenance params.

    Args:
        returns: (n_obs, n_assets) 收益率矩阵。
        block_size: sklearn LedoitWolf block_size (None 时用 sklearn 默认)。

    Returns:
        ((n_assets, n_assets) 协方差, {"shrinkage": float, "sklearn_version": str})。
    """
    # Phase 10 惰性导入契约: sklearn 只在模型边界函数体内导入 (subprocess gate
    # 断言 import app.portfolio.risk 后 "sklearn" not in sys.modules)。
    from sklearn import __version__ as sklearn_version
    from sklearn.covariance import LedoitWolf

    finite = returns[np.all(np.isfinite(returns), axis=1)]
    kwargs: dict[str, int] = {}
    if block_size is not None:
        kwargs["block_size"] = block_size
    model = LedoitWolf(**kwargs).fit(finite)
    return (
        model.covariance_,
        {"shrinkage": float(model.shrinkage_), "sklearn_version": str(sklearn_version)},
    )


def check_psd(cov: np.ndarray, *, tol: float = 1e-8) -> tuple[float, np.ndarray]:
    """Symmetrize and return (min_eigenvalue, eigenvalues).

    Args:
        cov: 协方差矩阵。
        tol: 判定 PSD 的容差 (数值零)。

    Returns:
        (float(eigvals.min()), eigvals) —— 最小特征值与完整特征值谱。
    """
    sym = (cov + cov.T) / 2.0
    eigvals = np.linalg.eigvalsh(sym)
    return float(eigvals.min()), eigvals


def repair_psd(
    cov: np.ndarray,
    *,
    method: str = "eigen_clip",
    epsilon: float = PSD_EPSILON_DEFAULT,
) -> tuple[np.ndarray, dict]:
    """Eigen-clip PSD repair with mandatory provenance.

    Args:
        cov: 需要修复的协方差矩阵。
        method: 修复方法, 当前支持 ``"eigen_clip"`` (默认) 与 ``"none"``
            (记录为无需修复, 原样返回对称化矩阵)。
        epsilon: 特征值钳位下界。

    Returns:
        (repaired, provenance), 其中 provenance 携带 method / epsilon /
        min_eigenvalue_before / eigenvalues_before / eigenvalues_after;
        method == "none" 时 eigenvalues_after 为 None。
    """
    sym = (cov + cov.T) / 2.0
    eigvals, eigvecs = np.linalg.eigh(sym)

    if method == "none":
        repaired = sym
        eigenvalues_after = None
    elif method == "eigen_clip":
        clipped = np.maximum(eigvals, epsilon)
        repaired = (eigvecs * clipped) @ eigvecs.T
        repaired = (repaired + repaired.T) / 2.0
        eigenvalues_after = np.linalg.eigvalsh(repaired).tolist()
    else:
        raise ValueError(f"unknown PSD repair method: {method}")

    provenance = {
        "method": method,
        "epsilon": epsilon,
        "min_eigenvalue_before": float(eigvals.min()),
        "eigenvalues_before": eigvals.tolist(),
        "eigenvalues_after": eigenvalues_after,
    }
    return repaired, provenance


def covariance_sha256(cov: np.ndarray) -> str:
    """Canonical 8-decimal sha256 identity for a covariance matrix (PFOL-01).

    The digest is computed over the canonical JSON of the matrix as a list of
    lists rounded to 8 decimals (sort_keys + compact separators + ensure_ascii
    False) — byte-identical to ``PortfolioArtifactService.write_bundle``'s
    ``covariance.json`` serialization (11-06). Phase 12 can therefore verify the
    artifact bytes against the digest recorded in ``risk_model_json``.

    Args:
        cov: (n, n) 协方差矩阵 (修复后进入工件的矩阵)。

    Returns:
        64 位小写 hex 摘要。
    """
    matrix = np.asarray(cov, dtype=float).round(8).tolist()
    content = json.dumps(
        matrix, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return sha256(content).hexdigest()


def make_risk_model_family(
    returns: np.ndarray,
    *,
    risk_model_name: str,
    window: tuple[str, str] | None = None,
    epsilon: float = PSD_EPSILON_DEFAULT,
) -> dict:
    """Single PSD-provenance dispatcher across the four RSK-02 risk models.

    Dispatches ``sample_covariance_v1 | semi_covariance_v1 | ewma_covariance_v1
    | ledoit_wolf_v1`` (unknown → ValueError), then runs the SAME
    check_psd → repair_psd (eigen_clip, never silent) → provenance path for
    every model and returns ``{"covariance", "risk_model_json"}`` with
    ``risk_model`` = the selected name, model params (benchmark/lam/shrinkage)
    recorded, ``window``, ``dropna: True``, ``psd_repair`` provenance
    (method/epsilon/eigenvalues before/after — method "none" when no repair),
    and ``covariance_sha256``. This is the Phase 13 per-fold covariance seam.

    Args:
        returns: (n_obs, n_assets) 收益率矩阵。
        risk_model_name: 四种模型名之一。
        window: (start, end) 窗口字符串对, 记录进 risk_model_json (测试可省略)。
        epsilon: PSD 判定/修复容差。

    Returns:
        {"covariance": (n, n) 修复后矩阵, "risk_model_json": {...}}。

    Raises:
        ValueError: 未知模型名 (fail closed, 绝不静默回退样本协方差)。
    """
    finite = returns[np.all(np.isfinite(returns), axis=1)]
    if risk_model_name == "sample_covariance_v1":
        cov = sample_covariance(returns, dropna=True)
        model_params: dict = {"dropna": True}
    elif risk_model_name == "semi_covariance_v1":
        cov = semi_covariance(finite, benchmark="mean")
        model_params = {"benchmark": "mean"}
    elif risk_model_name == "ewma_covariance_v1":
        cov = ewma_covariance(finite, lam=0.94, adjust=True)
        model_params = {"lam": 0.94, "adjust": True}
    elif risk_model_name == "ledoit_wolf_v1":
        lw_cov, lw_params = ledoit_wolf_covariance(finite)
        cov = lw_cov
        model_params = {
            "shrinkage": lw_params["shrinkage"],
            "sklearn_version": lw_params["sklearn_version"],
        }
    else:
        raise ValueError(f"unknown risk model name: {risk_model_name}")

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
        "risk_model": risk_model_name,
        "window": list(window) if window is not None else [],
        "dropna": True,
        "model_params": model_params,
        "psd_repair": provenance,
        "covariance_sha256": covariance_sha256(cov),
    }
    return {"covariance": cov, "risk_model_json": risk_model_json}


def load_covariance_artifact(run: dict[str, Any], artifact_service_root: Path) -> np.ndarray:
    """Checksum-verified read of a run's recorded covariance artifact (RSK-01).

    The ONLY covariance source for the attribution identity path: reads
    ``risk_model_detail.covariance_artifact_relative_path`` via
    ``PortfolioArtifactService.read_artifact`` against the run's recorded
    ``covariance_sha256`` digest. A missing artifact or a checksum mismatch
    raises ``ArtifactReadError`` (fail closed — the identity path NEVER silently
    recomputes a covariance).

    Args:
        run: portfolio_optimization_runs 记录 (risk_model_detail 已展开)。
        artifact_service_root: PortfolioArtifactService 的工件根目录。

    Returns:
        (n, n) 协方差矩阵 (工件字节经 8 位小数规范化序列化)。

    Raises:
        ArtifactReadError: 工件缺失 / 路径逃逸 / checksum 不匹配。
        ValueError: 工件解码后不是方阵。
    """
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
