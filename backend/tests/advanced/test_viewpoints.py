"""RED contracts for immutable attributed viewpoints and frozen calibration."""
from __future__ import annotations

from datetime import date, datetime, timezone
import sqlite3

import pytest


class FixedMarketSnapshot:
    """Bounded governed-price fixture; no provider or current-price access."""

    def __init__(self, *, prices: dict[tuple[str, int], float], benchmarks: dict[tuple[str, int], float]):
        self.prices = prices
        self.benchmarks = benchmarks

    def price_at_window(self, instrument: str, trading_days: int) -> float | None:
        return self.prices.get((instrument, trading_days))

    def benchmark_at_window(self, benchmark: str, trading_days: int) -> float | None:
        return self.benchmarks.get((benchmark, trading_days))


def _service(tmp_path):
    from app.advanced.policy import AdvancedPolicy
    from app.advanced.repository import AdvancedRepository
    from app.advanced.viewpoints import ViewpointService

    repository = AdvancedRepository(tmp_path / "operational.db")
    repository.migrate()
    policy = AdvancedPolicy.bootstrap("advanced_policy_v1")
    return repository, ViewpointService(repository=repository, policy=policy)


def _create(service, **overrides):
    payload = {
        "source_profile": "operator-research-v1",
        "market_scope": "CN-A",
        "asset_type": "stock",
        "instrument": "600519.SH",
        "published_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "direction": "bullish",
        "conclusion": "盈利增长支持中期研究观点",
        "rating": "overweight",
        "target_range": [1500.0, 1650.0],
        "horizon_days": 60,
        "confidence": "high",
        "evidence": [{"id": "filing-2025q4", "published_at": "2026-01-01T00:00:00+00:00"}],
        "evaluation_window_days": 60,
    }
    payload.update(overrides)
    return service.create_viewpoint(**payload)


def test_viewpoint_versions_evidence_and_frozen_evaluation_plans_are_append_only(tmp_path):
    repository, service = _service(tmp_path)
    first = _create(service)
    correction = service.correct_viewpoint(
        viewpoint_id=first["viewpoint_id"],
        correction_reason="更正目标区间的单位换算",
        target_range=[1520.0, 1670.0],
    )

    versions = service.list_versions(first["viewpoint_id"])
    assert [version["version"] for version in versions] == [2, 1]
    assert correction["revision_kind"] == "correction"
    assert correction["correction_reason"] == "更正目标区间的单位换算"
    assert versions[1]["evidence"] == [{"id": "filing-2025q4", "published_at": "2026-01-01T00:00:00+00:00"}]
    assert versions[1]["evaluation_plan"] == {
        "window_days": 60,
        "benchmark": "000300.SH",
        "metric": "relative_return",
    }

    with sqlite3.connect(repository.database_path) as connection:
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute(
                "UPDATE advanced_viewpoint_versions SET confidence = 'low' WHERE id = ?",
                (first["id"],),
            )
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("DELETE FROM advanced_viewpoint_evidence WHERE viewpoint_version_id = ?", (first["id"],))
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("DELETE FROM advanced_viewpoint_evaluations WHERE viewpoint_version_id = ?", (first["id"],))


def test_structured_stance_deltas_classify_material_changes_but_keep_minor_revisions_visible(tmp_path):
    _repository, service = _service(tmp_path)
    first = _create(service)
    wording = service.revise_viewpoint(
        viewpoint_id=first["viewpoint_id"],
        conclusion="盈利增长继续支持中期研究判断",
        evidence=[{"id": "filing-2025q4"}, {"id": "call-notes"}],
    )
    material = service.revise_viewpoint(
        viewpoint_id=first["viewpoint_id"],
        direction="bearish",
        rating="underweight",
        target_range=[1200.0, 1300.0],
        horizon_days=20,
        confidence="low",
    )

    assert wording["revision_kind"] == "non_material_revision"
    assert wording["material_change"] is False
    assert wording["changed_fields"] == ["conclusion", "evidence"]
    assert material["revision_kind"] == "material_stance_change"
    assert material["material_change"] is True
    assert set(material["changed_fields"]) == {
        "direction",
        "rating",
        "target_range",
        "horizon_days",
        "confidence",
    }


@pytest.mark.parametrize(
    ("asset_type", "benchmark", "expected"),
    [
        ("stock", None, "000300.SH"),
        ("etf", None, "000300.SH"),
        ("index", None, "000001.SH"),
        ("stock", "000905.SH", "000905.SH"),
        ("stock", "000852.SH", "000852.SH"),
    ],
)
def test_server_policy_freezes_only_allowed_cn_a_benchmarks(tmp_path, asset_type, benchmark, expected):
    _repository, service = _service(tmp_path)
    viewpoint = _create(service, asset_type=asset_type, benchmark=benchmark)

    assert viewpoint["policy_version"] == "advanced_policy_v1"
    assert viewpoint["source_profile"] == "operator-research-v1"
    assert viewpoint["market_scope"] == "CN-A"
    assert viewpoint["evaluation_plan"]["benchmark"] == expected


@pytest.mark.parametrize("benchmark", ["000001.SH", "399001.SZ", "SPX"])
def test_server_policy_rejects_unsupported_profile_scope_and_benchmark_overrides(tmp_path, benchmark):
    _repository, service = _service(tmp_path)

    with pytest.raises(ValueError, match="benchmark"):
        _create(service, benchmark=benchmark)
    with pytest.raises(ValueError, match="source profile|scope"):
        _create(service, source_profile="browser-controlled", market_scope="US")


@pytest.mark.parametrize("window_days", [20, 60, 120])
def test_evaluation_uses_the_frozen_trading_day_plan_not_a_current_price(tmp_path, window_days):
    _repository, service = _service(tmp_path)
    viewpoint = _create(service, evaluation_window_days=window_days)
    snapshot = FixedMarketSnapshot(
        prices={("600519.SH", window_days): 110.0},
        benchmarks={("000300.SH", window_days): 105.0},
    )

    outcome = service.evaluate_viewpoint(viewpoint_version_id=viewpoint["id"], market_snapshot=snapshot)

    assert outcome == {
        "status": "evaluated",
        "window_days": window_days,
        "benchmark": "000300.SH",
        "instrument_return": 0.1,
        "benchmark_return": 0.05,
        "relative_return": 0.05,
        "as_of": date(2026, 1, 2),
    }


@pytest.mark.parametrize(
    ("prices", "benchmarks", "reason"),
    [
        ({}, {("000300.SH", 60): 105.0}, "missing_price"),
        ({("600519.SH", 60): 110.0}, {}, "missing_benchmark"),
    ],
)
def test_missing_market_inputs_persist_explicit_unevaluable_outcomes(tmp_path, prices, benchmarks, reason):
    _repository, service = _service(tmp_path)
    viewpoint = _create(service)

    outcome = service.evaluate_viewpoint(
        viewpoint_version_id=viewpoint["id"],
        market_snapshot=FixedMarketSnapshot(prices=prices, benchmarks=benchmarks),
    )

    assert outcome["status"] == "unevaluable"
    assert outcome["reason"] == reason
    assert outcome["relative_return"] is None
    assert service.calibration(source_profile="operator-research-v1")["excluded_unevaluable"] == 0


def test_calibration_projects_low_medium_high_buckets_with_coverage_and_insufficient_state(tmp_path):
    _repository, service = _service(tmp_path)
    outcomes = [
        ("low", 0.01, date(2026, 1, 2)),
        ("medium", -0.02, date(2026, 2, 2)),
        ("high", 0.05, date(2026, 3, 2)),
        ("high", 0.03, date(2026, 4, 2)),
    ]
    for confidence, relative_return, published_at in outcomes:
        viewpoint = _create(service, confidence=confidence, published_at=datetime.combine(published_at, datetime.min.time(), tzinfo=timezone.utc))
        service.record_evaluation(
            viewpoint_version_id=viewpoint["id"],
            status="evaluated",
            relative_return=relative_return,
            coverage_start=published_at,
            coverage_end=published_at,
        )

    calibration = service.calibration(source_profile="operator-research-v1", minimum_sample_count=2)

    assert calibration["low"] == {
        "status": "insufficient_sample",
        "sample_count": 1,
        "hit_rate": 1.0,
        "mean_relative_return": 0.01,
        "coverage_start": "2026-01-02",
        "coverage_end": "2026-01-02",
    }
    assert calibration["medium"]["status"] == "insufficient_sample"
    assert calibration["high"] == {
        "status": "calibrated",
        "sample_count": 2,
        "hit_rate": 1.0,
        "mean_relative_return": 0.04,
        "coverage_start": "2026-03-02",
        "coverage_end": "2026-04-02",
    }
