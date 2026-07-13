"""RED contracts for immutable attributed viewpoints and frozen calibration."""
from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


class FixedMarketSnapshot:
    """Bounded governed-price fixture; no provider or current-price access."""

    def __init__(self, *, prices: dict[tuple[str, int], float], benchmarks: dict[tuple[str, int], float]):
        self.prices = prices
        self.benchmarks = benchmarks

    def price_at_window(self, instrument: str, trading_days: int) -> float | None:
        return self.prices.get((instrument, trading_days))

    def benchmark_at_window(self, benchmark: str, trading_days: int) -> float | None:
        return self.benchmarks.get((benchmark, trading_days))


class FixedGovernedEvaluation:
    def evaluate_viewpoint(self, _version: dict[str, object]) -> dict[str, object]:
        return {
            "status": "evaluated",
            "instrument_start": 100.0,
            "instrument_end": 120.0,
            "benchmark_start": 100.0,
            "benchmark_end": 110.0,
            "coverage_start": date(2026, 1, 2),
            "coverage_end": date(2026, 3, 31),
        }


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
        "published_at": datetime(2026, 1, 2, tzinfo=UTC),
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


def test_policy_facts_reuse_only_identical_content_fingerprints(tmp_path):
    repository, _viewpoint_service = _service(tmp_path)

    original = repository.record_policy_revision(
        revision="advanced_policy_v1", fingerprint="a" * 64, snapshot={"quota_per_window": 5}
    )
    changed = repository.record_policy_revision(
        revision="advanced_policy_v1", fingerprint="b" * 64, snapshot={"quota_per_window": 10}
    )
    reused = repository.record_policy_revision(
        revision="advanced_policy_v1", fingerprint="b" * 64, snapshot={"quota_per_window": 10}
    )

    assert changed["id"] != original["id"]
    assert reused["id"] == changed["id"]
    assert reused["fingerprint"] == "b" * 64


def test_viewpoint_versions_link_to_their_exact_policy_fingerprint(tmp_path):
    from app.advanced.policy import AdvancedPolicy
    from app.advanced.viewpoints import ViewpointService

    repository, default_service = _service(tmp_path)
    original = _create(default_service)
    changed_policy = AdvancedPolicy.bootstrap(
        {
            "version": "advanced_policy_v1",
            "source_profiles": {"operator-research-v1": {"market_scopes": ["CN-A"]}},
            "benchmark_defaults": {"stock": "000300.SH", "etf": "000300.SH", "index": "000001.SH"},
            "benchmark_overrides": ["000300.SH", "000905.SH", "000852.SH"],
            "agent_allowlist": {"research_draft": ["CN-A"], "experiment": ["CN-A"], "strategy_evaluation": ["CN-A"]},
            "rate_limits": {"research_draft": 11, "experiment": 5, "strategy_evaluation": 5},
        }
    )
    changed_service = ViewpointService(repository=repository, policy=changed_policy)
    changed = _create(changed_service, instrument="000001.SZ")
    reused = _create(changed_service, instrument="000333.SZ")

    with repository._connection() as connection:
        rows = connection.execute(
            """SELECT version.id, policy.id AS policy_id, policy.fingerprint
               FROM advanced_viewpoint_versions AS version
               JOIN advanced_policy_revisions AS policy ON policy.id = version.policy_revision_id
               WHERE version.id IN (?, ?, ?)""",
            (original["id"], changed["id"], reused["id"]),
        ).fetchall()
    linked = {row["id"]: dict(row) for row in rows}

    assert linked[original["id"]]["fingerprint"] == default_service.policy.fingerprint
    assert linked[changed["id"]]["fingerprint"] == changed_policy.fingerprint
    assert linked[changed["id"]]["policy_id"] != linked[original["id"]]["policy_id"]
    assert linked[reused["id"]]["policy_id"] == linked[changed["id"]]["policy_id"]


def test_policy_fingerprint_migration_preserves_existing_viewpoint_attribution(tmp_path):
    from app.operational.migrations import MIGRATIONS, migrate_operational_db

    database = tmp_path / "operational.db"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    for migration in MIGRATIONS[:-1]:
        connection.executescript(migration)
    connection.execute(f"PRAGMA user_version = {len(MIGRATIONS) - 1}")
    connection.executescript(
        """
        INSERT INTO advanced_policy_revisions (id, revision, fingerprint, snapshot_json, created_at)
        VALUES ('policy-v1', 'advanced_policy_v1', 'a', '{}', '2026-01-01T00:00:00+00:00');
        INSERT INTO advanced_viewpoints (id, source_profile, market_scope, instrument, created_at)
        VALUES ('viewpoint-v1', 'operator-research-v1', 'CN-A', '600519.SH', '2026-01-01T00:00:00+00:00');
        INSERT INTO advanced_viewpoint_versions
        (id, viewpoint_id, version, policy_revision_id, asset_type, published_at, direction, rating, conclusion,
         target_low, target_high, horizon_days, confidence, revision_kind, correction_reason,
         evaluation_window_days, benchmark, metric, created_at)
        VALUES ('version-v1', 'viewpoint-v1', 1, 'policy-v1', 'stock', '2026-01-01T00:00:00+00:00', 'bullish', 'overweight', 'original',
                1500, 1650, 60, 'high', 'initial', NULL, 60, '000300.SH', 'relative_return', '2026-01-01T00:00:00+00:00');
        """
    )
    migrate_operational_db(connection)

    linked = connection.execute(
        """SELECT policy.id, policy.fingerprint
           FROM advanced_viewpoint_versions AS version
           JOIN advanced_policy_revisions AS policy ON policy.id = version.policy_revision_id
           WHERE version.id = 'version-v1'"""
    ).fetchone()
    connection.execute(
        """INSERT INTO advanced_policy_revisions (id, revision, fingerprint, snapshot_json, created_at)
           VALUES ('policy-v2', 'advanced_policy_v1', 'b', '{"quota_per_window":10}', '2026-01-02T00:00:00+00:00')"""
    )

    assert linked == ("policy-v1", "a")
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()

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
    with pytest.raises(ValueError, match=r"source profile|scope"):
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
    with _repository._connection() as connection:
        evaluation = connection.execute(
            "SELECT governed_input_fingerprint FROM advanced_viewpoint_evaluations WHERE viewpoint_version_id = ? AND status = 'evaluated'",
            (viewpoint["id"],),
        ).fetchone()
    assert evaluation is not None
    assert len(evaluation["governed_input_fingerprint"]) == 64


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


def test_governed_collaborator_records_real_returns_and_coverage_dates(tmp_path):
    _repository, service = _service(tmp_path)
    viewpoint = _create(service)

    outcome = service.evaluate_viewpoint(
        viewpoint_version_id=viewpoint["id"], market_snapshot=FixedGovernedEvaluation()
    )

    assert outcome == {
        "status": "evaluated",
        "window_days": 60,
        "benchmark": "000300.SH",
        "instrument_return": 0.2,
        "benchmark_return": 0.1,
        "relative_return": 0.1,
        "as_of": date(2026, 3, 31),
    }
    assert service.list_versions(viewpoint["viewpoint_id"])[0]["evaluation"] == {
        "status": "evaluated",
        "reason": None,
        "relative_return": 0.1,
        "coverage_start": "2026-01-02",
        "coverage_end": "2026-03-31",
        "window_days": 60,
        "benchmark": "000300.SH",
    }


def test_calibration_projects_low_medium_high_buckets_with_coverage_and_insufficient_state(tmp_path):
    _repository, service = _service(tmp_path)
    outcomes = [
        ("low", 0.01, date(2026, 1, 2)),
        ("medium", -0.02, date(2026, 2, 2)),
        ("high", 0.05, date(2026, 3, 2)),
        ("high", 0.03, date(2026, 4, 2)),
    ]
    for confidence, relative_return, published_at in outcomes:
        viewpoint = _create(service, confidence=confidence, published_at=datetime.combine(published_at, datetime.min.time(), tzinfo=UTC))
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


class _ViewpointApiService:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.revisions: list[dict[str, object]] = []
        self.corrections: list[dict[str, object]] = []
        self.evaluations: list[dict[str, object]] = []

    def create_viewpoint(self, **payload: object) -> dict[str, object]:
        self.created.append(payload)
        return {
            "id": "version-owned",
            "viewpoint_id": "viewpoint-owned",
            "version": 1,
            "source_profile": "operator-research-v1",
            "instrument": str(payload["instrument"]),
            "published_at": "2026-01-02T00:00:00+00:00",
            "confidence": "high",
        }

    def list_versions(self, viewpoint_id: str) -> list[dict[str, object]]:
        if viewpoint_id == "viewpoint-owned":
            return [{
                "id": "version-owned",
                "viewpoint_id": viewpoint_id,
                "version": 1,
                "instrument": "600519.SH",
                "source_profile": "operator-research-v1",
                "published_at": "2026-01-02T00:00:00+00:00",
                "confidence": "high",
            }]
        return [{"id": "version-other", "viewpoint_id": viewpoint_id, "instrument": "000001.SZ"}]

    def list_for_instrument(self, instrument: str) -> list[dict[str, object]]:
        return self.list_versions("viewpoint-owned" if instrument == "600519.SH" else "viewpoint-other")

    def get_viewpoint_version(self, viewpoint_version_id: str) -> dict[str, object] | None:
        return self.list_versions("viewpoint-owned")[0] if viewpoint_version_id == "version-owned" else None

    def revise_viewpoint(self, *, viewpoint_id: str, **changes: object) -> dict[str, object]:
        self.revisions.append({"viewpoint_id": viewpoint_id, **changes})
        return {**self.list_versions(viewpoint_id)[0], "version": 2, "revision_kind": "material_stance_change"}

    def correct_viewpoint(self, *, viewpoint_id: str, correction_reason: str, **changes: object) -> dict[str, object]:
        self.corrections.append({"viewpoint_id": viewpoint_id, "correction_reason": correction_reason, **changes})
        return {**self.list_versions(viewpoint_id)[0], "version": 3, "revision_kind": "correction", "correction_reason": correction_reason}

    def evaluate_viewpoint(self, *, viewpoint_version_id: str, market_snapshot: object) -> dict[str, object]:
        self.evaluations.append({"viewpoint_version_id": viewpoint_version_id, "market_snapshot": market_snapshot})
        return {**self.list_versions("viewpoint-owned")[0], "evaluation": {"status": "unevaluable", "reason": "missing_benchmark"}}

    def calibration(self, *, source_profile: str) -> dict[str, object]:
        assert source_profile == "operator-research-v1"
        return {"low": {"status": "insufficient_sample"}}


def test_viewpoint_api_resolves_persisted_instrument_before_safe_projection_and_rejects_mutation_authority():
    from app.advanced import api as advanced_api

    service = _ViewpointApiService()
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.viewpoint_service = service
    app.state.viewpoint_market_snapshot = object()
    app.state.resolve_advanced_subject_scope = lambda _request: advanced_api.AdvancedSubjectScope(
        frozenset({("instrument", "600519.SH")})
    )

    @app.middleware("http")
    async def authenticated(request: Request, call_next):
        request.state.reviewer_principal = "server-researcher"
        return await call_next(request)

    client = TestClient(app)
    payload = {
        "source_profile": "operator-research-v1",
        "market_scope": "CN-A",
        "asset_type": "stock",
        "instrument": "600519.SH",
        "published_at": "2026-01-02T00:00:00+00:00",
        "direction": "bullish",
        "conclusion": "受控研究观点",
        "rating": "overweight",
        "target_range": [1500, 1600],
        "horizon_days": 60,
        "confidence": "high",
        "evidence": [{"id": "filing-1"}],
        "evaluation_window_days": 60,
    }

    assert client.post("/api/advanced/viewpoints", json={**payload, "principal": "browser"}).status_code == 422
    created = client.post("/api/advanced/viewpoints", json=payload)
    assert created.status_code == 200
    assert service.created[0]["instrument"] == "600519.SH"
    assert "principal" not in service.created[0]
    assert client.get("/api/advanced/viewpoints/viewpoint-other/versions").status_code == 404
    allowed = client.get("/api/advanced/viewpoints/viewpoint-owned/versions")
    assert allowed.status_code == 200
    version = allowed.json()["versions"][0]
    assert version["id"] == "version-owned"
    assert version["viewpoint_id"] == "viewpoint-owned"
    assert version["instrument"] == "600519.SH"
    assert version["status"] == "recorded"
    assert version["evaluation"] is None
    assert version["audit_reference"] is None
    assert not {"policy", "token", "principal", "source_code", "diagnostics"}.intersection(version)
    assert client.patch("/api/advanced/viewpoints/viewpoint-owned", json={}).status_code == 404
    assert client.delete("/api/advanced/viewpoints/viewpoint-owned").status_code == 404
    listed = client.get("/api/advanced/viewpoints?instrument=600519.SH")
    assert listed.status_code == 200
    assert listed.json()["viewpoints"][0]["instrument"] == "600519.SH"
    assert client.get("/api/advanced/viewpoints?instrument=000001.SZ").status_code == 404

    revision = client.post(
        "/api/advanced/viewpoints/viewpoint-owned/revisions",
        json={"direction": "bearish"},
    )
    assert revision.status_code == 200
    assert service.revisions == [{"viewpoint_id": "viewpoint-owned", "direction": "bearish"}]
    assert client.post(
        "/api/advanced/viewpoints/viewpoint-owned/revisions",
        json={"principal": "browser"},
    ).status_code == 422

    correction = client.post(
        "/api/advanced/viewpoints/viewpoint-owned/corrections",
        json={"correction_reason": "更正结论中的单位", "conclusion": "修正后的受控研究观点"},
    )
    assert correction.status_code == 200
    assert service.corrections == [{
        "viewpoint_id": "viewpoint-owned",
        "correction_reason": "更正结论中的单位",
        "conclusion": "修正后的受控研究观点",
    }]

    evaluation = client.post("/api/advanced/viewpoints/versions/version-owned/evaluate", json={})
    assert evaluation.status_code == 200
    assert service.evaluations == [{"viewpoint_version_id": "version-owned", "market_snapshot": app.state.viewpoint_market_snapshot}]
    assert client.post(
        "/api/advanced/viewpoints/versions/version-owned/evaluate",
        json={"benchmark": "SPX"},
    ).status_code == 422
