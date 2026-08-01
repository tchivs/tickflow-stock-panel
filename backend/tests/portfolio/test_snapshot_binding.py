"""Phase 11 snapshot binding — checksum-verified composite consumption (PFOL-04).

Contracts (11-RESEARCH.md `## Input Snapshot Binding`): the optimizer consumes
the Phase 10 composite BY SNAPSHOT — catalog.get_composite_model →
checksum-verified artifact load (output_sha256 vs bytes) → as_of cross-section —
never a live module hand-off. Every fail-closed path (model missing, no snapshot,
artifact absent/tampered, lookahead as_of) raises SnapshotBindingError; through
run_optimization the failure is recorded as a failed run with failure_reason.
"""
from __future__ import annotations

import json
from datetime import date
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from app.portfolio.optimizer import run_optimization
from app.portfolio.repository import PortfolioRepository
from app.portfolio.snapshot import SnapshotBindingError, load_composite_snapshot
from app.research.catalog import ExperimentCatalog
from app.research.repository import ResearchRepository

FIXTURE_SYMBOLS = ("600000.SH", "600001.SH", "600002.SH", "600003.SH")


def _write_signals_artifact(data_dir: Path, model_id: str, rows: list[dict]) -> tuple[str, str]:
    """Write a [symbol, date, composite] signals.json artifact and return
    (relative_path, output_sha256) matching the Phase 10 write pattern."""
    relative = f"research_artifacts/{model_id}/signals.json"
    path = data_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    path.write_bytes(content)
    return relative, sha256(content).hexdigest()


def _register_composite(
    repository: PortfolioRepository,
    *,
    model_id: str,
    artifact_relative_path: str,
    output_sha256: str,
    input_snapshot_sha256: str,
) -> None:
    """Register a composite model definition + snapshot row (the catalog seam
    factor_model_models / factor_model_composites pair)."""
    research = ResearchRepository(repository.database_path)
    research.insert_model_definition(
        model_id=model_id,
        name=f"snapshot-fixture {model_id}",
        weighting="equal",
        revision_ids=[],
        weights={},
        input_snapshot_sha256=input_snapshot_sha256,
    )
    research.insert_model_composite(
        model_id=model_id,
        output_sha256=output_sha256,
        artifact_relative_path=artifact_relative_path,
        input_snapshot_sha256=input_snapshot_sha256,
    )


@pytest.fixture
def snapshot_catalog(portfolio_repository: PortfolioRepository) -> ExperimentCatalog:
    return ExperimentCatalog(ResearchRepository(portfolio_repository.database_path))


def _default_rows(as_of: date) -> list[dict]:
    return [
        {"symbol": "600000.SH", "date": as_of.isoformat(), "composite": 0.5},
        {"symbol": "600001.SH", "date": as_of.isoformat(), "composite": -0.3},
        {"symbol": "600002.SH", "date": as_of.isoformat(), "composite": 0.2},
        {"symbol": "600003.SH", "date": as_of.isoformat(), "composite": 0.1},
    ]


def test_load_composite_snapshot_returns_checksum_verified_cross_section(
    portfolio_repository: PortfolioRepository,
    snapshot_catalog: ExperimentCatalog,
    artifact_root: Path,
) -> None:
    """(1) model present + artifact checksum match → symbols/mu + audit-root sha."""
    model_id = "snapshot-model-v1"
    input_sha = "a" * 64
    as_of = date(2026, 8, 1)
    relative, output_sha = _write_signals_artifact(
        artifact_root, model_id, _default_rows(as_of)
    )
    _register_composite(
        portfolio_repository,
        model_id=model_id,
        artifact_relative_path=relative,
        output_sha256=output_sha,
        input_snapshot_sha256=input_sha,
    )
    snapshot = load_composite_snapshot(
        snapshot_catalog, model_id=model_id, as_of=as_of, data_dir=artifact_root
    )
    assert snapshot["model_id"] == model_id
    assert snapshot["input_snapshot_sha256"] == input_sha
    assert snapshot["composite_snapshot_id"]
    assert snapshot["symbols"] == list(FIXTURE_SYMBOLS)
    assert snapshot["mu"] == pytest.approx([0.5, -0.3, 0.2, 0.1])


def test_model_missing_fails_closed(
    snapshot_catalog: ExperimentCatalog, artifact_root: Path
) -> None:
    """(2) model missing from catalog → SnapshotBindingError."""
    with pytest.raises(SnapshotBindingError, match="model not found"):
        load_composite_snapshot(
            snapshot_catalog, model_id="missing-model", as_of=date(2026, 8, 1), data_dir=artifact_root
        )


def test_no_composite_snapshot_fails_closed(
    portfolio_repository: PortfolioRepository,
    snapshot_catalog: ExperimentCatalog,
    artifact_root: Path,
) -> None:
    """(3) latest_composite is None (definition without any snapshot) → error."""
    research = ResearchRepository(portfolio_repository.database_path)
    research.insert_model_definition(
        model_id="definition-only",
        name="definition only",
        weighting="equal",
        revision_ids=[],
        weights={},
        input_snapshot_sha256="b" * 64,
    )
    with pytest.raises(SnapshotBindingError, match="no composite snapshot recorded"):
        load_composite_snapshot(
            snapshot_catalog, model_id="definition-only", as_of=date(2026, 8, 1), data_dir=artifact_root
        )


def test_artifact_tampered_fails_closed(
    portfolio_repository: PortfolioRepository,
    snapshot_catalog: ExperimentCatalog,
    artifact_root: Path,
) -> None:
    """(4) artifact bytes tampered → SnapshotBindingError (checksum mismatch)."""
    model_id = "snapshot-model-tampered"
    input_sha = "c" * 64
    as_of = date(2026, 8, 1)
    relative, _ = _write_signals_artifact(artifact_root, model_id, _default_rows(as_of))
    # Tamper the artifact AFTER recording its original checksum.
    _register_composite(
        portfolio_repository,
        model_id=model_id,
        artifact_relative_path=relative,
        output_sha256="d" * 64,
        input_snapshot_sha256=input_sha,
    )
    with pytest.raises(SnapshotBindingError, match="checksum mismatch"):
        load_composite_snapshot(
            snapshot_catalog, model_id=model_id, as_of=as_of, data_dir=artifact_root
        )


def test_artifact_absent_fails_closed(
    portfolio_repository: PortfolioRepository,
    snapshot_catalog: ExperimentCatalog,
    artifact_root: Path,
) -> None:
    """(4b) artifact file absent → SnapshotBindingError (checksum mismatch)."""
    model_id = "snapshot-model-absent"
    _register_composite(
        portfolio_repository,
        model_id=model_id,
        artifact_relative_path=f"research_artifacts/{model_id}/signals.json",
        output_sha256="e" * 64,
        input_snapshot_sha256="f" * 64,
    )
    with pytest.raises(SnapshotBindingError, match="checksum mismatch"):
        load_composite_snapshot(
            snapshot_catalog, model_id=model_id, as_of=date(2026, 8, 1), data_dir=artifact_root
        )


def test_lookahead_as_of_fails_closed(
    portfolio_repository: PortfolioRepository,
    snapshot_catalog: ExperimentCatalog,
    artifact_root: Path,
) -> None:
    """(5) as_of precedes the artifact's data coverage → SnapshotBindingError
    (lookahead guard — the panel window clause of RESEARCH.md)."""
    model_id = "snapshot-model-lookahead"
    input_sha = "f" * 64
    as_of = date(2026, 8, 1)
    # Data coverage starts AFTER as_of: consuming this snapshot at as_of is lookahead.
    future_rows = [
        {"symbol": "600000.SH", "date": "2026-08-05", "composite": 0.5},
        {"symbol": "600001.SH", "date": "2026-08-05", "composite": -0.3},
    ]
    relative, output_sha = _write_signals_artifact(artifact_root, model_id, future_rows)
    _register_composite(
        portfolio_repository,
        model_id=model_id,
        artifact_relative_path=relative,
        output_sha256=output_sha,
        input_snapshot_sha256=input_sha,
    )
    with pytest.raises(SnapshotBindingError, match="as_of precedes"):
        load_composite_snapshot(
            snapshot_catalog, model_id=model_id, as_of=as_of, data_dir=artifact_root
        )


def test_run_optimization_records_failed_run_on_snapshot_binding_failure(
    portfolio_repository: PortfolioRepository,
    snapshot_catalog: ExperimentCatalog,
    artifact_root: Path,
) -> None:
    """(6) end-to-end: a snapshot binding failure through run_optimization is
    recorded as a failed run with failure_reason — never a silent abort."""
    model_id = "snapshot-model-run-fail"
    input_sha = "f" * 64
    as_of = date(2026, 8, 1)
    relative, _ = _write_signals_artifact(artifact_root, model_id, _default_rows(as_of))
    # Recorded output_sha256 does NOT match the artifact bytes → binding fails.
    _register_composite(
        portfolio_repository,
        model_id=model_id,
        artifact_relative_path=relative,
        output_sha256="0" * 64,
        input_snapshot_sha256=input_sha,
    )
    run = run_optimization(
        {
            "objective": "min_volatility",
            "as_of": as_of.isoformat(),
            "universe": "cn-a-share",
            "model_id": model_id,
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        catalog=snapshot_catalog,
        data_dir=artifact_root,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert "checksum mismatch" in run["failure_reason"]
    # The failed run is persisted (auditable) and retrievable.
    fetched = portfolio_repository.get_optimization_run(run["id"])
    assert fetched is not None
    assert fetched["problem_status"] == "failed"
    assert fetched["failure_reason"] == run["failure_reason"]


def test_run_optimization_input_snapshot_sha256_matches_composite(
    portfolio_repository: PortfolioRepository,
    snapshot_catalog: ExperimentCatalog,
    artifact_root: Path,
) -> None:
    """PFOL-04: a successful catalog-seam run records input_snapshot_sha256 ==
    factor_model_composites.input_snapshot_sha256 (cross-module audit root)."""
    model_id = "snapshot-model-run-ok"
    input_sha = "f" * 64
    as_of = date(2026, 8, 1)
    relative, output_sha = _write_signals_artifact(
        artifact_root, model_id, _default_rows(as_of)
    )
    _register_composite(
        portfolio_repository,
        model_id=model_id,
        artifact_relative_path=relative,
        output_sha256=output_sha,
        input_snapshot_sha256=input_sha,
    )
    run = run_optimization(
        {
            "objective": "min_volatility",
            "as_of": as_of.isoformat(),
            "universe": "cn-a-share",
            "model_id": model_id,
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.30,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        catalog=snapshot_catalog,
        data_dir=artifact_root,
        returns=np.array(
            [
                [0.010, 0.012, 0.008, 0.006],
                [0.011, 0.013, 0.007, 0.005],
                [0.012, 0.014, 0.009, 0.007],
                [0.009, 0.011, 0.010, 0.004],
                [0.013, 0.015, 0.006, 0.008],
                [0.010, 0.012, 0.011, 0.006],
            ]
        ),
    )
    assert run["problem_status"] == "optimal"
    assert run["input_snapshot_sha256"] == input_sha
    assert run["composite_snapshot_id"] is not None
    composites = ResearchRepository(portfolio_repository.database_path).list_model_composites(model_id)
    assert composites[0]["input_snapshot_sha256"] == input_sha
