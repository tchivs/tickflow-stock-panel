"""优化器编排测试 — 用假 service 注入受控 stats, 验证排序/取消/进度/目标方向。"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date

import pytest

from app.backtest.optimizer import OptimizeConfig, StrategyOptimizer

# ---- 假 StrategyDef / 引擎 / service ----

@dataclass
class _FakeDef:
    meta: dict


class _FakeEngine:
    def __init__(self, params_meta):
        self._def = _FakeDef(meta={"params": params_meta})

    def get(self, strategy_id):
        return self._def


@dataclass
class _FakeResult:
    stats: dict
    error: str | None = None


class _FakeService:
    """run() 依据 params 返回受控 stats: sortino = ma_proximity 的映射, 便于校验排序。"""

    def __init__(self, score_fn):
        self.score_fn = score_fn
        self.calls = []
        self._lock = threading.Lock()

    def run(self, config, progress_cb=None, cancel_event=None):
        with self._lock:
            self.calls.append(dict(config.params or {}))
        return self.score_fn(config.params or {})


PARAMS_META = [
    {"id": "ma_proximity", "type": "float", "default": 0.02, "min": 0.01, "max": 0.05, "step": 0.005},
]


def _optimizer(score_fn):
    return StrategyOptimizer(_FakeService(score_fn), _FakeEngine(PARAMS_META))


def _cfg(**kw):
    base = dict(
        strategy_id="s", symbols=None, start=date(2024, 1, 1), end=date(2024, 6, 1),
        param_grid={"ma_proximity": [0.01, 0.02, 0.03]}, objective="sortino", max_workers=4,
    )
    base.update(kw)
    return OptimizeConfig(**base)


def test_ranks_best_by_objective_max():
    # sortino 随 ma_proximity 递增 -> 最大值应为 0.03
    def score(p):
        return _FakeResult(stats={"sortino": p["ma_proximity"] * 100})
    out = _optimizer(score).optimize(_cfg())
    assert out["best_params"] == {"ma_proximity": 0.03}
    assert out["best_score"] == 3.0
    assert out["n_combinations"] == 3
    assert out["n_completed"] == 3
    assert [r["rank"] for r in out["results"]] == [1, 2, 3]
    assert out["results"][0]["params"] == {"ma_proximity": 0.03}


def test_all_combos_executed_once():
    def score(p):
        return _FakeResult(stats={"sortino": 1.0})
    opt = _optimizer(score)
    out = opt.optimize(_cfg(param_grid={"ma_proximity": [0.01, 0.02, 0.03, 0.04, 0.05]}))
    assert out["n_combinations"] == 5
    # 每组恰跑一次
    ran = sorted(c["ma_proximity"] for c in opt.service.calls)
    assert ran == [0.01, 0.02, 0.03, 0.04, 0.05]


def test_min_direction_objective_restores_display_sign():
    # avg_holding_days 是 min 方向: 最小者最优, 且 best_score 必须是原始正值 (非内部取负值)
    def score(p):
        return _FakeResult(stats={"avg_holding_days": p["ma_proximity"] * 100})
    out = _optimizer(score).optimize(_cfg(objective="avg_holding_days"))
    assert out["best_params"] == {"ma_proximity": 0.01}
    # min 方向: 最优 avg_holding_days = 0.01*100 = 1.0, 用户应看到 +1.0 而非 -1.0
    assert out["best_score"] == 1.0
    # results 不应外露内部排序键 _sort
    assert all("_sort" not in r for r in out["results"])
    assert out["results"][0]["objective_raw"] == 1.0


def test_max_drawdown_objective_prefers_smaller_drawdown():
    # max_drawdown 为负值, max 方向: -0.1 (回撤更小) 应优于 -0.3
    def score(p):
        dd = {0.01: -0.1, 0.02: -0.3, 0.03: -0.2}[p["ma_proximity"]]
        return _FakeResult(stats={"max_drawdown": dd})
    out = _optimizer(score).optimize(_cfg(objective="max_drawdown"))
    assert out["best_params"] == {"ma_proximity": 0.01}
    assert out["best_score"] == -0.1  # 展示原始负值


def test_service_exception_isolated_not_crashing_batch():
    # 某组 service.run 抛异常 -> 应记为该组失败, 其余组正常完成, 不拖垮整批
    def score(p):
        if p["ma_proximity"] == 0.02:
            raise KeyError("boom")
        return _FakeResult(stats={"sortino": p["ma_proximity"] * 100})
    out = _optimizer(score).optimize(_cfg())
    assert out["n_completed"] == 3  # 三组都有结果记录 (含失败组)
    assert out["best_params"] == {"ma_proximity": 0.03}  # 最优组不受影响
    failed = [r for r in out["results"] if r.get("error")]
    assert len(failed) == 1
    assert "boom" in failed[0]["error"]


def test_backtest_kwargs_illegal_key_rejected():
    def score(p):
        return _FakeResult(stats={"sortino": 1.0})
    with pytest.raises(ValueError, match=r"非法字段|不能包含"):
        _optimizer(score).optimize(_cfg(backtest_kwargs={"bad_field": 1}))


def test_backtest_kwargs_reserved_key_rejected():
    def score(p):
        return _FakeResult(stats={"sortino": 1.0})
    with pytest.raises(ValueError, match="不能包含"):
        _optimizer(score).optimize(_cfg(backtest_kwargs={"symbols": ["x"]}))


def test_base_params_merged_and_overridden_by_sweep():
    # base_params 提供固定参数, combo 覆盖同名; 记录 service 实际收到的 params
    def score(p):
        return _FakeResult(stats={"sortino": 1.0})
    opt = _optimizer(score)
    opt.optimize(_cfg(base_params={"ma_proximity": 0.99, "other": 7}))
    # 每次 run 收到的 params: ma_proximity 被 combo 覆盖, other 保留
    for call in opt.service.calls:
        assert call["other"] == 7
        assert call["ma_proximity"] in (0.01, 0.02, 0.03)


def test_none_and_error_results_sink_to_bottom():
    # ma_proximity=0.02 的组返回 error, 0.03 的 sortino=None -> 都应排在有效结果之后
    def score(p):
        if p["ma_proximity"] == 0.02:
            return _FakeResult(stats={}, error="boom")
        if p["ma_proximity"] == 0.03:
            return _FakeResult(stats={"sortino": None})
        return _FakeResult(stats={"sortino": 5.0})
    out = _optimizer(score).optimize(_cfg())
    assert out["best_params"] == {"ma_proximity": 0.01}
    assert out["best_score"] == 5.0
    # 失败/None 组仍在结果里但 rank 靠后
    assert out["n_completed"] == 3
    assert out["results"][0]["params"] == {"ma_proximity": 0.01}


def test_cancel_event_stops_remaining():
    ev = threading.Event()
    ev.set()  # 一开始就取消

    def score(p):
        return _FakeResult(stats={"sortino": 1.0})
    opt = _optimizer(score)
    out = opt.optimize(_cfg(), cancel_event=ev)
    # 取消后所有组跳过 -> 无有效结果
    assert opt.service.calls == []
    assert out["best_params"] is None


def test_progress_callback_reports_done_total():
    seen = []

    def score(p):
        return _FakeResult(stats={"sortino": 1.0})

    def cb(msg):
        seen.append(msg)
    _optimizer(score).optimize(_cfg(), progress_cb=cb)
    assert len(seen) == 3
    assert seen[-1]["done"] == 3
    assert all(m["total"] == 3 for m in seen)


def test_invalid_objective_rejected():
    def score(p):
        return _FakeResult(stats={"sortino": 1.0})
    with pytest.raises(ValueError, match="不支持的优化目标"):
        _optimizer(score).optimize(_cfg(objective="not_a_metric"))


# ---------------------------------------------------------------------------
# WFWD-02: OOS-scored walk-forward search — RED until 13-03 lands WalkForwardOptimizer
# ---------------------------------------------------------------------------


class _WfFold:
    def __init__(self, fold_index: int, is_oos: bool) -> None:
        self.fold_index = fold_index
        self.is_oos = is_oos
        self.train_start = date(2025, 7, 29)
        self.train_end = date(2026, 1, 22)
        self.gap_start = date(2026, 1, 23)
        self.gap_end = date(2026, 2, 27)
        self.test_start = date(2026, 3, 2)
        self.test_end = date(2026, 3, 27)


class _WfPlan:
    def __init__(self, folds: list[_WfFold], oos_fold: _WfFold | None = None) -> None:
        self.folds = tuple(folds)
        self.oos_fold = oos_fold if oos_fold is not None else _WfFold(0, True)
        self.plan_id = "wf-plan-oos"
        self.universe = "cn-a-share"
        self.asset_type = "stock"
        self.start = date(2025, 7, 29)
        self.end = date(2026, 7, 30)
        self.train_size = 120
        self.gap_size = 20
        self.test_size = 20
        self.oos_size = 40
        self.horizon = 5
        self.trading_dates = [date(2025, 7, 29)]


_WF_PLAN_3_FOLDS = _WfPlan([_WfFold(0, False), _WfFold(1, False), _WfFold(2, False)])


def _wf_optimizer(score_fn, params_meta=PARAMS_META):
    from app.backtest.optimizer import WalkForwardOptimizer  # RED until 13-03

    return WalkForwardOptimizer(_FakeService(score_fn), _FakeEngine(params_meta))


def test_wf_search_folds_exclude_plan_oos_fold():
    """The reserved OOS is structurally excluded; a plan leaking it fails closed."""
    # plan.folds must never contain is_oos=True by construction — fail closed.
    leaked = _WfPlan([_WfFold(0, False), _WfFold(0, True)])
    with pytest.raises(ValueError, match="OOS"):
        _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": 1.0})).optimize(
            plan=leaked, strategy_id="s", param_grid={"ma_proximity": [0.01]}, objective="sharpe"
        )


def test_wf_search_scores_test_folds_only_never_oos():
    """WFWD-02: never in-sample — every scored window is a fold test segment."""
    seen: list[dict] = []

    def score(p):
        return _FakeResult(stats={"sharpe": p["ma_proximity"] * 100})

    def record_run(bt_cfg, progress_cb=None, cancel_event=None):  # type: ignore[no-untyped-def]
        seen.append({"start": bt_cfg.start, "end": bt_cfg.end})
        return score(bt_cfg.params)

    svc = _FakeService(lambda p: _FakeResult(stats={"sharpe": 1.0}))
    svc.run = record_run
    opt = _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": 1.0}))
    opt.service.run = record_run
    out = opt.optimize(
        plan=_WF_PLAN_3_FOLDS, strategy_id="s", param_grid={"ma_proximity": [0.01]}, objective="sharpe"
    )
    assert out["n_trials"] == 1
    assert out["best_params"] == {"ma_proximity": 0.01}


def test_wf_search_trials_use_per_fold_membership_symbols_when_resolver_passed(
    fixture_membership,
) -> None:
    """BL-01: search trials score on the per-fold PIT membership universe, never None.

    With a resolver the optimizer threads each fold's ``_fold_symbols(membership)``
    into every trial backtest — identical to the fold/OOS scorer — so best_params
    and the OOS unbiased estimate live on the same universe. Without a resolver
    (explicit opt-out) the trial symbol set falls back to ``[]`` (empty), never the
    full lake universe via ``symbols=None``.
    """
    from tests.backtest.conftest import StubUniverseResolver

    resolver = StubUniverseResolver(fixture_membership)
    seen: list[dict] = []

    def record_run(bt_cfg, progress_cb=None, cancel_event=None):  # type: ignore[no-untyped-def]
        del progress_cb, cancel_event
        seen.append(
            {
                "symbols": list(bt_cfg.symbols) if bt_cfg.symbols is not None else None,
                "start": bt_cfg.start,
                "end": bt_cfg.end,
            }
        )
        return _FakeResult(stats={"sharpe": 1.0})

    opt = _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": 1.0}))
    opt.service.run = record_run
    out = opt.optimize(
        plan=_WF_PLAN_3_FOLDS,
        strategy_id="s",
        param_grid={"ma_proximity": [0.01, 0.02]},
        objective="sharpe",
        resolver=resolver,
    )
    # 2 combos x 3 search folds = 6 trial runs; every trial carries the per-fold
    # membership symbol set (never None / never the full lake universe).
    assert len(seen) == 6
    assert all(call["symbols"] is not None for call in seen)
    assert all(call["symbols"] for call in seen)  # non-empty PIT membership
    expected = sorted(set(fixture_membership["symbol"].to_list()))
    assert all(sorted(call["symbols"]) == expected for call in seen)
    # search_space records the auditable universe fingerprint.
    universe = out["search_space"]["universe"]
    assert universe["n_symbols"] == len(expected)
    assert universe["per_fold_symbol_counts"] == {"fold_0": 4, "fold_1": 4, "fold_2": 4}
    assert len(universe["fingerprint"]) == 64

    # Without a resolver the optimizer must NOT fall back to symbols=None (the
    # full-lake-universe bug); an explicit opt-out degrades to the empty set.
    seen.clear()
    opt2 = _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": 1.0}))
    opt2.service.run = record_run
    opt2.optimize(
        plan=_WF_PLAN_3_FOLDS,
        strategy_id="s",
        param_grid={"ma_proximity": [0.01]},
        objective="sharpe",
    )
    assert len(seen) == 3
    assert all(call["symbols"] == [] for call in seen)


def test_wf_search_grid_cap_respected():
    """The GRID_MAX_COMBINATIONS cap is inherited; an over-cap grid raises first."""
    wide = [
        {"id": "n", "type": "int", "default": 1, "min": 1, "max": 100000, "step": 1}
    ]
    with pytest.raises(ValueError, match=r"上限|GRID|超过"):
        _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": 1.0}), wide).optimize(
            plan=_WF_PLAN_3_FOLDS, strategy_id="s",
            param_grid={"n": {"min": 1, "max": 5000, "step": 1}},
            objective="sharpe",
        )


def test_wf_search_records_trial_space_and_score_distribution():
    """WFWD-02 bookkeeping: n_trials + search_space + score_distribution recorded."""
    out = _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": p["ma_proximity"] * 100})).optimize(
        plan=_WF_PLAN_3_FOLDS, strategy_id="s",
        param_grid={"ma_proximity": [0.01, 0.02, 0.03]}, objective="sharpe",
    )
    assert out["n_trials"] == 3
    assert out["search_space"]["param_grid"] == {"ma_proximity": [0.01, 0.02, 0.03]}
    dist = out["score_distribution"]
    assert "per_trial" in dist and "per_fold" in dist
    assert dist["min"] <= dist["median"] <= dist["max"]
    assert dist["mean"] > 0 and dist["std"] >= 0


def test_wf_search_isolates_per_combo_failures():
    """One failing combo is isolated and sinks to the bottom."""
    def score(p):
        if p["ma_proximity"] == 0.02:
            raise RuntimeError("combo boom")
        return _FakeResult(stats={"sharpe": p["ma_proximity"] * 100})

    out = _wf_optimizer(score).optimize(
        plan=_WF_PLAN_3_FOLDS, strategy_id="s",
        param_grid={"ma_proximity": [0.01, 0.02, 0.03]}, objective="sharpe",
    )
    assert out["n_completed"] == 3
    assert out["best_params"] == {"ma_proximity": 0.03}
    failed = [r for r in out["results"] if r.get("error")]
    assert len(failed) == 1 and "combo boom" in failed[0]["error"]


def test_wf_search_records_search_run_row():
    """A completed search with no repo returns search_run_id=None (WR-10).

    A fabricated uuid would never be persisted and would FK-fail later inside
    evaluate_best_params(search_run_id=...) — returning None keeps that path honest.
    """
    out = _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": 1.0})).optimize(
        plan=_WF_PLAN_3_FOLDS, strategy_id="s",
        param_grid={"ma_proximity": [0.01]}, objective="sharpe",
    )
    assert out["search_run_id"] is None  # repo=None → no fabricated id


def test_wf_search_persists_search_run_row_when_repo_passed(research_repository):
    """With a repo the search persists wf_search_runs (oos_excluded=1 enforced)."""
    research_repository.create_wf_plan(_WF_PLAN_3_FOLDS)  # FK: plan must exist first
    out = _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": 1.0})).optimize(
        plan=_WF_PLAN_3_FOLDS, strategy_id="s",
        param_grid={"ma_proximity": [0.01, 0.02]}, objective="sharpe",
        repo=research_repository,
    )
    assert out["search_run_id"]
    import sqlite3

    with sqlite3.connect(research_repository.database_path) as connection:
        row = connection.execute(
            "SELECT oos_excluded, n_trials, plan_id FROM wf_search_runs WHERE id = ?",
            (out["search_run_id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == 1  # oos_excluded=1 persisted
    assert row[1] == 2  # n_trials == len(combos)
    assert row[2] == "wf-plan-oos"


def test_wf_search_oos_excluded_zero_fails_closed(research_repository):
    """record_wf_search fails closed unless oos_excluded=1 (WFWD-02 guard)."""
    with pytest.raises(ValueError, match="oos_excluded=1"):
        research_repository.record_wf_search(
            plan_id="wf-plan-oos",
            strategy_id="s",
            objective="sharpe",
            direction="max",
            search_space={"param_grid": {}, "params_meta": []},
            n_trials=1,
            n_completed=1,
            score_distribution={"per_trial": [], "per_fold": {}, "min": 1.0, "max": 1.0},
            best_params={},
            best_score=1.0,
            oos_excluded=0,
        )


def test_wf_search_never_scores_train_or_oos_windows():
    """WFWD-02: a scorer that records every window sees only fold test segments."""
    seen: list[tuple[date, date]] = []

    def record_run(bt_cfg, progress_cb=None, cancel_event=None):  # type: ignore[no-untyped-def]
        del progress_cb, cancel_event
        seen.append((bt_cfg.start, bt_cfg.end))
        return _FakeResult(stats={"sharpe": 1.0})

    opt = _wf_optimizer(lambda p: _FakeResult(stats={"sharpe": 1.0}))
    opt.service.run = record_run
    out = opt.optimize(
        plan=_WF_PLAN_3_FOLDS, strategy_id="s",
        param_grid={"ma_proximity": [0.01, 0.02]}, objective="sharpe",
    )
    assert out["n_trials"] == 2
    # 2 combos x 3 search folds = 6 test-window runs; every window is exactly the
    # fold test segment (2026-03-02..2026-03-27) — never a train window, never OOS.
    expected = (date(2026, 3, 2), date(2026, 3, 27))
    assert len(seen) == 2 * 3
    assert all((s, e) == expected for s, e in seen)


def test_wf_search_min_direction_reports_raw_best_score():
    """WR-05: min-direction objectives report the RAW best_score, not the negated sign.

    ``avg_holding_days`` is min-direction; a 1.0-day holding pool must surface as
    +1.0 (raw metric space, comparable to OOS validation_score) — never -1.0.
    """
    def score(p):
        return _FakeResult(stats={"avg_holding_days": p["ma_proximity"] * 100})

    out = _wf_optimizer(score).optimize(
        plan=_WF_PLAN_3_FOLDS, strategy_id="s",
        param_grid={"ma_proximity": [0.01, 0.02]}, objective="avg_holding_days",
    )
    assert out["best_params"] == {"ma_proximity": 0.01}  # 最小者最优 (min 方向)
    # best_score 在原始指标空间 = 0.01*100 = 1.0 (非取负的 -1.0)。
    assert out["best_score"] == 1.0
    # per_trial / per_fold 分布也报告原始值。
    top = out["results"][0]
    assert top["objective_raw"] == 1.0
    assert out["score_distribution"]["min"] == 1.0

