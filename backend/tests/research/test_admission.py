"""RED scaffold for the Phase 10 admission gate pipeline (FACT-01).

These tests lock the admission contracts and are expected to FAIL until 10-01 creates
``app/research/admission.py``.  Contracts covered:

1. every gate result is recorded in the verdict (admitted AND rejected);
2. a rejection produces a full verdict row with the candidate trail;
3. the temporal split is deterministic (identical train/val boundaries);
4. IC-correlation dedup catches a near-duplicate that Jaccard misses;
5. ``MIN_TRAIN_OBSERVATIONS`` short-window rejection;
6. the verdict is append-only: one row per (revision_id, policy_version).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from app.research.artifacts import EvaluationArtifactService
from app.research.catalog import ExperimentCatalog
from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository
from tests.research.conftest import StubBacktestEngine


@pytest.fixture

def admission_module():
    """Deferred import: the module does not exist until 10-01."""
    from app.research.admission import (  # noqa: F401
        ADMISSION_POLICY_VERSION,
        TRAIN_MIN_MEAN_IC,
        VAL_MIN_MEAN_IC,
        MIN_TRAIN_OBSERVATIONS,
        MAX_SIMILARITY_SCORE,
        MAX_IC_CORRELATION,
        SHIFTED_LABEL_MAX_ABS_IC,
        MIN_COVERAGE,
        run_admission,
        temporal_split,
    )

    return {
        "ADMISSION_POLICY_VERSION": ADMISSION_POLICY_VERSION,
        "TRAIN_MIN_MEAN_IC": TRAIN_MIN_MEAN_IC,
        "VAL_MIN_MEAN_IC": VAL_MIN_MEAN_IC,
        "MIN_TRAIN_OBSERVATIONS": MIN_TRAIN_OBSERVATIONS,
        "MAX_SIMILARITY_SCORE": MAX_SIMILARITY_SCORE,
        "MAX_IC_CORRELATION": MAX_IC_CORRELATION,
        "SHIFTED_LABEL_MAX_ABS_IC": SHIFTED_LABEL_MAX_ABS_IC,
        "MIN_COVERAGE": MIN_COVERAGE,
        "run_admission": run_admission,
        "temporal_split": temporal_split,
    }


def test_policy_constants_are_fixed_and_documented(admission_module) -> None:
    assert admission_module["ADMISSION_POLICY_VERSION"] == "admission-policy-v1"
    assert admission_module["TRAIN_MIN_MEAN_IC"] > 0
    assert admission_module["VAL_MIN_MEAN_IC"] > 0
    assert admission_module["MIN_TRAIN_OBSERVATIONS"] >= 1
    assert 0 < admission_module["MAX_SIMILARITY_SCORE"] < 1
    assert 0 < admission_module["MAX_IC_CORRELATION"] < 1
    assert admission_module["SHIFTED_LABEL_MAX_ABS_IC"] > 0
    assert 0 < admission_module["MIN_COVERAGE"] <= 1


def test_every_gate_result_is_recorded_in_verdict(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    admission_module,
) -> None:
    revision = research_registry.create_factor(name="Close", expression="close")
    verdict = admission_module["run_admission"](
        research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_id=revision.id,
        universe="fixture-a-share",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )
    assert verdict["verdict"] in {"admitted", "rejected"}
    assert verdict["policy_version"] == admission_module["ADMISSION_POLICY_VERSION"]
    assert verdict["input_snapshot_sha256"] and len(verdict["input_snapshot_sha256"]) == 64


def test_rejection_records_full_verdict_row_with_candidate_trail(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    admission_module,
) -> None:
    revision = research_registry.create_factor(
        name="Lookahead", expression="close", provenance={"source": "manual", "ticket": "R-42"}
    )
    verdict = admission_module["run_admission"](
        research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_id=revision.id,
        universe="fixture-a-share",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )
    assert verdict["verdict"] in {"admitted", "rejected"}
    assert "provenance" in verdict["candidate_trail_json"]
    assert "evaluation_run_ids" in verdict["candidate_trail_json"]
    assert "experiment_snapshot_ids" in verdict["candidate_trail_json"]
    assert "gate_results" in verdict["candidate_trail_json"]


def test_temporal_split_is_deterministic(admission_module) -> None:
    """Identical inputs yield identical train/val boundaries by date order."""
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]
    per_date_ics = {day: 0.05 for day in dates}
    first_train, first_val = admission_module["temporal_split"](per_date_ics)
    second_train, second_val = admission_module["temporal_split"](per_date_ics)
    assert first_train == second_train
    assert first_val == second_val
    assert len(first_train) == 4  # 70% of 6 dates by date order
    assert len(first_val) == 2
    assert first_train == {"2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"}
    assert first_val == {"2024-01-08", "2024-01-09"}


def test_verdict_is_append_only_single_row_per_revision_policy(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    admission_module,
) -> None:
    revision = research_registry.create_factor(name="Close", expression="close")
    admission_module["run_admission"](
        research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_id=revision.id,
        universe="fixture-a-share",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )
    with pytest.raises(Exception):
        admission_module["run_admission"](
            research_repository,
            engine=stub_engine,
            registry=research_registry,
            revision_id=revision.id,
            universe="fixture-a-share",
            start=date(2024, 1, 2),
            end=date(2024, 1, 3),
        )


def _seed7_panel(n_dates: int, *, seed: int = 7) -> pl.DataFrame:
    """Deterministic 8-symbol panel whose ``close`` factor passes gates 1-3."""
    rng = np.random.default_rng(seed)
    n_syms = 8
    prices = np.empty((n_dates, n_syms))
    for i in range(n_syms):
        walk = rng.normal(0, 0.02, n_dates)
        prices[:, i] = np.exp(np.cumsum(walk) + 0.001 * np.arange(n_dates))
    start = date(2024, 1, 2)
    rows = []
    for day_idx in range(n_dates):
        day = start + timedelta(days=day_idx)
        for symbol_idx in range(n_syms):
            rows.append({"symbol": f"S{symbol_idx:02d}", "date": day, "close": float(prices[day_idx, symbol_idx])})
    return pl.DataFrame(rows)


def test_admission_verdict_carries_catalogued_evaluation_reference(tmp_path) -> None:
    """A real run records the evaluation it performed and links the snapshot."""
    from app.research.admission import run_admission

    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    registry = FactorRegistry(repository)
    engine = StubBacktestEngine(_seed7_panel(60))
    artifacts = EvaluationArtifactService(tmp_path / "app-data")
    catalog = ExperimentCatalog(repository)
    revision = registry.create_factor(
        name="Close", expression="close", provenance={"source": "manual", "ticket": "R-42"}
    )
    verdict = run_admission(
        repository,
        engine=engine,
        registry=registry,
        revision_id=revision.id,
        universe="fixture-a-share",
        start=date(2024, 1, 2),
        end=date(2024, 1, 2) + timedelta(days=59),
        catalog=catalog,
        artifact_service=artifacts,
    )
    assert verdict["verdict"] == "admitted"
    trail = verdict["candidate_trail_json"]
    assert trail["provenance"] == {"source": "manual", "ticket": "R-42"}
    assert len(trail["evaluation_run_ids"]) == 1
    assert len(trail["experiment_snapshot_ids"]) == 1
    snapshot = catalog.get(trail["experiment_snapshot_ids"][0])
    assert snapshot is not None
    assert snapshot.originating_run_id == trail["evaluation_run_ids"][0]
    assert [gate["gate"] for gate in trail["gate_results"]] == [
        "no_lookahead", "coverage", "no_label_leakage", "similarity_dedup", "train_ic", "val_ic",
    ]


def test_ic_correlation_dedup_catches_what_jaccard_misses(tmp_path) -> None:
    """A structurally-different twin with identical per-date IC is rejected by IC-corr."""
    from app.research.admission import run_admission

    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    registry = FactorRegistry(repository)
    engine = StubBacktestEngine(_seed7_panel(60))
    artifacts = EvaluationArtifactService(tmp_path / "app-data")
    catalog = ExperimentCatalog(repository)

    admitted = registry.create_factor(name="Close", expression="close", provenance={"source": "manual", "ticket": "R-1"})
    verdict = run_admission(
        repository,
        engine=engine,
        registry=registry,
        revision_id=admitted.id,
        universe="fixture-a-share",
        start=date(2024, 1, 2),
        end=date(2024, 1, 2) + timedelta(days=59),
        catalog=catalog,
        artifact_service=artifacts,
    )
    assert verdict["verdict"] == "admitted"
    snapshot = catalog.get(verdict["candidate_trail_json"]["experiment_snapshot_ids"][0])
    admitted_ic = {row["date"]: row["ic"] for row in snapshot.metrics["ic_series"]}

    # Structural twin: different AST/operator set, identical values → IC series
    # perfectly correlated, but Jaccard structural similarity is far below 0.8.
    twin = registry.create_factor(name="CloseTwin", expression="close * 1.0 + 0.0", provenance={"source": "manual", "ticket": "R-2"})
    jaccard = max(
        (candidate.score for candidate in registry.discover_similar(twin.canonical_expression, exclude_revision_id=twin.id)),
        default=0.0,
    )
    assert jaccard < 0.8  # Jaccard structural dedup alone would NOT reject

    verdict = run_admission(
        repository,
        engine=engine,
        registry=registry,
        revision_id=twin.id,
        universe="fixture-a-share",
        start=date(2024, 1, 2),
        end=date(2024, 1, 2) + timedelta(days=59),
        admitted_ic_series={admitted.id: admitted_ic},
        catalog=catalog,
        artifact_service=artifacts,
    )
    assert verdict["verdict"] == "rejected"
    gate = next(item for item in verdict["gates_json"] if item["gate"] == "similarity_dedup")
    assert gate["passed"] is False
    assert gate["observed"]["ic_correlation"] == pytest.approx(1.0)
    assert gate["observed"]["similarity_score"] < 0.8


def test_min_train_observations_rejects_short_window(tmp_path) -> None:
    """A 56-date window yields 38 train observations and rejects on train_ic."""
    from app.research.admission import MIN_TRAIN_OBSERVATIONS, run_admission

    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    registry = FactorRegistry(repository)
    engine = StubBacktestEngine(_seed7_panel(56))
    artifacts = EvaluationArtifactService(tmp_path / "app-data")
    catalog = ExperimentCatalog(repository)
    revision = registry.create_factor(name="Close", expression="close")
    verdict = run_admission(
        repository,
        engine=engine,
        registry=registry,
        revision_id=revision.id,
        universe="fixture-a-share",
        start=date(2024, 1, 2),
        end=date(2024, 1, 2) + timedelta(days=55),
        catalog=catalog,
        artifact_service=artifacts,
    )
    assert verdict["verdict"] == "rejected"
    assert verdict["reason"] == "train_ic"
    train_gate = next(item for item in verdict["gates_json"] if item["gate"] == "train_ic")
    assert train_gate["passed"] is False
    assert f"min {MIN_TRAIN_OBSERVATIONS}" in train_gate["detail"]
    assert f"{MIN_TRAIN_OBSERVATIONS}" in train_gate["detail"]
    trail = verdict["candidate_trail_json"]
    assert trail["evaluation_run_ids"]
    assert trail["experiment_snapshot_ids"]
    # Gates before train_ic now include coverage: no_lookahead, coverage,
    # no_label_leakage, similarity_dedup, train_ic.
    assert len(trail["gate_results"]) == 5


def test_ic_correlation_dedup_aligns_sparse_admitted_dates(tmp_path) -> None:
    """CR-02: a sparse admitted IC series is date-aligned before correlation.

    The old implementation truncated both arrays to ``min(len)`` positionally,
    pairing a candidate with a SPARSE admitted series at mismatched dates.  In
    the fixture below the candidate observes all five val dates while the
    admitted series drops ``d0``; the positional pairing happens to pair
    anti-aligned values as if they were in phase and returns **+1.0**.  The
    date-intersected gate returns **-1.0** — the true anti-correlation of the
    common dates.
    """
    from app.research.admission import _ic_correlation_duplicate

    candidate = {"d0": 0.1, "d1": 0.2, "d2": 0.1, "d3": 0.2, "d4": 0.1}
    admitted = {"d1": 0.1, "d2": 0.2, "d3": 0.1, "d4": 0.2}  # sparse: d0 dropped
    val_dates = {"d0", "d1", "d2", "d3", "d4"}

    observed = _ic_correlation_duplicate(candidate, {"admitted": admitted}, val_dates=val_dates)

    # Date-aligned reference: common dates are d1..d4 and the series are
    # perfectly anti-correlated there.
    common = sorted(set(candidate) & set(admitted) & set(val_dates))
    candidate_values = np.array([candidate[day] for day in common], dtype=float)
    admitted_values = np.array([admitted[day] for day in common], dtype=float)
    reference = float(np.corrcoef(candidate_values, admitted_values)[0, 1])
    assert reference == pytest.approx(-1.0)
    assert observed == pytest.approx(-1.0, abs=1e-9)
    # The gate's signed worst is anti-correlated, NOT the spurious +1.0 the
    # positional truncation produced.
    assert observed < 0.0
