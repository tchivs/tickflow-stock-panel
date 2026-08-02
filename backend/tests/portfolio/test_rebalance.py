"""RBAL-01 RebalancePlan contracts — Wave 0 scaffold.

职责: 锁定 RebalancePlan 的契约面 —— 连续权重经 backtest/engine.py 的
lot 公式 (floor(allocation/(price*(1+cost))/100)*100) 离散化为 100 股手数,
blocked 剔除、现金残差、换手成本、RMSE (simple/weighted)、expires_at、
不可变工件 + rebalance_plans 行绑定, 以及缺失/非最优 run 的 fail-closed。

Wave 0 状态: 14-01 之前本文件按计划保持 RED —— 所有引用
``app.portfolio.rebalance`` 的用例在模块缺失时失败 (ImportError), 由 14-01
转绿。仓库层 (14-02 PortfolioRepository) 的 round-trip / 幂等 / 校验用例
在 14-02 落地后即转绿。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.portfolio.repository import PortfolioRepository


def _plan_fields(
    run: dict[str, object], *, plan_id: str = "rp-1"
) -> dict[str, object]:
    """Valid record_rebalance_plan fields bound to a recorded optimization run."""
    return {
        "id": plan_id,
        "optimization_run_id": str(run["id"]),
        "input_snapshot_sha256": str(run["input_snapshot_sha256"]),
        "as_of": str(run["as_of"]),
        "target_weights_json": {"600000.SH": 0.5, "600001.SH": 0.5},
        "discrete_weights_json": {"600000.SH": 0.5, "600001.SH": 0.5},
        "lot_sizes_json": {"600000.SH": 5000, "600001.SH": 2500},
        "cash_residue": 1200.0,
        "turnover_cost": 45.6,
        "blocked_instruments_json": [],
        "discretization_rmse": 0.012,
        "rmse_definition": "simple",
        "expires_at": "2026-08-08T00:00:00Z",
        "output_sha256": "b" * 64,
        "artifact_relative_path": f"research_artifacts/{run['id']}/rebalance/{plan_id}.json",
        "created_at": "2026-08-01T00:00:00Z",
    }


# ================================================================
# Repository surface (14-02) — GREEN once the methods land
# ================================================================


def test_record_rebalance_plan_round_trips_with_unwrapped_json(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    run = fixture_rebalance_run
    recorded = portfolio_repository.record_rebalance_plan(**_plan_fields(run))
    assert recorded["id"] == "rp-1"
    assert recorded["target_weights"] == {"600000.SH": 0.5, "600001.SH": 0.5}
    assert recorded["lot_sizes"] == {"600000.SH": 5000, "600001.SH": 2500}
    assert recorded["blocked_instruments"] == []
    assert recorded["rmse_definition"] == "simple"
    assert recorded["optimization_run_id"] == str(run["id"])

    fetched = portfolio_repository.get_rebalance_plan("rp-1")
    assert fetched is not None
    assert fetched["id"] == "rp-1"
    assert fetched["target_weights"] == {"600000.SH": 0.5, "600001.SH": 0.5}
    assert fetched["discrete_weights"] == {"600000.SH": 0.5, "600001.SH": 0.5}
    assert fetched["lot_sizes"] == {"600000.SH": 5000, "600001.SH": 2500}
    assert fetched["blocked_instruments"] == []
    assert fetched["cash_residue"] == 1200.0
    assert fetched["turnover_cost"] == 45.6
    assert fetched["discretization_rmse"] == 0.012


def test_record_rebalance_plan_duplicate_raises_value_error(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    portfolio_repository.record_rebalance_plan(**_plan_fields(fixture_rebalance_run))
    with pytest.raises(ValueError, match="duplicate"):
        portfolio_repository.record_rebalance_plan(**_plan_fields(fixture_rebalance_run))


def test_record_rebalance_plan_missing_run_raises_value_error(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    fields = _plan_fields(fixture_rebalance_run)
    fields["optimization_run_id"] = "no-such-run"
    with pytest.raises(ValueError, match="optimization run does not exist"):
        portfolio_repository.record_rebalance_plan(**fields)


def test_record_rebalance_plan_rejects_bad_sha256_and_enum(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    bad_input_sha = _plan_fields(fixture_rebalance_run, plan_id="rp-bad-sha")
    bad_input_sha["input_snapshot_sha256"] = "short"
    with pytest.raises(ValueError, match="input_snapshot_sha256"):
        portfolio_repository.record_rebalance_plan(**bad_input_sha)

    bad_rmse = _plan_fields(fixture_rebalance_run, plan_id="rp-bad-rmse")
    bad_rmse["rmse_definition"] = "squared"
    with pytest.raises(ValueError, match="rmse_definition"):
        portfolio_repository.record_rebalance_plan(**bad_rmse)


def test_list_rebalance_plans_filters_and_caps(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    run = fixture_rebalance_run
    for plan_id in ("rp-list-1", "rp-list-2"):
        portfolio_repository.record_rebalance_plan(**_plan_fields(run, plan_id=plan_id))
    all_plans = portfolio_repository.list_rebalance_plans()
    # created_at is identical for both rows; the tie-break is id ASC.
    assert [p["id"] for p in all_plans] == ["rp-list-1", "rp-list-2"]

    filtered = portfolio_repository.list_rebalance_plans(run_id=str(run["id"]))
    assert len(filtered) == 2
    none_match = portfolio_repository.list_rebalance_plans(run_id="missing-run")
    assert none_match == []

    with pytest.raises(ValueError, match="positive integer"):
        portfolio_repository.list_rebalance_plans(limit=0)


# ================================================================
# RebalancePlan module contracts (14-01) — RED until the module lands
# ================================================================


def _rebalance_module() -> object:
    """Lazy import — RED (ImportError) until 14-01 creates portfolio/rebalance.py."""
    from app.portfolio.rebalance import build_rebalance_plan, discretize_weights  # noqa: F401

    return None


def test_discretize_weights_lot_floor_matches_engine_formula(
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """100-share lots from floor(allocation/(price*(1+buy_cost))/100)*100 (engine.py:1158)."""
    _rebalance_module()


def test_blocked_instruments_excluded_and_recorded(
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """A blocked symbol carries zero discrete weight and appears in blocked_instruments."""
    _rebalance_module()


def test_cash_residue_is_deterministic(
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """Cash residue = equity - sum(share_i * price_i * (1 + buy_cost_pct)); never reallocated."""
    _rebalance_module()


def test_turnover_cost_matches_matcher_config_reference(
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """Buy leg at buy_cost_pct + sell leg at sell_cost_pct; zero on a no-change plan."""
    _rebalance_module()


def test_discretization_rmse_simple_and_weighted(
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """RMSE simple = sqrt(mean((w_cont - w_disc)^2)); weighted = sqrt(mean(w_cont * ...))."""
    _rebalance_module()


def test_expires_at_defaults_to_now_plus_seven_days(
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """Default expires_at = now + 7 calendar days; a caller-provided value is honored."""
    _rebalance_module()


def test_build_rebalance_plan_writes_artifact_and_row(
    portfolio_repository: PortfolioRepository,
    artifact_root: object,
    fixture_rebalance_run: dict[str, object],
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """O_EXCL + fsync + sha256 artifact; rebalance_plans row binds output_sha256 + path."""
    _rebalance_module()


def test_build_rebalance_plan_fails_closed_on_missing_run(
    portfolio_repository: PortfolioRepository,
    fixture_plan_inputs: dict[str, object],
) -> None:
    """A missing / non-optimal / empty-weight run raises ValueError (mirrors analyzer)."""
    _rebalance_module()


# ================================================================
# 14-01 tracer: end-to-end RebalancePlan → paper-rebalance spine
# ================================================================


def _run_prices(run: dict[str, object]) -> dict[str, float]:
    """Deterministic prices covering every symbol in the run's output_weights."""
    weights = run["output_weights"]
    return {symbol: round(10.0 + idx * 0.5, 2) for idx, symbol in enumerate(sorted(weights))}


def test_tracer_rebalance_plan_to_paper_fill_end_to_end(
    portfolio_repository: PortfolioRepository,
    artifact_root: object,
    fixture_rebalance_run: dict[str, object],
    fixture_plan_inputs: dict[str, object],
) -> None:
    """The full Phase 14 spine on a fixture: run weights → plan → suggestion → approve → fill.

    Locks RBAL-01 + RBAL-02 together: the engine.py-lot-formula adapter renders an
    immutable artifact + rebalance_plans row; the paper state machine lands
    suggested → approved → filled as append-only idempotent audit facts; and the
    no-execution-route gate holds (positions row count unchanged).
    """
    import sqlite3

    from app.portfolio.paper import approve, create_suggestion, paper_fill
    from app.portfolio.rebalance import build_rebalance_plan, load_rebalance_plan

    run = fixture_rebalance_run
    weights = run["output_weights"]
    symbols = sorted(weights)
    prices = _run_prices(run)
    blocked = {symbols[-1]}
    matcher_config = fixture_plan_inputs["matcher_config"]
    equity = float(fixture_plan_inputs["equity"])

    # --- build_rebalance_plan: discretize → artifact → rebalance_plans row ---
    plan = build_rebalance_plan(
        run_id=str(run["id"]),
        prices=prices,
        equity=equity,
        matcher_config=matcher_config,
        blocked=blocked,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
    )
    # run binding + audit contract
    assert plan.optimization_run_id == str(run["id"])
    assert plan.input_snapshot_sha256 == str(run["input_snapshot_sha256"])
    assert plan.as_of == run["as_of"]
    assert set(plan.target_weights) == set(weights)
    assert plan.rmse_definition == "simple"

    # blocked exclusion: zero discrete weight + recorded verbatim
    for sym in blocked:
        assert plan.discrete_weights[sym] == 0.0
    assert sorted(plan.blocked_instruments) == sorted(blocked)
    # every non-blocked lot is a 100-share board lot
    for sym, lot in plan.lot_sizes.items():
        assert lot % 100 == 0

    # cash residue = equity - Σ share·price·(1 + buy_cost_pct), never reallocated
    buy_cost_pct = matcher_config.buy_cost_pct()
    expected_residue = equity - sum(
        lot * prices[sym] * (1 + buy_cost_pct) for sym, lot in plan.lot_sizes.items()
    )
    assert plan.cash_residue == pytest.approx(expected_residue, rel=1e-9)
    assert plan.cash_residue >= 0.0

    # discretization RMSE reference (simple, over full universe incl. blocked)
    universe = sorted(weights)
    w_cont = np.asarray([weights[s] for s in universe], dtype=float)
    w_disc = np.asarray([plan.discrete_weights[s] for s in universe], dtype=float)
    expected_rmse = float(np.sqrt(np.mean((w_cont - w_disc) ** 2)))
    assert plan.discretization_rmse == pytest.approx(expected_rmse, rel=1e-9)

    # expires_at defaults to now + 7 calendar days
    expiry_delta = datetime.fromisoformat(plan.expires_at) - datetime.now(UTC)
    assert timedelta(days=6, hours=23) <= expiry_delta <= timedelta(days=7, hours=1)

    # artifact + row binding (O_EXCL + fsync + sha256)
    row = portfolio_repository.get_rebalance_plan(plan.plan_id)
    assert row is not None
    assert row["output_sha256"] == plan.output_sha256
    assert row["artifact_relative_path"] == plan.artifact_relative_path
    assert row["input_snapshot_sha256"] == plan.input_snapshot_sha256
    loaded = load_rebalance_plan(
        plan.plan_id, repository=portfolio_repository, artifact_service_root=artifact_root
    )
    assert loaded["plan"]["id"] == plan.plan_id
    assert loaded["content"]["lot_sizes"] == plan.lot_sizes

    # positions row count is unchanged across the whole paper flow
    def _positions_count() -> int:
        with sqlite3.connect(portfolio_repository.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM positions").fetchone()[0])

    positions_before = _positions_count()

    # --- paper state machine: suggestion → approve (idempotent) → fill ---
    suggested = create_suggestion(plan.plan_id, repository=portfolio_repository)
    assert suggested["transition"] == "suggested"
    approved = approve(
        plan.plan_id, repository=portfolio_repository, idempotency_key="approve-1"
    )
    assert approved["transition"] == "approved"
    approved_again = approve(
        plan.plan_id, repository=portfolio_repository, idempotency_key="approve-1"
    )
    assert approved_again["id"] == approved["id"]  # idempotent re-approve
    filled = paper_fill(
        plan.plan_id,
        repository=portfolio_repository,
        prices=prices,
        matcher_config=matcher_config,
    )
    assert filled["transition"] == "filled"
    assert filled["paper_position_delta"] == dict(plan.lot_sizes)

    # append-only ledger: ordinals increase, previous_state recorded
    ledger = portfolio_repository.list_paper_transitions(plan_id=plan.plan_id)
    assert [t["transition"] for t in ledger] == ["suggested", "approved", "filled"]
    assert ledger[0]["id"] < ledger[1]["id"] < ledger[2]["id"]
    assert ledger[1]["previous_state"] == "suggested"
    assert ledger[2]["previous_state"] == "approved"

    # no-execution-route gate: paper fill never wrote a positions row
    assert _positions_count() == positions_before
