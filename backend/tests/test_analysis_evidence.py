"""Wave 0 contracts for deterministic, server-owned analysis evidence."""
from __future__ import annotations

from datetime import date, datetime, timezone
import sqlite3

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError


class EvidenceFixture(BaseModel):
    """Offline fixture mirroring the governed source facts passed to the future boundary."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    origin: str
    independence_group: str
    value: float
    unit: str
    period: str
    definition: str
    retrieved_at: datetime
    as_of: date


def _source(
    source_id: str,
    *,
    origin: str = "exchange-filing",
    independence_group: str = "exchange",
    value: float = 100.0,
    unit: str = "CNY_million",
    period: str = "2025-Q4",
    definition: str = "revenue",
) -> EvidenceFixture:
    return EvidenceFixture(
        source_id=source_id,
        origin=origin,
        independence_group=independence_group,
        value=value,
        unit=unit,
        period=period,
        definition=definition,
        retrieved_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
        as_of=date(2026, 7, 11),
    )


@pytest.mark.parametrize(
    ("origin", "expected_grade"),
    [
        ("exchange-filing", "A"),
        ("issuer-presentation", "B"),
        ("media-summary", "C"),
    ],
)
def test_analysis_evidence_assigns_versioned_source_grades_deterministically(origin, expected_grade):
    from app.analysis.evidence import EvidencePreparationService

    snapshot = EvidencePreparationService(policy_version="evidence-v1").freeze(
        subject_key="600519.SH", records=[_source("source-1", origin=origin)]
    )

    assert snapshot.sources[0].grade == expected_grade
    assert snapshot.policy_version == "evidence-v1"


def test_analysis_evidence_requires_an_independent_peer_for_confirmed_material_number():
    from app.analysis.evidence import EvidencePreparationService

    snapshot = EvidencePreparationService().freeze(
        subject_key="600519.SH",
        records=[
            _source("filing", independence_group="issuer"),
            _source("syndication", origin="media-summary", independence_group="issuer"),
        ],
    )

    assert snapshot.material_numbers[0].status == "unresolved"


@pytest.mark.parametrize(
    "peer",
    [
        _source("peer-unit", independence_group="auditor", unit="CNY"),
        _source("peer-period", independence_group="auditor", period="2026-Q1"),
        _source("peer-definition", independence_group="auditor", definition="operating_income"),
        _source("peer-conflict", independence_group="auditor", value=135.0),
    ],
)
def test_analysis_evidence_keeps_unit_period_definition_and_value_conflicts_visible(peer):
    from app.analysis.evidence import EvidencePreparationService

    snapshot = EvidencePreparationService().freeze(
        subject_key="600519.SH", records=[_source("filing"), peer]
    )

    assert snapshot.material_numbers[0].status in {"unresolved", "conflicting"}


def test_analysis_evidence_returns_explicit_context_insufficient_without_governed_records():
    from app.analysis.evidence import EvidencePreparationService

    snapshot = EvidencePreparationService().freeze(subject_key="600519.SH", records=[])

    assert snapshot.context_status == "context_insufficient"


def test_analysis_evidence_freezes_normalized_provenance_without_raw_source_text():
    from app.analysis.evidence import EvidencePreparationService

    snapshot = EvidencePreparationService().freeze(
        subject_key="600519.SH",
        records=[
            {
                **_source("filing").model_dump(),
                "content": "untrusted filing text must not enter the frozen context",
                "source_locator": "financials/metrics/part.parquet#600519.SH",
            }
        ],
    )

    source = snapshot.sources[0]
    assert source.unit == "CNY_million"
    assert source.provenance.truncated is True
    assert source.provenance.source_locator == "financials/metrics/part.parquet#600519.SH"
    assert "content" not in source.model_dump()
    with pytest.raises(ValidationError):
        source.grade = "C"  # type: ignore[misc]


def test_generated_analysis_and_server_report_reject_extra_fields_and_unknown_citations():
    from app.analysis.evidence import EvidencePreparationService
    from app.analysis.schemas import (
        AnalysisReport,
        FrozenEvidenceSnapshot,
        GeneratedAnalysis,
        ICMemo,
        Perspective,
        SignalLifecycleState,
        ValuationAssessment,
    )

    generated = GeneratedAnalysis(
        perspectives=[
            Perspective(name="fundamental", stance="supports", score=70, rationale="盈利稳定", evidence_ids=["filing"]),
            Perspective(name="risk", stance="neutral", score=50, rationale="需要跟踪", evidence_ids=["filing"]),
        ],
        valuation=ValuationAssessment(applicable=False, method="not_applicable", conclusion="数据不足"),
        ic_memo=ICMemo(
            recommendation="research_only_watch",
            thesis="等待证据完善",
            risks=["财务数据有限"],
            invalidation_conditions=["独立来源冲突"],
            evidence_ids=["filing"],
        ),
    )
    snapshot = FrozenEvidenceSnapshot.model_validate(
        EvidencePreparationService().freeze(subject_key="600519.SH", records=[_source("filing")]).model_dump()
    )

    report = AnalysisReport(
        generated=generated,
        evidence_snapshot=snapshot,
        lifecycle=SignalLifecycleState(signal_id="signal-1", current_state="active", history=[]),
        run_id="run-1",
        report_version=1,
        schema_version="analysis-v1",
    )
    assert report.generated.ic_memo.recommendation == "research_only_watch"
    with pytest.raises(ValidationError):
        GeneratedAnalysis.model_validate({**generated.model_dump(), "source_grade": "A"})
    with pytest.raises(ValidationError, match="unknown evidence ids"):
        AnalysisReport.model_validate({
            **report.model_dump(),
            "generated": {**generated.model_dump(), "ic_memo": {**generated.ic_memo.model_dump(), "evidence_ids": ["unknown"]}},
        })


def test_analysis_repository_migrates_shared_database_and_enforces_single_active_subject_run(tmp_path):
    from app.analysis.repository import AnalysisRepository

    repository = AnalysisRepository(tmp_path / "operational.db")
    repository.migrate()

    first = repository.acquire_run(
        run_id="run-1", subject_kind="stock", subject_key="600519.SH", focus="earnings"
    )
    duplicate = repository.acquire_run(
        run_id="run-2", subject_kind="stock", subject_key="600519.SH", focus="valuation"
    )

    assert duplicate["id"] == first["id"]
    assert first["status"] == "queued"
    assert repository.acquire_run(
        run_id="run-3", subject_kind="stock", subject_key="000001.SZ", focus="earnings"
    )["id"] == "run-3"


def test_analysis_repository_appends_reports_and_database_blocks_audit_rewrites(tmp_path):
    from app.analysis.repository import AnalysisRepository

    repository = AnalysisRepository(tmp_path / "operational.db")
    repository.migrate()
    first = repository.append_validated_report(
        subject_kind="stock", subject_key="600519.SH", report={"version": 1}
    )
    second = repository.append_validated_report(
        subject_kind="stock", subject_key="600519.SH", report={"version": 2}
    )

    assert [row["id"] for row in repository.list_reports("stock", "600519.SH")] == [second["id"], first["id"]]
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        with sqlite3.connect(repository.database_path) as connection:
            connection.execute("UPDATE analysis_reports SET report_json = '{}' WHERE id = ?", (first["id"],))
    assert not hasattr(repository, "delete_report")
