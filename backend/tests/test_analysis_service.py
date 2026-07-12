"""Wave 0 contracts for server-enveloped analysis generation and immutable versions."""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest


def _repository(tmp_path):
    from app.analysis.repository import AnalysisRepository

    repository = AnalysisRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository


def _evidence_records():
    return [
        {
            "source_id": "known-source",
            "origin": "exchange-filing",
            "independence_group": "exchange",
            "value": 100.0,
            "unit": "CNY_million",
            "period": "2025-Q4",
            "definition": "revenue",
            "retrieved_at": datetime(2026, 7, 12),
            "as_of": date(2026, 7, 11),
        }
    ]


def _analysis_body(evidence_id="known-source"):
    return {
        "perspectives": [
            {"name": "fundamental", "stance": "supports", "score": 70, "rationale": "evidence", "evidence_ids": [evidence_id]},
            {"name": "risk", "stance": "neutral", "score": 50, "rationale": "watch", "evidence_ids": [evidence_id]},
        ],
        "valuation": {"applicable": False, "method": "not_applicable", "conclusion": "insufficient"},
        "ic_memo": {
            "recommendation": "research_only_watch",
            "thesis": "wait",
            "risks": ["risk"],
            "invalidation_conditions": ["conflict"],
            "evidence_ids": [evidence_id],
        },
    }


async def test_analysis_service_returns_existing_active_run_for_the_same_subject(tmp_path):
    from app.analysis.service import AnalysisService

    repository = _repository(tmp_path)
    service = AnalysisService(repository=repository, evidence_preparer=None, graph=None)

    first = await service.start_run(subject_kind="stock", subject_key="600519.SH", focus="earnings")
    second = await service.start_run(subject_kind="stock", subject_key="600519.SH", focus="earnings")

    assert first["id"] == second["id"]
    assert first["status"] == "failed"
    assert second["status"] == "failed"


@pytest.mark.parametrize("missing", ["graph", "preparer", "loader"])
async def test_analysis_service_records_terminal_failure_when_new_run_lacks_execution_collaborator(
    tmp_path, missing
):
    from app.analysis.evidence import EvidencePreparationService
    from app.analysis.service import AnalysisService

    class Graph:
        async def ainvoke(self, *_args, **_kwargs):
            return {"generated_body": _analysis_body()}

    service = AnalysisService(
        repository=_repository(tmp_path),
        evidence_preparer=None if missing == "preparer" else EvidencePreparationService(),
        graph=None if missing == "graph" else Graph(),
        evidence_loader=None if missing == "loader" else lambda *_args: _evidence_records(),
    )

    run = await service.start_run(subject_kind="instrument", subject_key="600519.SH", focus="earnings")

    assert run["status"] == "failed"
    assert run["failure_reason"] == "analysis execution is unavailable; manual review required"


async def test_analysis_service_audits_unknown_citation_without_writing_a_partial_report(tmp_path):
    from app.analysis.service import AnalysisService

    class FakeGraph:
        async def ainvoke(self, *_args, **_kwargs):
            return {"generated_body": _analysis_body("unknown-source")}

    from app.analysis.evidence import EvidencePreparationService

    repository = _repository(tmp_path)
    service = AnalysisService(
        repository=repository,
        evidence_preparer=EvidencePreparationService(),
        graph=FakeGraph(),
        evidence_loader=lambda *_args: _evidence_records(),
    )

    run = await service.start_run(subject_kind="stock", subject_key="600519.SH", focus="earnings")

    assert repository.list_reports(subject_kind="stock", subject_key="600519.SH") == []
    assert repository.get_run(run["id"])["status"] == "failed"
    assert "unknown-source" not in repository.get_run(run["id"])["failure_reason"]
    metadata = json.loads(repository.get_run(run["id"])["audit_metadata_json"])
    assert metadata["attempts"] == 3
    assert metadata["evidence_fingerprint"]


async def test_analysis_service_persists_only_a_server_enveloped_validated_report(tmp_path):
    from app.analysis.evidence import EvidencePreparationService
    from app.analysis.service import AnalysisService

    class FakeGraph:
        async def ainvoke(self, *_args, **_kwargs):
            return {"generated_body": _analysis_body()}

    repository = _repository(tmp_path)
    service = AnalysisService(
        repository=repository,
        evidence_preparer=EvidencePreparationService(),
        graph=FakeGraph(),
        evidence_loader=lambda *_args: _evidence_records(),
    )

    run = await service.start_run(subject_kind="stock", subject_key="600519.SH", focus="earnings")
    reports = repository.list_reports("stock", "600519.SH")

    assert run["status"] == "completed"
    assert reports[0]["report"]["run_id"] == run["id"]
    assert reports[0]["report"]["generation_metadata"]["attempts"] == 1
    assert run["audit_metadata_json"]


async def test_completed_analysis_creates_an_attributable_review_proposal_without_official_transition(tmp_path):
    from app.analysis.evidence import EvidencePreparationService
    from app.analysis.lifecycle import LifecycleRuleService
    from app.analysis.service import AnalysisService

    class FakeGraph:
        async def ainvoke(self, *_args, **_kwargs):
            return {"generated_body": _analysis_body()}

    repository = _repository(tmp_path)
    lifecycle = LifecycleRuleService(repository=repository)
    service = AnalysisService(
        repository=repository,
        evidence_preparer=EvidencePreparationService(),
        graph=FakeGraph(),
        evidence_loader=lambda *_args: _evidence_records(),
        lifecycle_rule_service=lifecycle,
    )

    run = await service.start_run(subject_kind="stock", subject_key="600519.SH", focus="earnings")
    reports = repository.list_reports("stock", "600519.SH")
    reviews = repository.list_lifecycle_reviews(subject_kind="stock", subject_key="600519.SH")

    assert run["status"] == "completed"
    assert len(reviews) == 1
    review = reviews[0]
    assert review["prior_state"] == "active"
    assert review["proposed_state"] == "strengthened"
    assert review["evidence"][0]["run_id"] == run["id"]
    assert review["evidence"][0]["report_id"] == reports[0]["id"]
    assert review["evidence"][0]["evidence_snapshot_id"] == repository.get_frozen_snapshot(run["id"])["id"]
    assert repository.current_lifecycle_state(subject_kind="stock", subject_key="600519.SH") == "active"
    assert repository.list_events(subject_kind="stock", subject_key="600519.SH") == []

    repeated_run = await service.start_run(subject_kind="stock", subject_key="600519.SH", focus="earnings")

    assert repeated_run["status"] == "completed"
    assert len(repository.list_lifecycle_reviews(subject_kind="stock", subject_key="600519.SH")) == 1


async def test_failed_or_duplicate_analysis_completion_does_not_create_extra_lifecycle_proposals(tmp_path):
    from app.analysis.evidence import EvidencePreparationService
    from app.analysis.lifecycle import LifecycleRuleService
    from app.analysis.service import AnalysisService

    class InvalidGraph:
        async def ainvoke(self, *_args, **_kwargs):
            return {"generated_body": _analysis_body("unknown-source")}

    repository = _repository(tmp_path)
    lifecycle = LifecycleRuleService(repository=repository)
    service = AnalysisService(
        repository=repository,
        evidence_preparer=EvidencePreparationService(),
        graph=InvalidGraph(),
        evidence_loader=lambda *_args: _evidence_records(),
        lifecycle_rule_service=lifecycle,
    )

    failed_run = await service.start_run(subject_kind="stock", subject_key="600519.SH", focus="earnings")

    assert failed_run["status"] == "failed"
    assert repository.list_lifecycle_reviews(subject_kind="stock", subject_key="600519.SH") == []
    assert repository.list_events(subject_kind="stock", subject_key="600519.SH") == []


def test_analysis_repository_orders_versions_and_rejects_history_rewrites(tmp_path):
    repository = _repository(tmp_path)
    first = repository.append_validated_report(
        subject_kind="stock", subject_key="600519.SH", report={"version": 1}
    )
    second = repository.append_validated_report(
        subject_kind="stock", subject_key="600519.SH", report={"version": 2}
    )

    assert [report["id"] for report in repository.list_reports("stock", "600519.SH")] == [
        second["id"],
        first["id"],
    ]
    with pytest.raises((AttributeError, ValueError), match=r"immutable|update"):
        repository.update_report(first["id"], {"version": 99})
