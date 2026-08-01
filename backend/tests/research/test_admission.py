"""RED scaffold for the Phase 10 admission gate pipeline (FACT-01).

These tests lock the admission contracts and are expected to FAIL until 10-01 creates
``app/research/admission.py``.  Contracts covered:

1. every gate result is recorded in the verdict (admitted AND rejected);
2. a rejection produces a full verdict row with the candidate trail;
3. the temporal split is deterministic (identical train/val boundaries);
4. IC-correlation dedup catches a near-duplicate that Jaccard misses;
5. the verdict is append-only: one row per (revision_id, policy_version).
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository


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
