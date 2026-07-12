"""Wave 0 contracts for server-enveloped analysis generation and immutable versions."""
from __future__ import annotations

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
    assert first["status"] in {"queued", "running"}


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
