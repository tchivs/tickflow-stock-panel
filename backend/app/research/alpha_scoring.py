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
import re
import uuid
from collections.abc import Mapping
from typing import Any

import polars as pl

from app.research.evaluation import FactorEvaluationResult, FactorEvaluationService, _per_date_correlation_series
from app.research.factor_registry import FactorRegistry, FactorRevision
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


# ----------------------------------------------------------------------
# Phase 47-03 — candidate-ledger-linked admission verdict (AF-REQ-08 SC4)
# ----------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    """Recursively replace non-finite floats with ``None`` for bounded-JSON storage.

    Admission gate ``observed`` values can be non-finite for a degenerate panel
    (e.g. an undefined shifted-label IC over two dates). The verdict row stores
    the authoritative ``gates_json`` via the repository's tolerant serializer,
    but the candidate-ledger ``reason`` is validated by ``validate_bounded_json``
    which rejects non-finite numbers — so the embedded gate trail is sanitized
    (non-finite → ``null``) without dropping the trail structure.
    """
    import math

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _frozen_policy_fingerprint(repo: Any, run_id: str) -> str | None:
    """Return the frozen admission policy fingerprint bound to ``run_id``, or None.

    Reads the persisted input snapshot's manifest ``policy.fingerprint`` (the
    server-owned value populated at freeze). Returns ``None`` when the run has no
    frozen snapshot or no policy fingerprint — :func:`verify_admission_policy_fingerprint`
    treats that as a fail-closed mismatch.
    """
    snapshot_record = repo.get_run_snapshot(run_id)
    if snapshot_record is None:
        return None
    manifest = snapshot_record.get("manifest") or {}
    policy = manifest.get("policy") or {}
    value = policy.get("fingerprint")
    return value if isinstance(value, str) else None


def record_candidate_admission(
    *,
    repo: Any,
    registry: FactorRegistry,
    attempt: AlphaCandidateAttempt,
    revision: FactorRevision,
    universe: str,
    start: Any,
    end: Any,
    horizon: int,
    asset_type: str,
    engine: Any,
    admitted_ic_series: Mapping[str, Mapping[str, float]] | None = None,
    universe_resolver: object | None = None,
    rebalance: str = "daily",
    warmup_days: int = 0,
    n_groups: int = 2,
    catalog: Any | None = None,
    artifact_service: Any | None = None,
) -> dict[str, Any]:
    """Run admission for one candidate and record the terminal verdict on the ledger.

    Resolves the exploratory revision's provenance (``run_id`` / ``candidate_id`` /
    ``candidate_digest``, mintered by 47-01) so the verdict row joins the candidate
    ledger.  First verifies the frozen admission policy fingerprint against the
    live thresholds/gate order (fail-closed before any candidate is scored), then
    runs :func:`run_admission` — passing NO threshold/gate-order kwargs (none
    exist) — and appends one append-only candidate attempt row
    carrying the terminal status (``admitted`` / ``rejected`` / ``failed``) and a
    ``reason`` mapping ``{"verdict", "failing_gate", "gate_trail"}``. A clean gate
    failure records ``rejected`` with the failing gate + full gate trail; an
    evaluation/chain failure (``run_admission`` raising ``ValueError`` /
    ``SignalChainError``) is caught and recorded as ``failed`` with the terminal
    diagnostic — rejection is never converted to admission and failure is never a
    zero score (AF-REQ-07). The appended terminal status is a distinct append-only
    fact linked to the generation attempt by ``candidate_digest``.
    """
    from app.research.admission import run_admission, verify_admission_policy_fingerprint
    from app.research.signal_chain import SignalChainError

    # Fail closed BEFORE scoring any candidate (AF-REQ-08 SC4, T-47-08): the
    # frozen admission policy (server-populated at freeze) must match the live
    # thresholds + gate order + policy version. A divergent policy — a changed
    # constant or reordered gate — raises AdmissionPolicyMismatchError rather
    # than re-scoring a stored run under a different policy.
    verify_admission_policy_fingerprint(_frozen_policy_fingerprint(repo, attempt.run_id))

    # The revision id is the stable join key between the admission verdict row
    # (admission.py) and the candidate ledger (provenance carries run_id +
    # candidate_id). Provenance is recovered but never trusted to override the
    # attempt identity; the append uses the attempt's own ledger fields.
    provenance = dict(revision.provenance or {})
    run_id = provenance.get("run_id") or attempt.run_id
    candidate_id = provenance.get("candidate_id") or attempt.id
    candidate_digest = provenance.get("candidate_digest") or attempt.candidate_digest
    ledger_reason = {
        "candidate_run_id": run_id,
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
    }

    try:
        verdict = run_admission(
            repo,
            engine=engine,
            registry=registry,
            revision_id=revision.id,
            universe=universe,
            start=start,
            end=end,
            horizon=horizon,
            asset_type=asset_type,
            admitted_ic_series=admitted_ic_series,
            universe_resolver=universe_resolver,
            rebalance=rebalance,
            warmup_days=warmup_days,
            n_groups=n_groups,
            catalog=catalog,
            artifact_service=artifact_service,
        )
    except (SignalChainError, ValueError) as error:
        # An evaluation/chain failure is a terminal `failed` outcome — never a
        # zero score, never a clean rejection (AF-REQ-07). The status is sourced
        # verbatim from the failure; rejection cannot be synthesized here.
        reason = {
            **ledger_reason,
            "verdict": "failed",
            "failing_gate": None,
            "gate_trail": [],
            "error": str(error),
        }
        recorded = repo.append_candidate_attempt(
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
            status="failed",
            reason=reason,
        )
        return {**(recorded or {}), "admission_verdict": None}

    # Status sourced verbatim from the verdict — never overridden, never converted.
    status = verdict["verdict"]
    reason = {
        **ledger_reason,
        "verdict": status,
        "failing_gate": verdict["reason"] if status == "rejected" else None,
        "gate_trail": _json_safe(verdict["gates_json"]),
    }
    recorded = repo.append_candidate_attempt(
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
    )
    return {**(recorded or {}), "admission_verdict": verdict}


# ----------------------------------------------------------------------
# Phase 47-03-02 — no-edit hardening guard (AF-REQ-08 SC4, T-47-08)
# ----------------------------------------------------------------------

# Admission policy parameters that must NEVER appear as ``run_admission`` kwargs.
_ADMISSION_FORBIDDEN_PARAMS: frozenset[str] = frozenset({
    "train_min_mean_ic", "val_min_mean_ic", "min_train_observations",
    "max_similarity_score", "max_ic_correlation", "shifted_label_max_abs_ic",
    "min_coverage", "admission_policy_version", "gate_order", "thresholds",
})

# Admission threshold/policy constants a scoring module must NEVER assign to.
_ADMISSION_POLICY_CONSTANTS: frozenset[str] = frozenset({
    "TRAIN_MIN_MEAN_IC", "VAL_MIN_MEAN_IC", "MIN_TRAIN_OBSERVATIONS",
    "MAX_SIMILARITY_SCORE", "MAX_IC_CORRELATION", "SHIFTED_LABEL_MAX_ABS_IC",
    "MIN_COVERAGE", "ADMISSION_POLICY_VERSION",
})


def _run_admission_signature_clean(func: Any) -> bool:
    """True if ``func`` exposes no threshold/gate-order parameter.

    Source-level (structural) check (plan-check W3): it inspects the live
    signature of ``run_admission`` and cannot see dynamic dispatch.
    """
    params = {name.lower() for name in inspect.signature(func).parameters}
    return not (params & _ADMISSION_FORBIDDEN_PARAMS)


def _scoring_modules() -> list[Any]:
    """The factory/Agent scoring modules whose inputs must not reach the policy."""
    from app.backtest import walkforward
    from app.research import alpha_factory, evaluation

    return [alpha_factory, evaluation, walkforward]


def _source_mutates_policy(module: Any) -> bool:
    """True if ``module``'s source assigns to an admission threshold constant.

    Matches ``CONST =`` (and ``obj.CONST =``) but not ``==``/comparisons or a
    read on the right-hand side. Source-level (structural), not behavioral (W3).
    """
    names = "|".join(_ADMISSION_POLICY_CONSTANTS)
    pattern = re.compile(rf"\b({names})\s*=(?!=)")
    return bool(pattern.search(inspect.getsource(module)))


def _source_inserts_verdict(module: Any) -> bool:
    """True if ``module``'s source calls ``insert_admission_verdict`` directly.

    The only legitimate admission write path is ``run_admission`` →
    ``_record_verdict``; a scoring module forging a verdict directly is an
    SC4 violation. Source-level (structural), not behavioral (W3).
    """
    return "insert_admission_verdict" in inspect.getsource(module)


def assert_admission_no_edit() -> None:
    """Durable SC4 guard: factory/Agent inputs cannot edit the admission policy.

    Source-level (structural) guard mirroring :func:`assert_all_scoring_through_chain`
    (plan-check W3): it confirms at the import-graph / call-site level that
    (1) ``run_admission`` exposes no threshold/gate-order parameters,
    (2) no scoring module assigns to an admission threshold constant, and
    (3) no scoring module calls ``insert_admission_verdict`` directly with a
    hand-crafted verdict. It cannot see dynamic dispatch or runtime monkeypatching,
    but it durably catches a factory or Agent source edit that rewires the policy.
    """
    from app.research.admission import run_admission

    if not _run_admission_signature_clean(run_admission):
        raise AssertionError(
            "SC4 violation — run_admission exposes a threshold/gate-order parameter"
        )
    for module in _scoring_modules():
        name = module.__name__
        if _source_mutates_policy(module):
            raise AssertionError(
                f"SC4 violation — scoring module {name} mutates an admission threshold constant"
            )
        if _source_inserts_verdict(module):
            raise AssertionError(
                f"SC4 violation — scoring module {name} calls insert_admission_verdict directly"
            )
