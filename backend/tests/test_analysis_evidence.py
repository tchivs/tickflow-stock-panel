"""Wave 0 contracts for deterministic, server-owned analysis evidence."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import BaseModel, ConfigDict


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
