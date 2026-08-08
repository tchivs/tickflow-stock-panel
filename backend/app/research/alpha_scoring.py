"""Factory factor fold scoring, immutable evidence binding + chain-routing guard.

Phase 47-01 supplied the factory fold scorer through the existing
``fold_scorer(fold, *, frame, membership) -> dict`` seam and a source-level
chain-routing guard (AF-REQ-05 SC1). Phase 47-02 adds the durable per-candidate
evidence binding: ``record_candidate_evidence`` writes one immutable evidence
artifact and binds it to the candidate ledger via ``evidence_artifact_id``
(+ ``artifact_verified=True``), recording a terminal ``failed`` reason on
evaluation failure — never a zero score (AF-REQ-07 SC3) — and
``record_selection_fold_evidence`` records selection-fold (``is_oos=0``)
evidence in the candidate-keyed, INSERT-only ``research_alpha_fold_evidence``
table. No new engine, no forked compute path.
"""
from __future__ import annotations

import inspect
import uuid
from typing import Any

import polars as pl

from app.research.evaluation import FactorEvaluationResult, FactorEvaluationService, _per_date_correlation_series
from app.research.factor_registry import FactorRevision
from app.research.run_contract import AlphaCandidateAttempt
from app.research.signal_chain import FactorSignalFrame


def factor_fold_scorer(fold: Any, *, frame: FactorSignalFrame, membership: Any) -> dict[str, Any]:
    """Turn a ``FactorSignalFrame`` into per-fold IC/RankIC/coverage evidence.

    Consumes the chain frame over the fold's TEST window and returns factor-shaped
    stats by reusing ``evaluation._per_date_correlation_series`` / ``_summary`` /
    ``_coverage`` — the same helpers ``FactorEvaluationService.evaluate`` uses —
    without invoking ``StrategyBacktestService``. Supplied as ``fold_scorer=`` to
    ``run_walk_forward`` it replaces the default strategy-backtest per-fold score
    with factor IC/coverage evidence.

    Only the selection fold's own rectangle (``fold.test_start``/``test_end``) is
    read; the reserved OOS fold is never referenced here — its inaccessibility is
    enforced by ``run_walk_forward(evaluate_oos=False)``.
    """
    test_window = frame.frame.filter(
        (pl.col("date") >= fold.test_start) & (pl.col("date") <= fold.test_end)
    )
    ic_series, rank_ic_series = _per_date_correlation_series(test_window)
    ic_summary = FactorEvaluationService._summary(ic_series, "ic")
    rank_ic_summary = FactorEvaluationService._summary(rank_ic_series, "rank_ic")
    coverage = FactorEvaluationService._coverage(frame.resolved_universe)
    resolved = getattr(frame, "resolved_universe", None) or {}
    return {
        "test_stats": {
            "mean_ic": ic_summary.get("mean"),
            "rank_ic": rank_ic_summary.get("mean"),
            "coverage": coverage.get("mean"),
            "effective_days": len(ic_series),
        },
        "membership_fingerprint": str(resolved.get("membership_fingerprint", "")),
        "declared_fingerprints": dict(frame.declared_fingerprints),
    }


def _routes_through_chain(func: Any) -> bool:
    """True if ``func``'s own source references a ``FactorSignalChain.compute`` call.

    Source-level check: it proves the entry point's source routes through the
    shared chain. It cannot see dynamic dispatch or runtime monkeypatching
    (documented limitation, plan-check W3).
    """
    try:
        source = inspect.getsource(func)
    except (TypeError, OSError):
        return False
    return "compute(revision_id" in source or ".compute(" in source


def assert_all_scoring_through_chain() -> None:
    """Durable SC1 guard: every scoring entry point routes through the chain.

    Inspects the live source of the load-bearing scoring entry points and raises
    ``AssertionError`` if one no longer calls ``FactorSignalChain.compute``. This
    is a source-level (structural) guard, not a behavioral one — it cannot see
    dynamic dispatch or runtime monkeypatching (plan-check W3) — but it durably
    catches a factory or Agent source edit that rewires a scoring path around the
    governed chain.
    """
    from app.backtest import walkforward
    from app.research import admission
    from app.research.evaluation import FactorEvaluationService

    checks = [
        ("FactorEvaluationService.evaluate", FactorEvaluationService.evaluate),
        ("admission.run_admission", admission.run_admission),
        ("walkforward._run_fold", walkforward._run_fold),
    ]
    missing = [label for label, func in checks if not _routes_through_chain(func)]
    if missing:
        raise AssertionError(
            "SC1 violation — these scoring entry points no longer route through "
            "FactorSignalChain.compute: " + ", ".join(missing)
        )


# ----------------------------------------------------------------------
# Phase 47-02 — immutable per-candidate evidence binding (AF-REQ-07 SC3)
# ----------------------------------------------------------------------


def _candidate_outcome(
    result: FactorEvaluationResult, attempt: AlphaCandidateAttempt
) -> tuple[str, dict[str, Any]]:
    """Map an evaluation result onto a candidate-ledger (status, reason) pair.

    A completed evaluation preserves the candidate's prior status (it stays
    ``generated`` pending admission in 47-03). A failed/invalid evaluation is a
    terminal ``failed`` outcome carrying the diagnostic as reason — never a zero
    score or a ``completed`` evidence row (AF-REQ-07).
    """
    if result.status == "completed":
        return attempt.status, {
            "evaluation": "completed",
            "evaluation_run_id": result.evaluation_run_id,
        }
    diagnostic = "; ".join(result.diagnostics) if result.diagnostics else result.status
    return "failed", {"evaluation": result.status, "reason": diagnostic}


def record_candidate_evidence(
    *,
    repo: Any,
    artifact_service: Any,
    attempt: AlphaCandidateAttempt,
    revision: FactorRevision,
    result: FactorEvaluationResult,
    declared_fingerprints: Any,
    costs: Any,
) -> dict[str, Any]:
    """Bind one immutable evidence artifact to a candidate attempt (AF-REQ-07 SC3).

    Writes one content-addressed evidence artifact (the full
    ``FactorEvaluationResult`` + the six declared fingerprints + the declared
    cost policy; ``result.cost_diagnostics`` is already inside the result) via
    the existing ``AlphaRunArtifactService``, records its descriptor through the
    service-owned ``append_artifact`` seam, then appends a candidate attempt row
    whose status is derived from ``result.status`` and whose
    ``evidence_artifact_id`` is set with ``artifact_verified=True``. A terminal
    evaluation failure records ``status='failed'`` with the diagnostic as
    reason — never a zero score or a ``completed`` evidence row.
    """
    evidence_payload = {
        "evaluation": result.as_dict(),
        "declared_fingerprints": dict(declared_fingerprints),
        "costs": dict(costs),
        "candidate": {
            "run_id": attempt.run_id,
            "candidate_digest": attempt.candidate_digest,
            "canonical_expression": attempt.canonical_expression,
        },
        "revision": {"id": revision.id, "dsl_version": revision.dsl_version},
    }
    descriptor = artifact_service.write(run_id=attempt.run_id, payload=evidence_payload)
    artifact_id = uuid.uuid4().hex
    repo.append_artifact(
        run_id=attempt.run_id,
        artifact_id=artifact_id,
        logical_kind="candidate_evidence",
        relative_path=descriptor["relative_path"],
        content_type=descriptor["content_type"],
        byte_size=descriptor["byte_size"],
        checksum_sha256=descriptor["checksum_sha256"],
        artifact_service=artifact_service,
    )
    status, reason = _candidate_outcome(result, attempt)
    return repo.append_candidate_attempt(
        run_id=attempt.run_id,
        candidate_id=attempt.id,
        attempt_ordinal=attempt.attempt_ordinal,
        candidate_digest=attempt.candidate_digest,
        canonical_expression=attempt.canonical_expression,
        ast_signature=attempt.ast_signature,
        shape_signature=attempt.shape_signature,
        dsl_version=attempt.dsl_version,
        operation=attempt.operation,
        seed=attempt.seed,
        step=attempt.step,
        status=status,
        reason=reason,
        evidence_artifact_id=artifact_id,
        artifact_verified=True,
    )


def record_selection_fold_evidence(
    *,
    repo: Any,
    run_id: str,
    candidate_digest: str,
    revision_id: str,
    folds: Any,
) -> list[dict[str, Any]]:
    """Record selection-fold (``is_oos=0``) evidence for a candidate (AF-REQ-07).

    ``folds`` is an iterable of ``(fold, frame, membership)`` triples; each fold
    is scored via :func:`factor_fold_scorer` (from 47-01) and recorded in the
    candidate-keyed, INSERT-only ``research_alpha_fold_evidence`` table with
    ``is_oos=0``. A reconnect/retry is idempotent: a fold whose evidence already
    exists (``find_alpha_fold_evidence``) is skipped rather than duplicated. The
    reserved OOS fold is never recorded here — 47-04 owns the single
    ``is_oos=1`` row.
    """
    recorded: list[dict[str, Any]] = []
    for fold, frame, membership in folds:
        if (
            repo.find_alpha_fold_evidence(
                run_id=run_id,
                candidate_digest=candidate_digest,
                fold_index=fold.fold_index,
                is_oos=False,
            )
            is not None
        ):
            continue
        scored = factor_fold_scorer(fold, frame=frame, membership=membership)
        recorded.append(
            repo.record_alpha_fold_evidence(
                run_id=run_id,
                candidate_digest=candidate_digest,
                fold_index=fold.fold_index,
                is_oos=False,
                revision_id=revision_id,
                train_start=fold.train_start,
                train_end=fold.train_end,
                test_start=fold.test_start,
                test_end=fold.test_end,
                membership_fingerprint=scored["membership_fingerprint"],
                declared_fingerprints=scored["declared_fingerprints"],
                stats=scored["test_stats"],
            )
        )
    return recorded
