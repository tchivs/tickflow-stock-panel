"""Wave 0 contracts for server-enveloped analysis generation and immutable versions."""
from __future__ import annotations

import pytest


def _repository(tmp_path):
    from app.analysis.repository import AnalysisRepository

    repository = AnalysisRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository


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
            return {"generated_body": {"citations": ["unknown-source"]}}

    repository = _repository(tmp_path)
    service = AnalysisService(repository=repository, evidence_preparer=None, graph=FakeGraph())

    run = await service.start_run(subject_kind="stock", subject_key="600519.SH", focus="earnings")

    assert repository.list_reports(subject_kind="stock", subject_key="600519.SH") == []
    assert repository.get_run(run["id"])["status"] == "failed"


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
    with pytest.raises((AttributeError, ValueError), match="immutable|update"):
        repository.update_report(first["id"], {"version": 99})
