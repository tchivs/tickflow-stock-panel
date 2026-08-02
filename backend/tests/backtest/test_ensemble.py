"""Rank-average ensemble (WFWD-03) — Wave 0 RED scaffold.

Contract cases locked here (turned green by 13-04):
- validated-only gate: every strategy in the ensemble must resolve to a
  ``wf_validated_strategies`` row with ``passed_gate=1``, else fail closed
- rank-average: ``ensemble_rank`` equals the manual mean of per-strategy
  ``_rank`` per (symbol, date), then re-ranked per date
- output shape: ``[symbol, date, ensemble_rank, ensemble_zscore]``
- the ``wf_ensembles`` row binds ``input_snapshot_sha256`` (strategy_ids,
  weights, validation_record_ids, membership_fingerprint) to a checksum
  verified artifact
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from app.research.artifacts import EvaluationArtifactService
from app.research.repository import ResearchRepository


def _artifact_service(tmp_path: Path) -> EvaluationArtifactService:
    return EvaluationArtifactService(tmp_path / "data")


def _signal_frame(symbols: list[str], dates: list[str], rank: float) -> pl.DataFrame:
    """A per-strategy chain frame with a per-date cross-sectional ``_rank``."""
    rows = [{"symbol": symbol, "date": day, "_rank": rank} for symbol in symbols for day in dates]
    return pl.DataFrame(rows)


def _validated_record(
    research_repository: ResearchRepository,
    *,
    strategy_id: str = "s1",
    plan_id: str = "plan-v",
    oos_fold_id: str | None = None,
) -> dict:
    """Seed a passed_gate=1 verdict row (plan + OOS fold prerequisites)."""
    import datetime

    now = "2026-08-01T00:00:00Z"
    if oos_fold_id is None:
        oos_fold_id = "wf-fold-oos-" + strategy_id
        research_repository.create_wf_plan(
            _FakePlan(plan_id=plan_id + "-" + strategy_id, now=now)
        )
        research_repository.record_wf_fold(
            id=oos_fold_id,
            plan_id=plan_id + "-" + strategy_id,
            fold_index=0,
            is_oos=True,
            strategy_id=strategy_id,
            params_sha256="a" * 64,
            train_start=datetime.date(2026, 4, 1),
            train_end=datetime.date(2026, 6, 3),
            test_start=datetime.date(2026, 6, 4),
            test_end=datetime.date(2026, 7, 30),
            membership_fingerprint="b" * 64,
            chain_config={},
            stats={"effective_days": 35},
        )
    return research_repository.record_validated_strategy(
        strategy_id=strategy_id,
        plan_id=plan_id + "-" + strategy_id,
        search_run_id=None,
        params_sha256="a" * 64,
        oos_evidence_fold_id=oos_fold_id,
        resolved_asset_ids=["000001.SZ", "000002.SZ"],
        validation_score=0.5,
        fold_evidence={"per_fold": [0.4, 0.5, 0.6]},
        passed_gate=True,
    )


class _FakePlan:
    def __init__(self, plan_id: str, now: str = "2026-08-01T00:00:00Z") -> None:
        self.plan_id = plan_id
        self.universe = "cn-a-share"
        self.asset_type = "stock"
        self.start = "2025-07-29"
        self.end = "2026-07-30"
        self.train_size = 120
        self.gap_size = 20
        self.test_size = 20
        self.oos_size = 40
        self.horizon = 5
        self.trading_dates = ["2025-07-29"]
        self.folds: list[object] = []
        self.oos_fold = _FakeFold(0, True)
        self.created_at = now


class _FakeFold:
    def __init__(self, index: int, is_oos: bool) -> None:
        self.fold_index = index
        self.is_oos = is_oos
        self.train_start = "2025-07-29"
        self.train_end = "2026-01-22"
        self.gap_start = "2026-01-23"
        self.gap_end = "2026-02-27"
        self.test_start = "2026-06-04"
        self.test_end = "2026-07-30"


# ---------------------------------------------------------------------------
# WFWD-03: RED until 13-04 lands build_ensemble / EnsembleConfig
# ---------------------------------------------------------------------------


def test_build_ensemble_rank_averages_validated_signals(
    research_repository: ResearchRepository,
) -> None:
    """ensemble_rank == mean of per-strategy _rank, re-ranked per date."""
    from app.backtest.ensemble import EnsembleConfig, build_ensemble

    v1 = _validated_record(research_repository, strategy_id="s1")
    v2 = _validated_record(research_repository, strategy_id="s2", plan_id="plan-w")
    config = EnsembleConfig(
        strategy_ids=("s1", "s2"),
        weights={"s1": 0.5, "s2": 0.5},
        validation_record_ids=(v1["id"], v2["id"]),
    )
    signals = {
        "s1": _signal_frame(["A", "B"], ["2026-07-01"], rank=1.0),
        "s2": _signal_frame(["A", "B"], ["2026-07-01"], rank=3.0),
    }
    out = build_ensemble(
        config=config, signals=signals, universe="cn-a-share", start="2026-07-01", end="2026-07-01", horizon=5,
        repo=research_repository,
    )
    assert out.columns == ["symbol", "date", "ensemble_rank", "ensemble_zscore"]
    # manual reference: per (symbol, date) mean of _rank = 2.0 for both symbols
    a_row = out.filter(pl.col("symbol") == "A").select("ensemble_rank").item()
    b_row = out.filter(pl.col("symbol") == "B").select("ensemble_rank").item()
    assert a_row == b_row == 2.0


def test_build_ensemble_fails_closed_on_unvalidated_strategy(
    research_repository: ResearchRepository,
) -> None:
    """A strategy without a passed_gate=1 verdict raises ValueError."""
    from app.backtest.ensemble import EnsembleConfig, build_ensemble

    v1 = _validated_record(research_repository, strategy_id="s1")
    config = EnsembleConfig(
        strategy_ids=("s1", "s2"),
        weights={"s1": 0.5, "s2": 0.5},
        validation_record_ids=(v1["id"],),
    )
    signals = {"s1": _signal_frame(["A"], ["2026-07-01"], 1.0)}
    with pytest.raises(ValueError, match="not validated"):
        build_ensemble(
            config=config, signals=signals, universe="cn-a-share", start="2026-07-01", end="2026-07-01", horizon=5,
            repo=research_repository,
        )


def test_record_wf_ensemble_round_trips_and_lists(
    research_repository: ResearchRepository,
) -> None:
    """wf_ensembles row binds input/output sha256 + relative path."""
    row = research_repository.record_wf_ensemble(
        name="wf-ensemble-v1",
        strategy_ids=["s1", "s2"],
        weights={"s1": 0.5, "s2": 0.5},
        validation_record_ids=["v1", "v2"],
        input_snapshot_sha256="c" * 64,
        output_sha256="d" * 64,
        artifact_relative_path="research_artifacts/wf-ens-1/ensemble.parquet",
    )
    assert row["strategy_ids"] == ["s1", "s2"]
    assert row["input_snapshot_sha256"] == "c" * 64
    rows = research_repository.list_wf_ensembles()
    assert len(rows) == 1
    with pytest.raises(ValueError, match="limit"):
        research_repository.list_wf_ensembles(limit=0)


def test_build_ensemble_fails_closed_on_non_passed_gate_record(
    research_repository: ResearchRepository,
) -> None:
    """A validation_record_id resolving to passed_gate=0 fails closed."""
    from app.backtest.ensemble import EnsembleConfig, build_ensemble

    v1 = _validated_record(research_repository, strategy_id="s1")
    import datetime

    research_repository.record_wf_fold(
        id="wf-fold-extra-" + v1["id"],
        plan_id="plan-v-s1",
        fold_index=0,
        is_oos=True,
        strategy_id="s1",
        params_sha256="e" * 64,
        train_start=datetime.date(2026, 4, 1),
        train_end=datetime.date(2026, 6, 3),
        test_start=datetime.date(2026, 6, 4),
        test_end=datetime.date(2026, 7, 30),
        membership_fingerprint="e" * 64,
        chain_config={},
        stats={"effective_days": 35},
    )
    research_repository.record_validated_strategy(
        strategy_id="s1",
        plan_id="plan-v-s1",
        search_run_id=None,
        params_sha256="e" * 64,
        oos_evidence_fold_id="wf-fold-extra-" + v1["id"],
        resolved_asset_ids=["000001.SZ"],
        validation_score=-1.0,
        fold_evidence={},
        passed_gate=False,
    )
    config = EnsembleConfig(
        strategy_ids=("s1",),
        validation_record_ids=(v1["id"], "wf-fold-extra-" + v1["id"]),
    )
    signals = {"s1": _signal_frame(["A"], ["2026-07-01"], 1.0)}
    with pytest.raises(ValueError, match="not validated"):
        build_ensemble(
            config=config, signals=signals, universe="cn-a-share", start="2026-07-01", end="2026-07-01", horizon=5,
            repo=research_repository,
        )


def test_build_ensemble_defaults_to_equal_weights(
    research_repository: ResearchRepository,
) -> None:
    """Equal-weight default is frozen: omitted weights mean 1/n."""
    from app.backtest.ensemble import EnsembleConfig, build_ensemble

    v1 = _validated_record(research_repository, strategy_id="s1")
    v2 = _validated_record(research_repository, strategy_id="s2", plan_id="plan-w")
    config = EnsembleConfig(
        strategy_ids=("s1", "s2"),
        validation_record_ids=(v1["id"], v2["id"]),
    )
    signals = {
        "s1": _signal_frame(["A", "B"], ["2026-07-01"], rank=2.0),
        "s2": _signal_frame(["A", "B"], ["2026-07-01"], rank=2.0),
    }
    out = build_ensemble(
        config=config, signals=signals, universe="cn-a-share", start="2026-07-01", end="2026-07-01", horizon=5,
        repo=research_repository,
    )
    # equal 1/2 weights: mean rank 2.0 for both symbols -> rank 2.0 (tie max)
    assert out.select("ensemble_rank").to_series().to_list() == [2.0, 2.0]
    assert out.select("ensemble_zscore").to_series().to_list() == [0.0, 0.0]


def test_save_ensemble_persists_checksum_verified_artifact(
    research_repository: ResearchRepository,
    tmp_path: Path,
) -> None:
    """save_ensemble: O_EXCL artifact + wf_ensembles row binding both digests."""
    from app.backtest.ensemble import EnsembleConfig, build_ensemble, save_ensemble

    v1 = _validated_record(research_repository, strategy_id="s1")
    v2 = _validated_record(research_repository, strategy_id="s2", plan_id="plan-w")
    config = EnsembleConfig(
        strategy_ids=("s1", "s2"),
        weights={"s1": 0.5, "s2": 0.5},
        validation_record_ids=(v1["id"], v2["id"]),
    )
    signals = {
        "s1": _signal_frame(["A", "B"], ["2026-07-01"], rank=1.0),
        "s2": _signal_frame(["A", "B"], ["2026-07-01"], rank=3.0),
    }
    frame = build_ensemble(
        config=config, signals=signals, universe="cn-a-share", start="2026-07-01", end="2026-07-01", horizon=5,
        repo=research_repository,
    )
    artifact_service = _artifact_service(tmp_path)
    result = save_ensemble(
        config=config, frame=frame, artifact_service=artifact_service, repo=research_repository,
        name="wf-ensemble-v1",
    )
    assert result["idempotent"] is False
    row = result["row"]
    assert len(row["input_snapshot_sha256"]) == 64
    assert len(row["output_sha256"]) == 64
    # the checksum-verified read path: re-hash the artifact bytes and compare
    artifact = artifact_service.root.parent / row["artifact_relative_path"]
    assert artifact.is_file()
    assert artifact.read_bytes()  # O_EXCL + fsync wrote real bytes
    import hashlib

    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == row["output_sha256"]
    assert row["strategy_ids"] == ["s1", "s2"]
    assert row["weights"] == {"s1": 0.5, "s2": 0.5}


def test_save_ensemble_idempotent_same_inputs_different_inputs_raise(
    research_repository: ResearchRepository,
    tmp_path: Path,
) -> None:
    """Same name+snapshot returns the existing row; different input raises (O_EXCL)."""
    from app.backtest.ensemble import EnsembleConfig, build_ensemble, save_ensemble

    v1 = _validated_record(research_repository, strategy_id="s1")
    v2 = _validated_record(research_repository, strategy_id="s2", plan_id="plan-w")
    config = EnsembleConfig(
        strategy_ids=("s1", "s2"),
        weights={"s1": 0.5, "s2": 0.5},
        validation_record_ids=(v1["id"], v2["id"]),
    )
    signals = {
        "s1": _signal_frame(["A", "B"], ["2026-07-01"], rank=1.0),
        "s2": _signal_frame(["A", "B"], ["2026-07-01"], rank=3.0),
    }
    frame = build_ensemble(
        config=config, signals=signals, universe="cn-a-share", start="2026-07-01", end="2026-07-01", horizon=5,
        repo=research_repository,
    )
    artifact_service = _artifact_service(tmp_path)
    first = save_ensemble(
        config=config, frame=frame, artifact_service=artifact_service, repo=research_repository,
        name="wf-ensemble-v1",
    )
    assert first["idempotent"] is False
    # same inputs: existing row returned, no second artifact namespace
    second = save_ensemble(
        config=config, frame=frame, artifact_service=artifact_service, repo=research_repository,
        name="wf-ensemble-v1",
    )
    assert second["idempotent"] is True
    assert second["row"]["id"] == first["row"]["id"]
    assert len(list(artifact_service.root.iterdir())) == 1
    # different membership -> different snapshot -> refuse to overwrite evidence
    altered = frame.filter(pl.col("symbol") == "A")
    with pytest.raises(ValueError, match="different input"):
        save_ensemble(
            config=config, frame=altered, artifact_service=artifact_service, repo=research_repository,
            name="wf-ensemble-v1",
        )


def test_save_ensemble_binds_membership_fingerprint_into_snapshot(
    research_repository: ResearchRepository,
    tmp_path: Path,
) -> None:
    """The input snapshot covers (strategy_ids, weights, validation_record_ids, fingerprint)."""
    from app.backtest.ensemble import EnsembleConfig, build_ensemble, save_ensemble

    v1 = _validated_record(research_repository, strategy_id="s1")
    v2 = _validated_record(research_repository, strategy_id="s2", plan_id="plan-w")
    config = EnsembleConfig(
        strategy_ids=("s1", "s2"),
        weights={"s1": 0.5, "s2": 0.5},
        validation_record_ids=(v1["id"], v2["id"]),
    )
    signals = {
        "s1": _signal_frame(["A", "B"], ["2026-07-01"], rank=1.0),
        "s2": _signal_frame(["A", "B"], ["2026-07-01"], rank=3.0),
    }
    frame = build_ensemble(
        config=config, signals=signals, universe="cn-a-share", start="2026-07-01", end="2026-07-01", horizon=5,
        repo=research_repository,
    )
    artifact_service = _artifact_service(tmp_path)
    fp = "f" * 64
    result = save_ensemble(
        config=config, frame=frame, artifact_service=artifact_service, repo=research_repository,
        name="wf-ensemble-v1", membership_fingerprint=fp,
    )
    payload = json.dumps(
        {
            "strategy_ids": ["s1", "s2"],
            "weights": {"s1": 0.5, "s2": 0.5},
            "validation_record_ids": [v1["id"], v2["id"]],
            "membership_fingerprint": fp,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    import hashlib

    assert result["input_snapshot_sha256"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_build_ensemble_window_trims_to_requested_dates(
    research_repository: ResearchRepository,
) -> None:
    """Rows outside [start, end] are trimmed (research-use windowing)."""
    from app.backtest.ensemble import EnsembleConfig, build_ensemble

    v1 = _validated_record(research_repository, strategy_id="s1")
    v2 = _validated_record(research_repository, strategy_id="s2", plan_id="plan-w")
    config = EnsembleConfig(
        strategy_ids=("s1", "s2"),
        weights={"s1": 0.5, "s2": 0.5},
        validation_record_ids=(v1["id"], v2["id"]),
    )
    signals = {
        "s1": _signal_frame(["A"], ["2026-06-01", "2026-07-01"], rank=1.0),
        "s2": _signal_frame(["A"], ["2026-06-01", "2026-07-01"], rank=3.0),
    }
    out = build_ensemble(
        config=config, signals=signals, universe="cn-a-share", start="2026-07-01", end="2026-07-01", horizon=5,
        repo=research_repository,
    )
    assert out["date"].to_list() == ["2026-07-01"]
