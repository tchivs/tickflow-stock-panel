"""Pure fail-closed preflight gate over a frozen ``ResearchInputSnapshot``.

Phase 48 (AF-REQ-11). The preflight is a *liveness/consistency* layer run over
the already-validated frozen snapshot right before the first provider call. It
maps every AF-REQ-11 capability to one observable check. It is pure: no
provider I/O, no mutation, deterministic from the snapshot. A failed preflight
means the caller MUST NOT reach the provider seam (SC1).

Each failed ``PreflightCheck.reason`` is a bounded machine-readable mapping
(canonical-bounded-JSON validated). Folded capabilities carry a ``sub_reason``
discriminator so each folded sub-item is independently failable (plan-check W2):

* ``data_availability_freshness`` folds data availability/freshness
  (``data_fingerprint``) with source quality (``partition_fingerprint``).
* ``required_fields_sample_length`` folds required fields (``required_fields``)
  with sample length (``sample_length``).

The ``connection`` parameter is accepted but unused by the pure path; it is a
forward hook for an optional live universe-membership resolution wired in a
later phase and would only ever strengthen (never weaken) the gate. The pure
contract — two calls over the same snapshot return an identical result — holds
because no live lookup is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from app.research.run_contract import (
    ResearchInputSnapshot,
    digest_bytes,
    validate_bounded_json,
)

_STATUS_PASS = "pass"
_STATUS_FAIL = "fail"

_REASON_MSG_LIMIT = 200


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    """One capability check: name + pass/fail + bounded reason (None on pass)."""

    name: str
    status: str
    reason: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Aggregate gate result. ``passed`` is False if any check failed."""

    passed: bool
    checks: tuple[PreflightCheck, ...]

    def failed(self) -> tuple[PreflightCheck, ...]:
        """Return only the failed checks, in declaration order."""
        return tuple(check for check in self.checks if check.status == _STATUS_FAIL)


def _reason(code: str, **extra: Any) -> Mapping[str, Any]:
    """Build a bounded machine-readable failure reason with a stable shape."""
    payload: dict[str, Any] = {"code": code}
    for key, value in extra.items():
        payload[key] = _coerce_reason_value(value)
    validate_bounded_json(payload, f"preflight {code}")
    return payload


def _coerce_reason_value(value: Any) -> Any:
    """Reduce a reason component to a bounded JSON scalar."""
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str):
            return value[:_REASON_MSG_LIMIT]
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce_reason_value(item) for item in value][:_REASON_MSG_LIMIT]
    if isinstance(value, Mapping):
        return {str(k): _coerce_reason_value(v) for k, v in value.items()}
    return _coerce_reason_value(str(value))


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _digest_over(group: Mapping[str, Any], key: str) -> str:
    """Recompute a component digest exactly as freeze did (key-scoped)."""
    return digest_bytes({key: group.get(key)})


# ------------------------------------------------------------------
# Per-capability checks. Each returns None on pass or a bounded reason on fail.
# ------------------------------------------------------------------


def _check_data_availability_freshness(snapshot: ResearchInputSnapshot) -> Mapping[str, Any] | None:
    """Data availability/freshness + source quality (folded, W2)."""
    manifest = snapshot.manifest
    data_group = manifest.get("data_manifest")
    if not isinstance(data_group, Mapping) or not data_group:
        return _reason("data_manifest_missing", sub_reason="data_fingerprint")
    live_data = _digest_over(data_group, "fingerprint")
    if live_data != snapshot.component_digests.get("data"):
        return _reason(
            "data_fingerprint_mismatch",
            sub_reason="data_fingerprint",
            frozen=snapshot.component_digests.get("data"),
            live=live_data,
        )
    # Folded sub-item: partition/source-quality fingerprint.
    live_partition = _digest_over(data_group, "partition_fingerprint")
    if live_partition != snapshot.component_digests.get("partition"):
        return _reason(
            "partition_fingerprint_mismatch",
            sub_reason="partition_fingerprint",
            frozen=snapshot.component_digests.get("partition"),
            live=live_partition,
        )
    window = manifest.get("measured_window")
    if not isinstance(window, Mapping) or not window.get("start") or not window.get("end"):
        return _reason("measured_window_missing", sub_reason="measured_window")
    return None


def _check_measured_calendar(snapshot: ResearchInputSnapshot) -> Mapping[str, Any] | None:
    """Fold geometry (the measured calendar definition) structural validity."""
    geometry = snapshot.manifest.get("fold_geometry")
    if not isinstance(geometry, Mapping) or not geometry:
        return _reason("fold_geometry_missing")
    for field in ("train_size", "gap_size", "test_size", "n_folds"):
        value = geometry.get(field)
        if type(value) is not int or value < 0:
            return _reason("fold_geometry_invalid", field=field)
    if geometry["n_folds"] < 1:
        return _reason("fold_geometry_invalid", field="n_folds")
    window = snapshot.manifest.get("measured_window")
    if isinstance(window, Mapping):
        start = _parse_date(window.get("start"))
        end = _parse_date(window.get("end"))
        if start is not None and end is not None and end < start:
            return _reason("measured_window_inverted")
    return None


def _check_pit_universe_scope(snapshot: ResearchInputSnapshot) -> Mapping[str, Any] | None:
    """PIT universe membership fingerprint consistency (frozen scope)."""
    universe = snapshot.manifest.get("universe")
    if not isinstance(universe, Mapping) or not universe:
        return _reason("universe_missing")
    membership_fp = universe.get("membership_fingerprint")
    if not isinstance(membership_fp, str) or not membership_fp:
        return _reason("membership_fingerprint_missing")
    live = _digest_over(universe, "membership_fingerprint")
    if live != snapshot.component_digests.get("membership"):
        return _reason(
            "membership_fingerprint_mismatch",
            frozen=snapshot.component_digests.get("membership"),
            live=live,
        )
    return None


def _check_required_fields_sample_length(snapshot: ResearchInputSnapshot) -> Mapping[str, Any] | None:
    """Required fields + sample length (folded, W2)."""
    from app.research import factor_dsl

    # Folded sub-item 5: required/governed field vocabulary is non-empty.
    if not factor_dsl.ALLOWED_FIELDS:
        return _reason("no_allowed_fields", sub_reason="required_fields")
    # Folded sub-item 6: the measured window spans at least one training fold.
    window = snapshot.manifest.get("measured_window")
    geometry = snapshot.manifest.get("fold_geometry")
    floor = geometry.get("train_size") if isinstance(geometry, Mapping) else None
    if (
        isinstance(window, Mapping)
        and isinstance(floor, int)
        and floor >= 0
    ):
        start = _parse_date(window.get("start"))
        end = _parse_date(window.get("end"))
        if start is not None and end is not None:
            span = (end - start).days
            if span < floor:
                return _reason(
                    "sample_too_short",
                    sub_reason="sample_length",
                    span_days=span,
                    floor_days=floor,
                )
    return None


def _check_dsl_grammar_compatibility(snapshot: ResearchInputSnapshot) -> Mapping[str, Any] | None:
    """DSL vocabulary + grammar fingerprint compatibility with the live build."""
    from app.research.alpha_factory import (
        DEFAULT_MAX_DEPTH,
        DEFAULT_MAX_NODES,
        grammar_fingerprint,
        verify_vocabulary_fingerprint,
    )

    vocabulary = snapshot.manifest.get("vocabulary")
    frozen_vocab = vocabulary.get("fingerprint") if isinstance(vocabulary, Mapping) else None
    try:
        verify_vocabulary_fingerprint(frozen_vocab)
    except Exception as error:  # VocabularyMismatchError or any drift.
        return _reason("vocabulary_mismatch", sub_reason="vocabulary", error=type(error).__name__)
    grammar = snapshot.manifest.get("grammar")
    grammar_map = grammar if isinstance(grammar, Mapping) else {}
    max_depth = grammar_map.get("max_depth", DEFAULT_MAX_DEPTH)
    max_nodes = grammar_map.get("max_nodes", DEFAULT_MAX_NODES)
    try:
        live_grammar = grammar_fingerprint(max_depth=max_depth, max_nodes=max_nodes)
    except Exception as error:
        return _reason("grammar_recompute_failed", sub_reason="grammar", error=type(error).__name__)
    if live_grammar != grammar_map.get("fingerprint"):
        return _reason(
            "grammar_mismatch",
            sub_reason="grammar",
            frozen=grammar_map.get("fingerprint"),
            live=live_grammar,
        )
    return None


def _check_budgets(snapshot: ResearchInputSnapshot) -> Mapping[str, Any] | None:
    """Budget envelope parses from the manifest and is not pre-exhausted."""
    from app.research.alpha_factory import BudgetGuard, BudgetLimits

    try:
        limits = BudgetLimits.from_manifest(snapshot.manifest)
    except Exception as error:
        return _reason("budgets_unparseable", error=type(error).__name__)
    guard = BudgetGuard(limits)
    exhausted = guard.exhausted(candidates=0)
    if exhausted is not None:
        return _reason("budgets_pre_exhausted", budget=exhausted)
    return None


def _check_provider_availability(*, provider: str | None, fixture_selected: bool) -> Mapping[str, Any] | None:
    """A real configured provider OR an explicitly declared offline fixture (D-48-04)."""
    from app.services import ai_provider

    if fixture_selected:
        return None
    configured = ai_provider.ai_configured(provider)
    model = ai_provider.current_ai_model()
    if not configured or not model:
        return _reason(
            "provider_unavailable",
            provider=str(provider),
            configured=bool(configured),
            has_model=bool(model),
        )
    return None


def _check_policy_mode(snapshot: ResearchInputSnapshot) -> Mapping[str, Any] | None:
    """Admission policy fingerprint matches the live build."""
    from app.research.admission import verify_admission_policy_fingerprint

    try:
        verify_admission_policy_fingerprint(snapshot.policy_fingerprint)
    except Exception as error:
        return _reason("policy_mismatch", error=type(error).__name__)
    return None


def _run_check(name: str, fn: Any) -> PreflightCheck:
    """Execute one check, converting any unexpected exception into a failed reason."""
    try:
        reason = fn()
    except Exception as error:  # Defensive: a check must never crash the gate.
        reason = _reason("check_error", error=type(error).__name__)
    if reason is None:
        return PreflightCheck(name=name, status=_STATUS_PASS, reason=None)
    return PreflightCheck(name=name, status=_STATUS_FAIL, reason=reason)


def preflight(
    snapshot: ResearchInputSnapshot,
    *,
    provider: str | None = None,
    fixture_selected: bool = False,
    connection: Any | None = None,
) -> PreflightResult:
    """Run every AF-REQ-11 capability check over the frozen snapshot (pure).

    Pure: performs no provider call, no write, and no lookup whose result could
    vary between two calls over the same snapshot. ``connection`` is accepted as
    a forward hook for an optional live universe resolution but is deliberately
    unused so the result stays deterministic. A ``passed=False`` result means the
    caller MUST NOT reach the provider seam (SC1).
    """
    if not isinstance(snapshot, ResearchInputSnapshot):
        raise TypeError("preflight requires a frozen ResearchInputSnapshot")
    del connection  # Forward hook only; the pure path does not consult it.

    checks = (
        _run_check(
            "data_availability_freshness",
            lambda: _check_data_availability_freshness(snapshot),
        ),
        _run_check("measured_calendar", lambda: _check_measured_calendar(snapshot)),
        _run_check("pit_universe_scope", lambda: _check_pit_universe_scope(snapshot)),
        _run_check(
            "required_fields_sample_length",
            lambda: _check_required_fields_sample_length(snapshot),
        ),
        _run_check(
            "dsl_grammar_compatibility",
            lambda: _check_dsl_grammar_compatibility(snapshot),
        ),
        _run_check("budgets", lambda: _check_budgets(snapshot)),
        _run_check(
            "provider_availability",
            lambda: _check_provider_availability(provider=provider, fixture_selected=fixture_selected),
        ),
        _run_check("policy_mode", lambda: _check_policy_mode(snapshot)),
    )
    return PreflightResult(
        passed=all(check.status == _STATUS_PASS for check in checks),
        checks=checks,
    )
