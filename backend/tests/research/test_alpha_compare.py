"""Phase 50-02 — side-by-side compare projection + Tier-1 stress matrix.

Covers:
  * ``service.compare_candidates`` / ``projections.compare`` (50-02-01, SC3, AF-REQ-22)
  * ``service.stress_matrix`` / ``projections.stress_matrix`` (50-02-02, AF-REQ-20 Tier-1)

The compare projection exposes every requested candidate's configuration,
per-fold evidence, admission verdict + gate trail, artifact refs, and
diversity/redundancy outcome EQUALLY — there is NEVER an opaque aggregate
"winner score" (SC3): the researcher, not a hidden number, makes the call.

The Tier-1 stress matrix is a PURE ARITHMETIC re-projection of the frozen
evidence under declared fee/slippage/rebalance assumptions over the STORED
turnover — it recomputes no factor values, re-scores nothing through the
chain, and writes nothing to admission. Tier-2 axes (calendar-regime,
coverage, symbol-subset) are an explicit deferral and return a bounded 422.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import research_alpha
from app.research import projections
from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot
from app.research.run_service import ResearchRunService
from tests.research.conftest import DeterministicClock

_PRINCIPAL = "researcher@example.com"


# ---------------------------------------------------------------------
# Manifest / seeding helpers.
# ---------------------------------------------------------------------


def _sample_manifest(*, seed: int = 42, scoring: bool = True) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {"name": "cn-a-share", "asset_type": "stock", "membership_fingerprint": "c" * 64},
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {
            "train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10,
            "oos_size": 20, "horizon": 5,
        },
        "code_manifest": {"fingerprint": "d" * 64, "build_fingerprint": "e" * 64, "dependency_fingerprint": "f" * 64},
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": seed,
    }
    if scoring:
        manifest["scoring"] = {"rebalance": "daily", "n_groups": 5, "warmup_days": 10}
        manifest["costs"] = {"commission_pct": 0.0003, "stamp_tax_pct": 0.001, "slippage_bps": 5.0}
    return manifest


def _make_run(
    repo: ResearchRepository,
    clock: DeterministicClock,
    *,
    run_id: str = "run-cmp-0",
    idempotency_key: str = "idem-cmp-0000000001",
    principal: str = _PRINCIPAL,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = freeze_input_snapshot(
        manifest=manifest or _sample_manifest(), created_at=clock.now_iso(),
    )
    clock.advance()
    return repo.create_alpha_run(
        run_id=run_id, principal=principal, idempotency_key=idempotency_key,
        snapshot=snapshot, event_id="aevt-" + run_id,
    )


def _candidate_params(
    *, run_id: str, candidate_id: str, ordinal: int, digest: str | None = None,
    status: str = "admitted",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "attempt_ordinal": ordinal,
        "candidate_digest": digest or ("a" * 60 + f"{ordinal:04d}"),
        "canonical_expression": f"rank(close) + {ordinal}",
        "ast_signature": f"ast-{ordinal}",
        "shape_signature": f"shape-{ordinal}",
        "dsl_version": "factor-dsl-v1",
        "operation": "generate",
        "seed": 42,
        "step": ordinal,
        "status": status,
        "reason": {"note": f"candidate {ordinal}"},
    }


_DECLARED = {
    "panel": "p" * 64, "membership": "m" * 64, "source_field": "s" * 64,
    "warmup": "w" * 64, "missing_data": "d" * 64, "signal": "g" * 64,
}


def _seed_fold_evidence(
    repo: ResearchRepository, *, run_id: str, candidate_digest: str,
    fold_index: int = 0, is_oos: bool = False,
    stats: dict[str, Any] | None = None, declared: dict[str, str] | None = None,
) -> dict[str, Any]:
    return repo.record_alpha_fold_evidence(
        run_id=run_id, candidate_digest=candidate_digest,
        fold_index=fold_index, is_oos=is_oos, revision_id=f"rev-{candidate_digest[-4:]}",
        train_start="2020-01-01", train_end="2020-06-30",
        test_start="2020-07-01", test_end="2020-12-31",
        membership_fingerprint="a" * 64,
        declared_fingerprints=declared or dict(_DECLARED),
        stats=stats if stats is not None else {"coverage": 0.95, "mean_ic": 0.03},
    )


def _seed_compare_run(
    repo: ResearchRepository, clock: DeterministicClock, *, run_id: str = "run-cmp",
) -> tuple[str, list[str]]:
    """Seed one run with three candidates + fold evidence; return (run_id, candidate_ids)."""
    run = _make_run(repo, clock, run_id=run_id)
    candidate_ids = [f"cand-{i}" for i in (1, 2, 3)]
    for ordinal, cid in enumerate(candidate_ids, start=1):
        repo.append_candidate_attempt(
            **_candidate_params(run_id=run["id"], candidate_id=cid, ordinal=ordinal)
        )
        _seed_fold_evidence(
            repo, run_id=run["id"],
            candidate_digest="a" * 60 + f"{ordinal:04d}",
            fold_index=0, is_oos=False,
            stats={"coverage": 0.9 + 0.01 * ordinal, "mean_ic": 0.02 * ordinal},
        )
    return run["id"], candidate_ids


# ================================================================
# Task 50-02-01: service.compare_candidates + projections.compare
# ================================================================


class TestCompareCandidatesService:
    def test_full_evidence_side_by_side_no_winner(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_id, candidate_ids = _seed_compare_run(alpha_run_repository, deterministic_clock)
        service = ResearchRunService(alpha_run_repository)
        result = service.compare_candidates(
            run_id, principal=_PRINCIPAL, candidate_ids=candidate_ids,
        )
        assert result is not None
        assert result["run_id"] == run_id
        assert len(result["candidates"]) == 3
        # Every candidate carries config + fold evidence + verdict + artifacts + diversity.
        for entry in result["candidates"]:
            assert {"candidate_id", "config", "fold_evidence", "admission_verdict",
                    "gate_trail_digest", "artifact_refs", "diversity"} <= set(entry)
            cfg = entry["config"]
            assert {"canonical_expression", "seed", "step", "operation",
                    "candidate_digest", "attempt_ordinal", "dsl_version"} <= set(cfg)
            assert len(entry["fold_evidence"]) == 1
        # SC3 — NO opaque aggregate / winner / rank / score key anywhere.
        forbidden = {"winner", "rank", "score", "best", "ranking", "winner_score"}
        for entry in result["candidates"]:
            assert not (forbidden & set(entry))
            assert not (forbidden & set(entry["config"]))

    def test_missing_candidate_partial_not_500(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_id, candidate_ids = _seed_compare_run(alpha_run_repository, deterministic_clock)
        service = ResearchRunService(alpha_run_repository)
        # One unknown candidate id mixed in; present ones still compare.
        result = service.compare_candidates(
            run_id, principal=_PRINCIPAL,
            candidate_ids=[candidate_ids[0], "no-such-candidate"],
        )
        assert result is not None
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["candidate_id"] == candidate_ids[0]

    def test_cross_principal_returns_none(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_id, candidate_ids = _seed_compare_run(alpha_run_repository, deterministic_clock)
        service = ResearchRunService(alpha_run_repository)
        # Cross-principal: same None boundary as an unknown run (no 403 leak).
        assert service.compare_candidates(
            run_id, principal="attacker@example.com", candidate_ids=candidate_ids,
        ) is None
        assert service.compare_candidates(
            "run-nonexistent", principal=_PRINCIPAL, candidate_ids=candidate_ids,
        ) is None


class TestCompareProjection:
    def test_compare_exposes_every_candidate_equally(self) -> None:
        record = {
            "run_id": "run-x",
            "candidates": [
                {
                    "candidate_id": "c1", "candidate_digest": "a" * 64,
                    "config": {"canonical_expression": "rank(close)", "seed": 1,
                               "step": 0, "operation": "seed",
                               "candidate_digest": "a" * 64, "attempt_ordinal": 1,
                               "dsl_version": "factor-dsl-v1"},
                    "fold_evidence": [{"fold_index": 0, "is_oos": False, "stats": {"mean_ic": 0.03}}],
                    "admission_verdict": "admitted",
                    "gate_trail_digest": "d" * 64,
                    "policy_version": "admission-v1",
                    "artifact_refs": [{"artifact_id": "art-1"}],
                    "diversity": {"exact_structural_match": False, "shape_match": False},
                },
            ],
        }
        projected = projections.compare(record)
        assert projected["run_id"] == "run-x"
        assert len(projected["candidates"]) == 1
        c = projected["candidates"][0]
        assert c["admission_verdict"] == "admitted"
        assert c["gate_trail_digest"] == "d" * 64
        assert c["config"]["canonical_expression"] == "rank(close)"

    def test_compare_drops_unknown_keys_deny_by_default(self) -> None:
        record = {
            "run_id": "run-y",
            "candidates": [
                {
                    "candidate_id": "c1", "candidate_digest": "a" * 64,
                    "config": {"canonical_expression": "rank(close)", "seed": 1,
                               "step": 0, "operation": "seed",
                               "candidate_digest": "a" * 64, "attempt_ordinal": 1,
                               "dsl_version": "factor-dsl-v1"},
                    "fold_evidence": [],
                    "admission_verdict": None,
                    "gate_trail_digest": None,
                    "policy_version": None,
                    "artifact_refs": [],
                    "diversity": None,
                    "secret_internal": "should-not-leak",
                },
            ],
        }
        projected = projections.compare(record)
        assert "secret_internal" not in projected["candidates"][0]


# ---------------------------------------------------------------------
# API surface.
# ---------------------------------------------------------------------


@pytest.fixture
def compare_client(
    tmp_path: Path, deterministic_clock: DeterministicClock,
) -> TestClient:
    repository = ResearchRepository(
        tmp_path / "op.db", clock=deterministic_clock, artifact_root=tmp_path / "art",
    )
    repository.migrate()
    app = FastAPI()

    @app.middleware("http")
    async def inject_test_principal(request, call_next):
        principal = request.headers.get("X-Test-Principal")
        if principal:
            request.state.reviewer_principal = principal
        return await call_next(request)

    app.state.research_run_service = ResearchRunService(repository)
    app.state.research_repository = repository
    app.include_router(research_alpha.router)
    client = TestClient(app)
    client._repo = repository  # type: ignore[attr-defined]
    client._clock = deterministic_clock  # type: ignore[attr-defined]
    return client


class TestCompareEndpoint:
    def test_compare_returns_full_evidence_no_winner(self, compare_client: TestClient) -> None:
        repo: ResearchRepository = compare_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = compare_client._clock  # type: ignore[attr-defined]
        run_id, candidate_ids = _seed_compare_run(repo, clock)
        resp = compare_client.get(
            f"/api/research/alpha/runs/{run_id}/compare",
            params={"candidates": ",".join(candidate_ids)},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert len(body["candidates"]) == 3
        forbidden = {"winner", "rank", "score", "best"}
        for entry in body["candidates"]:
            assert not (forbidden & set(entry))
            assert entry["config"]["canonical_expression"].startswith("rank(close)")
            assert len(entry["fold_evidence"]) == 1

    def test_compare_missing_candidate_partial(self, compare_client: TestClient) -> None:
        repo: ResearchRepository = compare_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = compare_client._clock  # type: ignore[attr-defined]
        run_id, candidate_ids = _seed_compare_run(repo, clock, run_id="run-partial")
        resp = compare_client.get(
            f"/api/research/alpha/runs/{run_id}/compare",
            params={"candidates": f"{candidate_ids[0]},ghost"},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 200
        assert len(resp.json()["candidates"]) == 1

    def test_compare_unknown_run_404(self, compare_client: TestClient) -> None:
        resp = compare_client.get(
            "/api/research/alpha/runs/no-such-run/compare",
            params={"candidates": "a,b"},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 404

    def test_compare_cross_principal_404(self, compare_client: TestClient) -> None:
        repo: ResearchRepository = compare_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = compare_client._clock  # type: ignore[attr-defined]
        run_id, candidate_ids = _seed_compare_run(repo, clock, run_id="run-xp")
        resp = compare_client.get(
            f"/api/research/alpha/runs/{run_id}/compare",
            params={"candidates": ",".join(candidate_ids)},
            headers={"X-Test-Principal": "attacker@example.com"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] != "forbidden"


# ================================================================
# Task 50-02-02: Tier-1 stress matrix (pure arithmetic, no admission)
# ================================================================


def _frozen_costs() -> dict[str, float]:
    return {"commission_pct": 0.0003, "stamp_tax_pct": 0.001, "slippage_bps": 5.0}


def _expected_cost_rate(costs: dict[str, float]) -> float:
    # Mirrors evaluation._cost_rate EXACTLY (commission double-sided + stamp + slippage*2/1e4).
    return (
        float(costs.get("commission_pct", 0.0)) * 2.0
        + float(costs.get("stamp_tax_pct", 0.0))
        + float(costs.get("slippage_bps", 0.0)) * 2.0 / 1e4
    )


def _seed_stress_candidate(
    repo: ResearchRepository, clock: DeterministicClock, *,
    run_id: str = "run-str", total_turnover: float = 2.0, raw_ls: float = 0.5,
    candidate_id: str = "cand-str",
) -> tuple[str, str, dict[str, Any]]:
    manifest = _sample_manifest()
    run = _make_run(repo, clock, run_id=run_id, manifest=manifest)
    digest = "a" * 60 + "0007"
    repo.append_candidate_attempt(
        **_candidate_params(run_id=run["id"], candidate_id=candidate_id, ordinal=1, digest=digest)
    )
    costs = _frozen_costs()
    cost_rate = _expected_cost_rate(costs)
    cost_drag = total_turnover * cost_rate
    cost_diag = {
        "turnover_per_rebalance": [{"date": "2020-01-02", "turnover": total_turnover}],
        "total_turnover": total_turnover,
        "cost_rate": cost_rate,
        "cost_drag": cost_drag,
        "raw_long_short_return": raw_ls,
        "net_long_short_return": raw_ls - cost_drag,
    }
    _seed_fold_evidence(
        repo, run_id=run["id"], candidate_digest=digest, fold_index=0, is_oos=False,
        stats={"coverage": 0.95, "mean_ic": 0.03, "cost_diagnostics": cost_diag},
    )
    return run["id"], candidate_id, cost_diag


class TestStressMatrixService:
    def test_baseline_matches_frozen_cost_diagnostics(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_id, candidate_id, cost_diag = _seed_stress_candidate(
            alpha_run_repository, deterministic_clock,
        )
        service = ResearchRunService(alpha_run_repository)
        result = service.stress_matrix(
            run_id, principal=_PRINCIPAL, candidate_id=candidate_id, axes={},
        )
        assert result is not None
        baseline = result["baseline"]
        # Baseline row equals the frozen cost_diagnostics verbatim (zero recomputation).
        assert baseline["total_turnover"] == cost_diag["total_turnover"]
        assert baseline["cost_rate"] == pytest.approx(cost_diag["cost_rate"])
        assert baseline["cost_drag"] == pytest.approx(cost_diag["cost_drag"])
        assert baseline["net_long_short_return"] == pytest.approx(cost_diag["net_long_short_return"])

    def test_fee_slippage_arithmetic_matches_hand_computed(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_id, candidate_id, cost_diag = _seed_stress_candidate(
            alpha_run_repository, deterministic_clock,
        )
        service = ResearchRunService(alpha_run_repository)
        result = service.stress_matrix(
            run_id, principal=_PRINCIPAL, candidate_id=candidate_id,
            axes={"fee_bps": [10.0, 50.0], "slippage_bps": [0.0, 20.0]},
        )
        assert result is not None
        matrix = result["matrix"]
        total_turnover = cost_diag["total_turnover"]
        raw_ls = cost_diag["raw_long_short_return"]
        costs = _frozen_costs()
        # fee_bps axis: round-trip fee+tax in bps replaces (commission*2 + stamp).
        for value in (10.0, 50.0):
            alt_rate = value / 1e4 + costs["slippage_bps"] * 2.0 / 1e4
            row = next(r for r in matrix if r["axis"] == "fee_bps" and math.isclose(r["value"], value))
            assert row["cost_rate"] == pytest.approx(alt_rate)
            assert row["cost_drag"] == pytest.approx(total_turnover * alt_rate)
            assert row["net_long_short_return"] == pytest.approx(raw_ls - total_turnover * alt_rate)
        # slippage_bps axis: vary slippage only, keep frozen fee.
        frozen_fee = costs["commission_pct"] * 2.0 + costs["stamp_tax_pct"]
        for value in (0.0, 20.0):
            alt_rate = frozen_fee + value * 2.0 / 1e4
            row = next(r for r in matrix if r["axis"] == "slippage_bps" and math.isclose(r["value"], value))
            assert row["cost_rate"] == pytest.approx(alt_rate)
            assert row["cost_drag"] == pytest.approx(total_turnover * alt_rate)

    def test_rebalance_axis_projects_turnover_by_frequency(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_id, candidate_id, cost_diag = _seed_stress_candidate(
            alpha_run_repository, deterministic_clock,
        )
        service = ResearchRunService(alpha_run_repository)
        result = service.stress_matrix(
            run_id, principal=_PRINCIPAL, candidate_id=candidate_id,
            axes={"rebalance": ["weekly", "monthly"]},
        )
        assert result is not None
        # Declared cadence is daily; weekly/monthly scale turnover by relative frequency.
        from app.research.projections import _REBALANCE_FREQUENCY
        declared_factor = _REBALANCE_FREQUENCY["daily"]
        base_rate = cost_diag["cost_rate"]
        raw_ls = cost_diag["raw_long_short_return"]
        for cadence in ("weekly", "monthly"):
            rel = _REBALANCE_FREQUENCY[cadence] / declared_factor
            alt_turnover = cost_diag["total_turnover"] * rel
            row = next(r for r in result["matrix"] if r["axis"] == "rebalance" and r["value"] == cadence)
            assert row["total_turnover"] == pytest.approx(alt_turnover)
            assert row["cost_drag"] == pytest.approx(alt_turnover * base_rate)
            assert row["net_long_short_return"] == pytest.approx(raw_ls - alt_turnover * base_rate)

    def test_no_admission_or_rescoring_collaborator_called(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        monkeypatch,
    ) -> None:
        run_id, candidate_id, _ = _seed_stress_candidate(
            alpha_run_repository, deterministic_clock,
        )
        service = ResearchRunService(alpha_run_repository)

        def _raising(*args, **kwargs):
            raise AssertionError("stress must not re-score through the signal chain / evaluation")

        # Raising fakes: the stress projection must not call evaluation or admission.
        import app.research.evaluation as evaluation_mod
        import app.research.signal_chain as signal_chain_mod
        import app.research.admission as admission_mod
        for mod, names in (
            (evaluation_mod, ("cost_diagnostics", "FactorEvaluationService", "_cost_rate")),
            (signal_chain_mod, ("FactorSignalChain",)),
            (admission_mod, ("run_admission",)),
        ):
            for name in names:
                if hasattr(mod, name):
                    monkeypatch.setattr(mod, name, _raising)
        # Must still succeed — pure arithmetic over stored turnover.
        result = service.stress_matrix(
            run_id, principal=_PRINCIPAL, candidate_id=candidate_id,
            axes={"fee_bps": [30.0]},
        )
        assert result is not None
        assert any(r["axis"] == "fee_bps" for r in result["matrix"])

    def test_tier2_axes_rejected_as_not_implemented(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_id, candidate_id, _ = _seed_stress_candidate(
            alpha_run_repository, deterministic_clock,
        )
        service = ResearchRunService(alpha_run_repository)
        # Tier-2 axes are an explicit deferral — never a fake result.
        for tier2 in ("calendar_regime", "coverage", "symbol_subset"):
            with pytest.raises(NotImplementedError):
                service.stress_matrix(
                    run_id, principal=_PRINCIPAL, candidate_id=candidate_id,
                    axes={tier2: ["x"]},
                )

    def test_cross_principal_returns_none(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_id, candidate_id, _ = _seed_stress_candidate(
            alpha_run_repository, deterministic_clock,
        )
        service = ResearchRunService(alpha_run_repository)
        assert service.stress_matrix(
            run_id, principal="attacker@example.com", candidate_id=candidate_id, axes={},
        ) is None


class TestStressMatrixEndpoint:
    def test_stress_matrix_returns_baseline_plus_axes(self, compare_client: TestClient) -> None:
        repo: ResearchRepository = compare_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = compare_client._clock  # type: ignore[attr-defined]
        run_id, candidate_id, cost_diag = _seed_stress_candidate(repo, clock)
        resp = compare_client.get(
            f"/api/research/alpha/runs/{run_id}/stress-matrix",
            params={"candidate_id": candidate_id, "fee_bps": [10.0, 30.0]},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["candidate_id"] == candidate_id
        assert body["baseline"]["cost_drag"] == pytest.approx(cost_diag["cost_drag"])
        fee_rows = [r for r in body["matrix"] if r["axis"] == "fee_bps"]
        assert len(fee_rows) == 2

    def test_stress_matrix_tier2_returns_422(self, compare_client: TestClient) -> None:
        repo: ResearchRepository = compare_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = compare_client._clock  # type: ignore[attr-defined]
        run_id, candidate_id, _ = _seed_stress_candidate(repo, clock, run_id="run-t2")
        resp = compare_client.get(
            f"/api/research/alpha/runs/{run_id}/stress-matrix",
            params={"candidate_id": candidate_id, "calendar_regime": ["2020"]},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "not_implemented"

    def test_stress_matrix_unknown_run_404(self, compare_client: TestClient) -> None:
        resp = compare_client.get(
            "/api/research/alpha/runs/no-such-run/stress-matrix",
            params={"candidate_id": "x"},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 404
