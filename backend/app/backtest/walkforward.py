"""Walk-forward 验证骨架 (WFWD-01) — 基于实测日历的滚动折叠 + 每折 PIT 计算。

知道: 滚动(非扩张)折叠几何 — 给定实测交易日列表, train/gap/test 段按交易日计数,
      边界吸附到实测日期 (Feb 2026 CNY 14 日缺口不会缩短 "20 日" 测试段), 保留段
      OOS 预约先于任何搜索重用, 每折独立 SignalChainConfig(end=test_end+horizon
      标签缓冲) 与 membership_fingerprint/effective_days 清单, OOS 只评估一次。
不知道: 因子计算 (FactorSignalChain 黑盒)、策略回测细节 (StrategyBacktestService)、
      仓储/迁移、产物落盘。折叠评分经 fold_scorer 接缝注入 (默认固定参数策略回测)。

几何 (13-RESEARCH.md `## Fold Geometry Calibration`):
  选择区 = dates[:-oos_size]; OOS = dates[-oos_size:]。
  fold i: train [i*Te, i*Te+Tr), gap [i*Te+Tr, i*Te+Tr+G), test [i*Te+Tr+G, i*Te+Tr+G+Te)。
  step=Te ⇒ 测试段平铺且两两不相交; 最末 fold.test_end < oos_start。
  折叠数 < 2 ⇒ fail-closed (ValueError), 绝不产生 1 折"验证"。
"""
#
# 本模块同时承载两套同名但不同域的 walk-forward 实现 (merge of HEAD research 栈与 upstream v0.2):
# 1. WFWD-01 研究治理栈: 基于实测日历的滚动折叠 + 每折 PIT 计算 (build_plan / run_walk_forward)。
# 2. upstream v0.2 策略步进优化: 滚动窗口的样本内优化 + 样本外验证 (WalkForwardConfig / WalkForwardService)。

from __future__ import annotations

import datetime
import hashlib
import itertools
import json
import logging
import time
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, timedelta
from typing import Any

from app.backtest.engine import BacktestEngine
from app.backtest.strategy import StrategyBacktestConfig
from app.research.repository import ResearchRepository
from app.research.signal_chain import FactorSignalChain, SignalChainConfig

logger = logging.getLogger(__name__)

# 与 strategy._panel_window 的日历日 warmup 一致 (strategy.py:123-124)。
_WARMUP_DAYS = 120
# 搜索折查询路径的最大行数 (单个 plan 的折叠记录数远小于此)。
_LIST_CAP = 100_000


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    """一个滚动折 (或保留 OOS 段) 的几何矩形 + 每折链配置。"""

    fold_index: int
    is_oos: bool
    train_start: date
    train_end: date
    gap_start: date
    gap_end: date
    test_start: date
    test_end: date
    membership_fingerprint: str
    chain_config: SignalChainConfig


@dataclass(frozen=True, slots=True)
class WalkForwardPlan:
    """一次 walk-forward 验证的完整几何: 搜索折 + 保留 OOS + 实测日历。"""

    plan_id: str
    universe: str
    asset_type: str
    start: date
    end: date
    train_size: int
    gap_size: int
    test_size: int
    oos_size: int
    horizon: int
    folds: tuple[WalkForwardFold, ...]
    oos_fold: WalkForwardFold
    trading_dates: tuple[date, ...]
    created_at: str


def trading_calendar(
    engine: BacktestEngine,
    *,
    symbols: list[str] | None,
    start: date,
    end: date,
    asset_type: str = "stock",
) -> list[date]:
    """``[start, end]`` 区间内去重排序的实测交易日。

    实测于执行期 (measured at execution) 契约: 调用方在每次运行时重测日历 —
    enriched lake 每月新增约 20 个交易日, 陈旧日历会产生错误的折叠数并把 OOS
    按设计向前滚动; 绝不硬编码历史末端日期。通过 governed seam
    ``BacktestEngine.load_panel(columns=["date"])`` 的只读探针 (复用
    PanelCache) — 绝不合成 weekday 日历 (Feb 2026 CNY 缺口)。
    """
    panel = engine.load_panel(symbols, start, end, columns=["date"], asset_type=asset_type)
    if panel.is_empty():
        return []
    return sorted({_to_date(day) for day in panel["date"].to_list()})


def build_plan(
    *,
    plan_id: str,
    universe: str,
    asset_type: str = "stock",
    dates: Sequence[date],
    train_size: int,
    gap_size: int,
    test_size: int,
    oos_size: int,
    horizon: int,
) -> WalkForwardPlan:
    """从实测日期列表推导滚动折 + 保留 OOS 的纯几何 (fail-closed)。

    折叠边界只按交易日索引切片, 吸附到实测日历; 任何长度不足/重叠/OOS 冲突都抛
    ValueError, 绝不降级为 1 折"验证"。
    """
    if not dates:
        raise ValueError("insufficient history: empty trading calendar")
    for name, value in (
        ("train_size", train_size),
        ("gap_size", gap_size),
        ("test_size", test_size),
        ("oos_size", oos_size),
        ("horizon", horizon),
    ):
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    trading_dates = tuple(sorted(set(dates)))
    total = len(trading_dates)
    selection_len = total - oos_size
    if selection_len < 1:
        raise ValueError("insufficient history for walk-forward validation")

    # Fail-closed below 2 folds (walk-forward degenerates at H≈180): a 2-fold
    # rectangle needs selection_len >= train_size + gap_size + 2 * test_size.
    # WR-08: 真实最小值为 oos + train + gap + 2*test + 1 — 第 2 折 test 段结束后还须
    # 留出至少 1 个交易日作为 OOS 缓冲 (gap_start > train_end), 否则 OOS 折的
    # gap 缓冲为空, _assert_geometry 报误导性错误。
    minimum = oos_size + train_size + gap_size + 2 * test_size + 1
    if total < minimum:
        raise ValueError(
            "insufficient history for walk-forward validation: "
            f"{total} measured trading days < minimum {minimum} "
            f"(need >= 2 folds with train={train_size}/gap={gap_size}/"
            f"test={test_size}/oos={oos_size})"
        )

    step = test_size
    fold_count = 0
    while (fold_count * step + train_size + gap_size + test_size - 1) <= selection_len - 1:
        fold_count += 1
    if fold_count < 2:
        raise ValueError(
            "insufficient history for walk-forward validation: "
            f"{total} trading days with train={train_size}/gap={gap_size}/"
            f"test={test_size}/oos={oos_size} yields only {fold_count} fold(s); need >= 2"
        )

    folds = tuple(
        _build_fold(
            i, trading_dates, step, train_size, gap_size, test_size, universe, asset_type, horizon
        )
        for i in range(fold_count)
    )
    oos_fold = _build_oos_fold(
        fold_count,
        trading_dates,
        selection_len,
        step,
        train_size,
        gap_size,
        test_size,
        universe,
        asset_type,
        horizon,
    )
    _assert_geometry(folds, oos_fold, trading_dates, oos_size)
    return WalkForwardPlan(
        plan_id=plan_id,
        universe=universe,
        asset_type=asset_type,
        start=trading_dates[0],
        end=trading_dates[-1],
        train_size=train_size,
        gap_size=gap_size,
        test_size=test_size,
        oos_size=oos_size,
        horizon=horizon,
        folds=folds,
        oos_fold=oos_fold,
        trading_dates=trading_dates,
        created_at=datetime.datetime.now(UTC).isoformat(),
    )


def run_walk_forward(
    plan: WalkForwardPlan,
    *,
    strategy_id: str,
    params: dict[str, Any],
    service: Any,
    chain: FactorSignalChain,
    resolver: Any,
    repo: ResearchRepository,
    fold_scorer: Any = None,
    evaluate_oos: bool = False,
) -> dict[str, Any]:
    """端到端走一遍搜索折 (WR-01: 默认不碰保留 OOS)。

    1. 先把 plan 钉入 wf_plans (oos_pinned_at 先于任何搜索重用; 同 plan_id 重跑走
       查询路径返回已存在行 — append-only 幂等)。
    2. 每折: resolve_universe_daily 解析自己的 PIT 成员窗 → 以每折 SignalChainConfig
       经共享 FactorSignalChain.compute 计算 → 从 frame.resolved_universe 记录
       membership_fingerprint → 跑 train/test 窗口回测 → append 一条 wf_folds
       清单 (含 effective_days)。
    3. 保留 OOS 是唯一无偏估计 — 只有 ``evaluate_oos=True`` 时才评估 (WFWD-01/
       WR-01: 搜索/探索调用默认不写 OOS 槽位; 唯一 OOS 写发生在 best_params
       验证 ``evaluate_best_params``)。OOS 折只评估一次: 第二次同
       (plan, strategy, params) 评估抛 ValueError。

    ``fold_scorer(fold, *, frame, membership) -> dict`` 可注入折评分 (如 Phase 14
    的 per-fold 组合优化变体); 默认 = 固定参数策略回测变体。
    """
    repo.create_wf_plan(plan)
    params_sha256 = _params_sha256(params)
    folds = (*plan.folds, plan.oos_fold) if evaluate_oos else plan.folds
    manifests = _run_folds(
        plan=plan,
        folds=folds,
        strategy_id=strategy_id,
        params=params,
        params_sha256=params_sha256,
        service=service,
        chain=chain,
        resolver=resolver,
        repo=repo,
        fold_scorer=fold_scorer,
    )
    return {
        "plan_id": plan.plan_id,
        "strategy_id": strategy_id,
        "params": params,
        "params_sha256": params_sha256,
        "fold_manifests": manifests,
        "evaluate_oos": evaluate_oos,
    }


def evaluate_best_params(
    plan: WalkForwardPlan,
    *,
    strategy_id: str,
    best_params: dict[str, Any],
    service: Any,
    chain: FactorSignalChain,
    resolver: Any,
    repo: ResearchRepository,
    objective: str = "sharpe",
    search_run_id: str | None = None,
    fold_evidence: dict[str, Any] | None = None,
    validation_threshold: float | None = None,
    fold_scorer: Any = None,
) -> dict[str, Any]:
    """best_params 在保留 OOS 上恰好一次评估 + 记录验证裁决 (WFWD-02)。

    OOS 折是唯一无偏估计: ``UNIQUE (plan_id, fold_index, is_oos=1, strategy_id,
    params_sha256)`` 使第二次评估抛 ``ValueError("OOS segment already evaluated")``。
    ``wf_validated_strategies`` 的 ``oos_evidence_fold_id`` UNIQUE 把裁决绑到那
    次 OOS 证据上 — 搜索再多次也不会污染最终估计。

    ``validation_threshold`` 提供机械门: 给定后 passed_gate 由 OOS 表现对照阈值
    得出 (min 方向为 <=, 其余为 >=); 缺省 None 时视为研究者显式接受 (passed_gate=1)。

    WR-02: OOS 折行只在目标指标确认存在后才持久化 — 一次 OOS 回测失败 (策略在
    OOS 窗口无信号) 不会永久烧掉恰好一次槽位。
    """
    from app.backtest.optimizer import default_direction

    repo.create_wf_plan(plan)  # 幂等钉住 OOS 预约 (先于任何搜索重用)
    params_sha256 = _params_sha256(best_params)
    memberships = _resolve_fold_membership(plan, plan.oos_fold, resolver)
    frame = chain.compute(
        revision_id=strategy_id, config=plan.oos_fold.chain_config
    )
    resolved = getattr(frame, "resolved_universe", None) or {}
    fingerprint = str(resolved.get("membership_fingerprint") or ("0" * 64))
    effective_days = _effective_test_days(
        plan.trading_dates,
        plan.oos_fold.test_start,
        plan.oos_fold.test_end,
        plan.oos_fold.chain_config.end,
        plan.horizon,
    )
    if effective_days < 10:
        raise ValueError(
            f"OOS fold has {effective_days} effective days (< 10)"
        )

    stats: dict[str, Any] = {"effective_days": effective_days}
    if fold_scorer is not None:
        extra = fold_scorer(
            fold=plan.oos_fold, frame=frame, membership=memberships
        )
        if extra:
            stats.update(extra)
    else:
        _default_fold_score(
            plan,
            plan.oos_fold,
            strategy_id,
            best_params,
            _fold_symbols(memberships),
            service,
            stats,
        )
    # WR-02: 目标指标必须在写 OOS 折行 (消耗恰好一次槽位) 之前确认存在。
    test_stats = dict(stats.get("test_stats") or {})
    raw = test_stats.get(objective)
    if raw is None:
        raise ValueError(f"OOS fold has no objective '{objective}' in its test stats")
    validation_score = float(raw)
    oos_manifest = repo.record_wf_fold(
        plan_id=plan.plan_id,
        fold_index=plan.oos_fold.fold_index,
        is_oos=True,
        strategy_id=strategy_id,
        params_sha256=params_sha256,
        train_start=plan.oos_fold.train_start,
        train_end=plan.oos_fold.train_end,
        test_start=plan.oos_fold.test_start,
        test_end=plan.oos_fold.test_end,
        membership_fingerprint=fingerprint,
        chain_config=_chain_config_dict(plan.oos_fold.chain_config),
        stats=stats,
    )
    if validation_threshold is None:
        passed_gate = True
    elif default_direction(objective) == "min":
        passed_gate = bool(validation_score <= validation_threshold)
    else:
        passed_gate = bool(validation_score >= validation_threshold)
    # WR-07: 验证裁决携带 OOS 折的 PIT 成员符号 (Phase 14 组合快照绑定无需重解析)。
    resolved_asset_ids = _fold_symbols(memberships)
    # WR-06: 裁决必须携带折级证据, 绝不写空 {}。调用方可传入更丰富的 per-fold
    # 搜索证据 (如优化器的 score_distribution); 缺省时自动注入本次 OOS 折自身的
    # stats (effective_days / train_stats / test_stats), 保留审计轨迹。
    if fold_evidence is None:
        fold_evidence = {"oos": stats}
    verdict = repo.record_validated_strategy(
        strategy_id=strategy_id,
        plan_id=plan.plan_id,
        search_run_id=search_run_id,
        params_sha256=params_sha256,
        oos_evidence_fold_id=oos_manifest["id"],
        resolved_asset_ids=resolved_asset_ids,
        validation_score=validation_score,
        fold_evidence=fold_evidence,
        passed_gate=passed_gate,
    )
    return {
        "plan_id": plan.plan_id,
        "strategy_id": strategy_id,
        "params_sha256": params_sha256,
        "oos_manifest": oos_manifest,
        "validation_score": validation_score,
        "passed_gate": passed_gate,
        "verdict": verdict,
        "resolved_asset_ids": resolved_asset_ids,
    }


def _run_folds(
    *,
    plan: WalkForwardPlan,
    folds: Sequence[WalkForwardFold],
    strategy_id: str,
    params: dict[str, Any],
    params_sha256: str,
    service: Any,
    chain: FactorSignalChain,
    resolver: Any,
    repo: ResearchRepository,
    fold_scorer: Any,
) -> list[dict[str, Any]]:
    """对给定折序列逐个运行 (搜索折 + 保留 OOS 共用同一条 PIT/链/回测路径)。"""
    manifests: list[dict[str, Any]] = []
    for fold in folds:
        manifests.append(
            _run_fold(
                plan=plan,
                fold=fold,
                strategy_id=strategy_id,
                params=params,
                params_sha256=params_sha256,
                service=service,
                chain=chain,
                resolver=resolver,
                repo=repo,
                fold_scorer=fold_scorer,
            )
        )
    return manifests


# ================================================================
# 几何构造
# ================================================================


def _build_fold(
    i: int,
    trading_dates: tuple[date, ...],
    step: int,
    train_size: int,
    gap_size: int,
    test_size: int,
    universe: str,
    asset_type: str,
    horizon: int,
) -> WalkForwardFold:
    """按索引切片构造第 ``i`` 个滚动折 (train/gap/test 各精确 Tr/G/Te 个交易日)。"""
    train_lo = i * step
    train = trading_dates[train_lo : train_lo + train_size]
    gap = trading_dates[train_lo + train_size : train_lo + train_size + gap_size]
    test = trading_dates[
        train_lo + train_size + gap_size : train_lo + train_size + gap_size + test_size
    ]
    if len(train) != train_size or len(gap) != gap_size or len(test) != test_size:
        raise ValueError("insufficient history for walk-forward folds")
    return WalkForwardFold(
        fold_index=i,
        is_oos=False,
        train_start=train[0],
        train_end=train[-1],
        gap_start=gap[0],
        gap_end=gap[-1],
        test_start=test[0],
        test_end=test[-1],
        membership_fingerprint="0" * 64,
        chain_config=_fold_chain_config(
            universe, asset_type, train[0], test[-1], horizon, trading_dates
        ),
    )


def _build_oos_fold(
    fold_count: int,
    trading_dates: tuple[date, ...],
    selection_len: int,
    step: int,
    train_size: int,
    gap_size: int,
    test_size: int,
    universe: str,
    asset_type: str,
    horizon: int,
) -> WalkForwardFold:
    """保留段 OOS 折: train = 选择区 (至最末测试段尾), gap = 末折与 OOS 间的缓冲。"""
    oos = trading_dates[selection_len:]
    last_test_end_idx = (fold_count - 1) * step + train_size + gap_size + test_size - 1
    buffer = trading_dates[last_test_end_idx + 1 : selection_len]
    train_end = trading_dates[last_test_end_idx]
    gap_start = buffer[0] if buffer else train_end
    gap_end = buffer[-1] if buffer else train_end
    return WalkForwardFold(
        fold_index=fold_count,
        is_oos=True,
        train_start=trading_dates[0],
        train_end=train_end,
        gap_start=gap_start,
        gap_end=gap_end,
        test_start=oos[0],
        test_end=oos[-1],
        membership_fingerprint="0" * 64,
        chain_config=_fold_chain_config(
            universe, asset_type, trading_dates[0], oos[-1], horizon, trading_dates
        ),
    )


def _fold_chain_config(
    universe: str,
    asset_type: str,
    train_start: date,
    test_end: date,
    horizon: int,
    trading_dates: Sequence[date] | None = None,
) -> SignalChainConfig:
    """每折独立 SignalChainConfig — 共享同一条 FactorSignalChain (FACT-06)。

    标签缓冲: end = test_end 之后第 ``horizon`` 个实测交易日 (WR-09) — 链的前向
    收益 drop 是逐行 ``shift(-horizon)`` (即 horizon 个交易日), 日历日缓冲会因周末/
    节假日少于 horizon 个交易日而静默缩短可评分测试日 (实测 18/20)。吸附到实测日历
    后, 搜索折 fully-covered 时保证 effective_days == test_size。仅当实测日历在
    test_end 之后不足 horizon 个交易日 (如 OOS 折在日历末端) 时退化为日历日缓冲。
    """
    if trading_dates is not None:
        after = [day for day in trading_dates if day > test_end]
        if len(after) >= horizon:
            buffer_end = after[horizon - 1]
        else:
            buffer_end = test_end + datetime.timedelta(days=horizon)
    else:
        buffer_end = test_end + datetime.timedelta(days=horizon)
    return SignalChainConfig(
        universe=universe,
        symbols=(),
        asset_type=asset_type,
        start=train_start,
        end=buffer_end,
        warmup_days=_WARMUP_DAYS,
        forward_return_horizon=horizon,
        rebalance="daily",
    )


def _assert_geometry(
    folds: tuple[WalkForwardFold, ...],
    oos_fold: WalkForwardFold,
    trading_dates: tuple[date, ...],
    oos_size: int,
) -> None:
    """Fail-closed 几何断言: 测试段两两不相交 + 平铺, OOS 在末折之后且长度精确。"""
    position = {day: i for i, day in enumerate(trading_dates)}
    for left, right in itertools.pairwise(folds):
        if position[right.test_start] != position[left.test_end] + 1:
            raise ValueError("walk-forward test segments must tile contiguously")
        if position[right.test_start] <= position[left.test_end]:
            raise ValueError("walk-forward test segments must be disjoint")
    for fold in (*folds, oos_fold):
        if not (
            position[fold.train_end] < position[fold.gap_start] <= position[fold.gap_end]
            < position[fold.test_start]
        ):
            raise ValueError("fold rectangle must keep train < gap < test in index order")
    last = folds[-1]
    if position[last.test_end] >= position[oos_fold.test_start]:
        raise ValueError("the reserved OOS must not overlap any fold test segment")
    oos_len = sum(1 for day in trading_dates if day >= oos_fold.test_start)
    if oos_len != oos_size:
        raise ValueError("reserved OOS segment length mismatch")


# ================================================================
# 运行器
# ================================================================


def _run_fold(
    *,
    plan: WalkForwardPlan,
    fold: WalkForwardFold,
    strategy_id: str,
    params: dict[str, Any],
    params_sha256: str,
    service: Any,
    chain: FactorSignalChain,
    resolver: Any,
    repo: ResearchRepository,
    fold_scorer: Any,
) -> dict[str, Any]:
    """单个折的 PIT 解析 + 共享链计算 + 回测 + append 清单 (OOS 严格一次)。"""
    if not fold.is_oos:
        existing = _find_existing_fold(repo, plan.plan_id, fold, strategy_id, params_sha256)
        if existing is not None:
            return existing
    membership = _resolve_fold_membership(plan, fold, resolver)
    frame = chain.compute(revision_id=strategy_id, config=fold.chain_config)
    resolved = getattr(frame, "resolved_universe", None) or {}
    fingerprint = str(resolved.get("membership_fingerprint") or ("0" * 64))
    effective_days = _effective_test_days(
        plan.trading_dates,
        fold.test_start,
        fold.test_end,
        fold.chain_config.end,
        plan.horizon,
    )
    if effective_days < 10:
        raise ValueError(f"fold {fold.fold_index} has {effective_days} effective days (< 10)")

    stats: dict[str, Any] = {"effective_days": effective_days}
    if fold_scorer is not None:
        extra = fold_scorer(fold=fold, frame=frame, membership=membership)
        if extra:
            stats.update(extra)
    else:
        _default_fold_score(
            plan, fold, strategy_id, params, _fold_symbols(membership), service, stats
        )
    return repo.record_wf_fold(
        plan_id=plan.plan_id,
        fold_index=fold.fold_index,
        is_oos=fold.is_oos,
        strategy_id=strategy_id,
        params_sha256=params_sha256,
        train_start=fold.train_start,
        train_end=fold.train_end,
        test_start=fold.test_start,
        test_end=fold.test_end,
        membership_fingerprint=fingerprint,
        chain_config=_chain_config_dict(fold.chain_config),
        stats=stats,
    )


def _find_existing_fold(
    repo: ResearchRepository,
    plan_id: str,
    fold: WalkForwardFold,
    strategy_id: str,
    params_sha256: str,
) -> dict[str, Any] | None:
    """搜索折查询路径 (IN-01): 已记录的 (plan, fold_index, is_oos, strategy, params) 直接返回。

    这是 **cache-only** 读取: 它只按 (plan, fold_index, strategy_id, params_sha256)
    命中已持久化的清单, 不重新验证链配置/成员指纹。同 params 在成员漂移后重跑会
    返回旧清单 — 对 append-only 是预期行为 (每条记录是不可变事实), 但不要把它
    误读为新鲜度。成员漂移由新的 params_sha256 (或新 plan_id) 捕获。

    保持 append-only 幂等 — 重跑同一 walk-forward 时搜索折走查询路径, 仅 OOS 折
    走写路径 (严格一次)。
    """
    rows = repo.list_wf_folds(plan_id=plan_id, is_oos=fold.is_oos, limit=_LIST_CAP)
    for row in rows:
        if (
            row["fold_index"] == fold.fold_index
            and row["strategy_id"] == strategy_id
            and row["params_sha256"] == params_sha256
        ):
            return row
    return None


def _resolve_fold_membership(
    plan: WalkForwardPlan, fold: WalkForwardFold, resolver: Any
) -> Any:
    """解析折窗口的 per-date PIT 成员帧 (与 ``_run_fold`` 同窗解析)。"""
    return resolver.resolve_universe_daily(
        universe_name=plan.universe,
        start=_calendar_days_before(fold.train_start, fold.chain_config.warmup_days),
        end=fold.chain_config.end,
        asset_type=plan.asset_type,
    )


def _default_fold_score(
    plan: WalkForwardPlan,
    fold: WalkForwardFold,
    strategy_id: str,
    params: dict[str, Any],
    symbols: list[str],
    service: Any,
    stats: dict[str, Any],
) -> None:
    """默认折评分 = 固定参数策略回测 (train 窗口 + test 窗口, 复用 StrategyBacktestService)。

    IN-04: 折/OOS 评分用窗口内 PIT 成员并集 (``_fold_symbols(membership)``) 作为
    symbol 集 — 与链的 per-date 成员语义不同, 但退市符号在 test 窗口无数据行,
    生存偏差基本被数据可得性中和。Phase 14 如需严格 per-date PIT, 应把 per-date
    成员 join 应用到回测面板 (与链一致)。
    """
    train_result = service.run(
        StrategyBacktestConfig(
            strategy_id=strategy_id,
            symbols=symbols,
            start=fold.train_start,
            end=fold.train_end,
            params=params,
            asset_type=plan.asset_type,
        )
    )
    test_result = service.run(
        StrategyBacktestConfig(
            strategy_id=strategy_id,
            symbols=symbols,
            start=fold.test_start,
            end=fold.test_end,
            params=params,
            asset_type=plan.asset_type,
        )
    )
    if getattr(train_result, "error", None) is None:
        stats["train_stats"] = dict(getattr(train_result, "stats", {}) or {})
    if getattr(test_result, "error", None) is None:
        stats["test_stats"] = dict(getattr(test_result, "stats", {}) or {})


# ================================================================
# 工具
# ================================================================


def _fold_symbols(membership: Any) -> list[str]:
    """折窗口内 PIT 成员并集 (去重排序), 用作回测 symbol 集。"""
    if membership is None:
        return []
    try:
        height = membership.height
    except AttributeError:
        return []
    if not height:
        return []
    return sorted(membership["symbol"].unique().to_list())


def _effective_test_days(
    trading_dates: Sequence[date],
    test_start: date,
    test_end: date,
    compute_end: date,
    horizon: int,
) -> int:
    """可评分测试日数: 测试日 d 可评分当且仅当计算窗内 d 之后还有 horizon 个交易日。

    计算窗延伸到 ``compute_end = test_end + horizon`` (标签缓冲), 窗内最后
    ``horizon`` 个交易日的前向收益为空 (链的 ``shift(-horizon)``), 故不计入。
    """
    window = [day for day in trading_dates if day <= compute_end]
    position = {day: i for i, day in enumerate(window)}
    return sum(
        1
        for day in window
        if test_start <= day <= test_end and position[day] + horizon < len(window)
    )


def _calendar_days_before(day: date, days: int) -> date:
    """``day`` 之前 ``days`` 个日历日 (warmup 是日历日, 非交易日)。"""
    return date.fromordinal(day.toordinal() - days)


def _chain_config_dict(config: SignalChainConfig) -> dict[str, Any]:
    """SignalChainConfig → JSON 可序列化 dict (写入 wf_folds.chain_config_json)。"""
    return {
        "universe": config.universe,
        "symbols": list(config.symbols),
        "asset_type": config.asset_type,
        "start": config.start.isoformat(),
        "end": config.end.isoformat(),
        "warmup_days": config.warmup_days,
        "forward_return_horizon": config.forward_return_horizon,
        "rebalance": config.rebalance,
    }


def _params_sha256(params: dict[str, Any]) -> str:
    """参数规范化 SHA-256 (wf_folds 恰好一次键的一部分)。"""
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _to_date(value: Any) -> date:
    """``date``/``datetime`` → ``date`` (datetime 是 date 子类, 需先判)。"""
    return value.date() if isinstance(value, datetime.datetime) else value

# ---------------------------------------------------------------------------
# 策略 walk-forward 优化 (upstream v0.2) — 滚动窗口的样本内优化 + 样本外验证。
#
# 每折在训练区间用参数网格优化选出最优参数, 再在紧邻的测试区间用该参数做样本外(OOS)
# 回测。滚动前移。核心产出是 OOS 拼接净值 + 每折 IS-vs-OOS 退化 —— 样本内漂亮、样本外
# 崩溃即过拟合信号, 单次样本内回测看不到。
#
# 依赖 StrategyOptimizer 做每折训练区间的网格优化。
# ---------------------------------------------------------------------------


@dataclass
class Fold:
    index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date


def generate_folds(
    start: date,
    end: date,
    train_days: int,
    test_days: int,
    step_days: int,
) -> list[Fold]:
    """滚动窗口 fold 切分: 训练窗口固定长度, 测试窗口紧接其后, 按 step 前移。

    测试区间超出 end 即停止。数据区间放不下一折则抛错。
    """
    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("train_days / test_days / step_days 必须为正")

    folds: list[Fold] = []
    i = 0
    train_start = start
    while True:
        train_end = train_start + timedelta(days=train_days)
        # 测试区间从训练末日的次日开始: 回测区间是闭区间, 若 test_start==train_end 则
        # 该日 K 线同时进训练优化与 OOS 首日, 构成前视泄漏。后移一天隔断。
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days)
        if test_end > end:
            break
        folds.append(Fold(i, train_start, train_end, test_start, test_end))
        i += 1
        train_start = train_start + timedelta(days=step_days)

    if not folds:
        raise ValueError(
            f"数据区间不足以切出至少一折 (需 train+test={train_days + test_days}天, "
            f"实有 {(end - start).days}天)"
        )
    return folds


def _norm(v: float, direction: str) -> float:
    """把目标值归一到"越大越好"空间, 以便跨目标一致地算退化 (min 类目标取负)。"""
    return -v if direction == "min" else v


def aggregate_oos(fold_records: list[dict], objective: str, direction: str = "max") -> dict:
    """从**有效折** (IS 与 OOS 都成功) 聚合: 复利净值 / IS-OOS 退化 / 一致性。

    调用方只传有效折 (best_params 非空且 OOS 未 error), 故此处每折 is_score/oos_objective
    均有值, 无需 .get 默认兜底 —— 无效折被伪装成 0 收益混入曾是 H1/H2 的根因。

    - compounded_oos_return: 各折 OOS 总收益复利
    - degradation: 归一空间下 IS 目标均值 - OOS 目标均值, 正值 = 样本外退化 (过拟合信号),
      对"越小越好"目标 (max_drawdown 等) 方向也正确
    - consistency: OOS 总收益 > 0 的折占比 (与目标方向无关, 直观)
    """
    n = len(fold_records)
    if n == 0:
        return {
            "n_folds": 0,
            "compounded_oos_return": 0.0,
            "avg_is_objective": None,
            "avg_oos_objective": None,
            "degradation": None,
            "consistency": 0.0,
            "oos_equity_curve": [],
        }

    equity = 1.0
    curve: list[dict] = []
    n_positive = 0
    for f in fold_records:
        r = float(f["oos_stats"].get("total_return", 0.0) or 0.0)
        equity *= (1 + r)
        if r > 0:
            n_positive += 1
        curve.append({"fold": f["index"], "date": str(f["test_end"]), "value": round(equity, 4)})

    is_vals = [f["is_score"] for f in fold_records if f["is_score"] is not None]
    oos_vals = [f["oos_objective"] for f in fold_records if f["oos_objective"] is not None]
    avg_is = round(float(sum(is_vals) / len(is_vals)), 4) if is_vals else None
    avg_oos = round(float(sum(oos_vals) / len(oos_vals)), 4) if oos_vals else None
    degradation = (
        round(_norm(avg_is, direction) - _norm(avg_oos, direction), 4)
        if (avg_is is not None and avg_oos is not None) else None
    )

    return {
        "n_folds": n,
        "compounded_oos_return": round(equity - 1.0, 4),
        "avg_is_objective": avg_is,
        "avg_oos_objective": avg_oos,
        "degradation": degradation,
        "consistency": round(n_positive / n, 4),
        "oos_equity_curve": curve,
    }


@dataclass
class WalkForwardConfig:
    strategy_id: str
    symbols: list[str] | None
    start: date
    end: date
    param_grid: dict
    objective: str = "sortino"
    train_days: int = 252
    test_days: int = 63
    step_days: int = 63
    direction: str | None = None
    max_workers: int = 4
    base_params: dict = field(default_factory=dict)
    overrides: dict | None = None
    backtest_kwargs: dict = field(default_factory=dict)
    matrix_cache_max_mb: int = 512


class WalkForwardService:
    """滚动窗口 walk-forward: 每折训练区间优化 -> 测试区间 OOS 验证 -> 聚合。"""

    def __init__(self, optimizer, service, strategy_engine) -> None:
        self.optimizer = optimizer
        self.service = service
        self.strategy_engine = strategy_engine

    def _prepare_shared_matrix(self, cfg: WalkForwardConfig, folds: list[Fold]):
        """Build one immutable superset matrix for every matrix-native fold."""
        if self.strategy_engine is None or not folds:
            return None
        strategy = self.strategy_engine.get(cfg.strategy_id)
        if strategy.execution_backend != "matrix_native":
            raise ValueError(
                f"步进优化暂仅支持矩阵(matrix_native)策略; "
                f"{cfg.strategy_id} 是 {strategy.execution_backend}"
            )

        from app.backtest.optimizer import expand_param_grid
        from app.backtest.strategy import StrategyBacktestConfig

        combos = expand_param_grid(strategy.meta.get("params", []), cfg.param_grid)
        shared_start = min(fold.train_start for fold in folds)
        shared_end = max(fold.test_end for fold in folds)
        configs = [
            StrategyBacktestConfig(
                strategy_id=cfg.strategy_id,
                symbols=cfg.symbols,
                start=shared_start,
                end=shared_end,
                params={**cfg.base_params, **combo},
                overrides=cfg.overrides,
                **cfg.backtest_kwargs,
            )
            for combo in combos
        ]
        return self.service.prepare_matrix_optimization(
            configs,
            matrix_cache_max_bytes=int(cfg.matrix_cache_max_mb) * 1024 * 1024,
        )

    def run(
        self,
        cfg: WalkForwardConfig,
        progress_cb=None,
        cancel_event=None,
    ) -> dict:
        from app.backtest.optimizer import OptimizeConfig, default_direction
        from app.backtest.strategy import StrategyBacktestConfig

        t0 = time.perf_counter()
        direction = cfg.direction or default_direction(cfg.objective)
        folds = generate_folds(cfg.start, cfg.end, cfg.train_days, cfg.test_days, cfg.step_days)
        n_total = len(folds)

        shared_prepared = self._prepare_shared_matrix(cfg, folds)
        shared_market_data = (
            shared_prepared.market_data if shared_prepared is not None else None
        )
        shared_date_labels = (
            tuple(label[:10] for label in shared_market_data.timestamp_labels)
            if shared_market_data is not None
            else ()
        )

        def _shared_window_has_data(window_start: date, window_end: date) -> bool:
            index = bisect_left(shared_date_labels, window_start.isoformat())
            return index < len(shared_date_labels) and shared_date_labels[index] <= window_end.isoformat()

        # 遥测: 首尾快照 PanelCache, 量化跨折重叠区间重复扫盘的 IO 占比 (是否值得进一步优化)。
        cache_before = self.service.engine.cache_stats()

        valid_records: list[dict] = []   # IS 与 OOS 都成功, 计入聚合
        skipped: list[dict] = []          # 无优化结果 或 OOS 失败, 不计入聚合 (避免伪装成有效折)
        done = 0

        # IS 训练区间强制 position 模式: full 模式会让训练折未平仓持仓用 train_end 之后
        # (即 OOS 区间) 的真实 K 线平仓, IS 分数被未来数据污染 -> 优化选参乐观偏移, 使过拟合
        # 被掩盖。OOS 回测保留用户所选 mode。参数扫描优化只看正式区间内的表现即可。
        is_backtest_kwargs = {**cfg.backtest_kwargs, "mode": "position"}

        for f in folds:
            if cancel_event is not None and cancel_event.is_set():
                break

            base = {
                "index": f.index,
                "train_start": str(f.train_start),
                "train_end": str(f.train_end),
                "test_start": str(f.test_start),
                "test_end": str(f.test_end),
            }
            missing_window = None
            if shared_market_data is not None:
                if not _shared_window_has_data(f.train_start, f.train_end):
                    missing_window = "训练区间无可用行情数据"
                elif not _shared_window_has_data(f.test_start, f.test_end):
                    missing_window = "测试区间无可用行情数据"
            if missing_window is not None:
                skipped.append({**base, "reason": missing_window})
                done += 1
                if progress_cb is not None:
                    progress_cb({"type": "walkforward_progress", "done": done, "total": n_total, "fold": f.index})
                continue

            # 训练区间: 网格优化选最优参数
            opt_cfg = OptimizeConfig(
                strategy_id=cfg.strategy_id,
                symbols=cfg.symbols,
                start=f.train_start,
                end=f.train_end,
                param_grid=cfg.param_grid,
                objective=cfg.objective,
                direction=cfg.direction,
                max_workers=cfg.max_workers,
                base_params=cfg.base_params,
                overrides=cfg.overrides,
                backtest_kwargs=is_backtest_kwargs,  # IS 强制 position, 堵前视泄漏
            )
            if shared_market_data is None:
                opt_res = self.optimizer.optimize(opt_cfg, cancel_event=cancel_event)
            else:
                opt_res = self.optimizer.optimize(
                    opt_cfg,
                    cancel_event=cancel_event,
                    prepared_market_data=shared_market_data,
                )
            best_params = opt_res.get("best_params")
            is_score = opt_res.get("best_score")
            done += 1

            # 训练区间没优化出参数 (全组失败/取消) -> 跳过, 不用默认参数硬跑 OOS 伪装成有效折
            if best_params is None:
                skipped.append({**base, "reason": "训练区间未优化出参数"})
                if progress_cb is not None:
                    progress_cb({"type": "walkforward_progress", "done": done, "total": n_total, "fold": f.index})
                continue

            # 测试区间: 用最优参数做样本外回测
            merged = {**cfg.base_params, **best_params}
            oos_cfg = StrategyBacktestConfig(
                strategy_id=cfg.strategy_id,
                symbols=cfg.symbols,
                start=f.test_start,
                end=f.test_end,
                params=merged,
                overrides=cfg.overrides,
                **cfg.backtest_kwargs,
            )
            oos_prepared = None
            try:
                if shared_market_data is not None:
                    oos_prepared = self.service.prepare_matrix_optimization(
                        [oos_cfg],
                        matrix_cache_max_bytes=int(cfg.matrix_cache_max_mb) * 1024 * 1024,
                        market_data_override=shared_market_data,
                    )
                if oos_prepared is None:
                    oos_res = self.service.run(
                        oos_cfg,
                        cancel_event=cancel_event,
                    )
                else:
                    oos_res = self.service.run(
                        oos_cfg,
                        cancel_event=cancel_event,
                        prepared=oos_prepared,
                    )
            finally:
                if oos_prepared is not None:
                    oos_prepared.compute_cache.close()

            # OOS 失败 (含 cancelled) -> 跳过, 不把空/0 收益混入复利曲线
            if oos_res.error:
                skipped.append({**base, "best_params": best_params, "reason": f"OOS 回测失败: {oos_res.error}"})
                if progress_cb is not None:
                    progress_cb({"type": "walkforward_progress", "done": done, "total": n_total, "fold": f.index})
                continue

            oos_objective = oos_res.stats.get(cfg.objective)
            # 该折 OOS 是否较 IS 退化 (方向感知: min 类目标数值更大才是退化)
            oos_degraded = (
                _norm(oos_objective, direction) < _norm(is_score, direction)
                if (oos_objective is not None and is_score is not None) else None
            )
            valid_records.append({
                **base,
                "best_params": best_params,
                "is_score": is_score,
                "oos_objective": oos_objective,
                "oos_degraded": oos_degraded,
                "oos_stats": oos_res.stats,
            })

            if progress_cb is not None:
                progress_cb({"type": "walkforward_progress", "done": done, "total": n_total, "fold": f.index})

        summary = aggregate_oos(valid_records, cfg.objective, direction)

        shared_matrix_bytes = (
            shared_prepared.market_data.nbytes if shared_prepared is not None else 0
        )
        shared_matrix_status = (
            shared_prepared.market_data.cache_status if shared_prepared is not None else "none"
        )
        if shared_prepared is not None:
            shared_prepared.compute_cache.close()

        # 遥测收尾: 本次 WF 累计扫盘耗时 / 命中 / 复用, 与总耗时对比得出 load_panel 占比。
        cache_after = self.service.engine.cache_stats()
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        io_seconds = round(cache_after["compute_seconds"] - cache_before["compute_seconds"], 4)
        io_pct = round(io_seconds * 1000 / elapsed_ms * 100, 1) if elapsed_ms > 0 else 0.0
        cache_telemetry = {
            "load_panel_seconds": io_seconds,
            "load_panel_pct": io_pct,  # 扫盘耗时 / WF 总耗时
            "scans": cache_after["compute_count"] - cache_before["compute_count"],
            "hits": cache_after["hit_count"] - cache_before["hit_count"],
            "single_flight_reuses": cache_after["reuse_count"] - cache_before["reuse_count"],
        }
        logger.info(
            "walk-forward IO 占比: load_panel %.3fs (%.1f%% of %.1fms) | 扫盘 %d 次 命中 %d 复用 %d",
            io_seconds, io_pct, elapsed_ms,
            cache_telemetry["scans"], cache_telemetry["hits"], cache_telemetry["single_flight_reuses"],
        )

        return {
            "objective": cfg.objective,
            "direction": direction,
            "n_folds": len(valid_records),
            "n_skipped": len(skipped),
            "n_planned_folds": n_total,
            "folds": valid_records,
            "skipped": skipped,
            "summary": summary,
            "cache_telemetry": cache_telemetry,
            "shared_market_data": shared_prepared is not None,
            "shared_market_data_bytes": shared_matrix_bytes,
            "shared_market_data_status": shared_matrix_status,
            "elapsed_ms": elapsed_ms,
        }