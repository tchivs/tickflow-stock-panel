"""RED scaffold for PortfolioRepository — append-only run records (PFOL-04).

Wave 0 (11-02) scaffold: the migrate() seam exists; the append-only
record/get/list methods land in 11-01, so the method-level tests below are RED
until then (AttributeError on the missing methods).
"""
from __future__ import annotations

import re
import sqlite3

import pytest

from app.portfolio.repository import PortfolioRepository

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _valid_run(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "id": "a" * 32,
        "objective": "min_volatility",
        "as_of": "2026-08-01",
        "universe": "cn-a-share",
        "model_id": None,
        "composite_snapshot_id": None,
        "input_snapshot_sha256": "1" * 64,
        "expected_return_method": "none",
        "risk_model": "sample_covariance_v1",
        "risk_model_json": {"psd_repair": {"method": "none"}},
        "constraint_stack_json": {"cap": 0.1, "min_cash": 0.05},
        "solver_name": "CLARABEL",
        "solver_version": "0.11.1",
        "solver_options_json": {},
        "problem_status": "optimal",
        "failure_reason": None,
        "output_weights_json": {"600000.SH": 0.5},
        "output_sha256": "2" * 64,
        "weights_artifact_relative_path": "research_artifacts/run/weights.json",
        "baseline_weights_json": {"600000.SH": 0.5},
        "created_at": "2026-08-01T00:00:00Z",
    }
    fields.update(overrides)
    return fields


def test_record_and_get_round_trip_json_columns(portfolio_repository: PortfolioRepository) -> None:
    """PFOL-04: an inserted run round-trips with JSON columns unwrapped."""
    inserted = portfolio_repository.record_optimization_run(**_valid_run())
    assert inserted["id"] == "a" * 32
    fetched = portfolio_repository.get_optimization_run("a" * 32)
    assert fetched is not None
    assert fetched["objective"] == "min_volatility"
    assert fetched["risk_model_detail"] == {"psd_repair": {"method": "none"}}
    assert fetched["constraint_stack"] == {"cap": 0.1, "min_cash": 0.05}
    assert fetched["solver_options"] == {}
    assert fetched["output_weights"] == {"600000.SH": 0.5}


def test_update_and_delete_are_blocked(portfolio_repository: PortfolioRepository) -> None:
    """PFOL-04: immutability triggers reject UPDATE and DELETE."""
    portfolio_repository.record_optimization_run(**_valid_run())
    with portfolio_repository._connection() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE portfolio_optimization_runs SET solver_name = 'OSQP' WHERE id = ?",
                ("a" * 32,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM portfolio_optimization_runs WHERE id = ?",
                ("a" * 32,),
            )


def test_failed_run_requires_failure_reason(portfolio_repository: PortfolioRepository) -> None:
    """PFOL-04: a failed run without a reason is rejected by the repository."""
    with pytest.raises(ValueError):
        portfolio_repository.record_optimization_run(**_valid_run(problem_status="failed"))


def test_non_hex_sha256_rejected(portfolio_repository: PortfolioRepository) -> None:
    with pytest.raises(ValueError):
        portfolio_repository.record_optimization_run(
            **_valid_run(input_snapshot_sha256="not-hex")
        )


def test_list_filters_by_objective_and_as_of(portfolio_repository: PortfolioRepository) -> None:
    """PFOL-04: list filters on objective/as_of and orders by created_at, id."""
    portfolio_repository.record_optimization_run(
        **_valid_run(id="b" * 32, objective="min_volatility", as_of="2026-08-01")
    )
    runs = portfolio_repository.list_optimization_runs(
        objective="min_volatility", as_of="2026-08-01"
    )
    assert [r["id"] for r in runs] == ["b" * 32]


def test_list_caps_at_limit(portfolio_repository: PortfolioRepository) -> None:
    """PFOL-04 (11-05): list respects the limit cap for the Phase 15 API."""
    for index in range(5):
        # created_at 秒级区分, 使 created_at, id 排序唯一 (00:00:00Z 会并列回退到 id)。
        portfolio_repository.record_optimization_run(
            **_valid_run(
                id=f"{index:032d}",
                created_at=f"2026-08-0{index + 1}T00:00:00Z",
            )
        )
    runs = portfolio_repository.list_optimization_runs(limit=2)
    assert len(runs) == 2
    # 升序 created_at, id: 前两行是 created_at 最早的 (id 为 0-padded 序号)。
    assert [r["id"] for r in runs] == [f"{0:032d}", f"{1:032d}"]
    # limit 为 0 / 负数 fail closed。
    with pytest.raises(ValueError, match="limit"):
        portfolio_repository.list_optimization_runs(limit=0)
    with pytest.raises(ValueError, match="limit"):
        portfolio_repository.list_optimization_runs(limit=-1)


def test_list_attribution_evidence_filters_by_risk_model_and_caps_limit(
    portfolio_repository: PortfolioRepository,
) -> None:
    """RSK-01 (12-05): evidence list filters on run_id / type / risk_model and
    fails closed on a non-positive limit (Phase 15 API surface)."""
    run_id = "a" * 32
    portfolio_repository.record_optimization_run(**_valid_run(id=run_id))
    models = [
        "sample_covariance_v1",
        "semi_covariance_v1",
        "ewma_covariance_v1",
        "ledoit_wolf_v1",
    ]
    for index, risk_model in enumerate(models):
        portfolio_repository.record_attribution_evidence(
            id=f"{index:032d}",
            attribution_type="exposure_contribution",
            run_id=run_id,
            risk_model=risk_model,
            as_of="2026-08-01",
            output_sha256="0" * 64,
            artifact_relative_path=f"research_artifacts/{run_id}/attribution/x-{index}.json",
            reconciliation_json={"portfolio_variance": 0.01},
            created_at=f"2026-08-0{index + 1}T00:00:00Z",
        )
    semi = portfolio_repository.list_attribution_evidence(risk_model="semi_covariance_v1")
    assert [row["id"] for row in semi] == [f"{1:032d}"]
    assert all(row["risk_model"] == "semi_covariance_v1" for row in semi)
    # Combined run_id + attribution_type + risk_model equality filter.
    combined = portfolio_repository.list_attribution_evidence(
        run_id=run_id, attribution_type="exposure_contribution", risk_model="ewma_covariance_v1"
    )
    assert [row["id"] for row in combined] == [f"{2:032d}"]
    # Unknown risk_model fails closed (validated against the 4-model enum).
    with pytest.raises(ValueError, match="risk_model"):
        portfolio_repository.list_attribution_evidence(risk_model="black_litterman_v1")
    # limit=0 / negative fail closed, mirroring list_optimization_runs.
    with pytest.raises(ValueError, match="limit"):
        portfolio_repository.list_attribution_evidence(limit=0)
    with pytest.raises(ValueError, match="limit"):
        portfolio_repository.list_attribution_evidence(limit=-1)
