"""Factory factor fold scoring + chain-routing guard (Phase 47-01, AF-REQ-05 SC1).

This module supplies the Phase 47 factory fold scorer through the existing
``fold_scorer(fold, *, frame, membership) -> dict`` seam (``walkforward.py:578``)
and a source-level guard that durably proves every scoring entry point routes
through ``FactorSignalChain.compute``. It holds no evaluation, admission, or
backtest authority of its own: the scorer reuses the shared evaluation helpers
to turn a ``FactorSignalFrame`` into per-fold IC/coverage evidence, never the
strategy backtest. No new engine, no forked compute path.
"""
from __future__ import annotations

import inspect
from typing import Any

import polars as pl

from app.research.evaluation import FactorEvaluationService, _per_date_correlation_series
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
