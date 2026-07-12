"""Allowlisted display projections for immutable analysis records."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def report_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project immutable report metadata without exposing its stored envelope."""
    snapshot = _snapshot(record)
    return {
        "id": str(record["id"]),
        "subject": _subject(record),
        "version": int(record["version"]),
        "status": "validated",
        "generated_at": str(record["created_at"]),
        "evidence_limitations": _limitations(snapshot),
    }


def report_detail(record: Mapping[str, Any], *, signal_id: str) -> dict[str, Any]:
    """Project the server-validated report body and its server-issued signal ID."""
    payload = _mapping(record.get("report"))
    generated = _mapping(payload.get("generated"))
    snapshot = _snapshot(record)
    limitations = _limitations(snapshot)
    perspectives = [
        {
            "name": str(perspective.get("name", "")),
            "conclusion": str(perspective.get("rationale", "")),
            "evidence_count": len(_strings(perspective.get("evidence_ids"))),
            "limitations": limitations,
        }
        for perspective in _mappings(generated.get("perspectives"))
    ]
    valuation = _mapping(generated.get("valuation"))
    memo = _mapping(generated.get("ic_memo"))
    return {
        **report_summary(record),
        "signal_id": signal_id,
        "perspectives": perspectives,
        "score": {
            "dimensions": [
                {
                    "name": item["name"],
                    "contribution": perspective.get("score"),
                    "evidence_ids": _strings(perspective.get("evidence_ids")),
                    "rationale": item["conclusion"],
                    "uncertainty": "; ".join(limitations) or None,
                }
                for item, perspective in zip(perspectives, _mappings(generated.get("perspectives")), strict=True)
            ]
        },
        "valuation": {
            "applicable": bool(valuation.get("applicable")),
            "method": valuation.get("method"),
            "reason": valuation.get("conclusion"),
            "limitations": limitations,
        },
        "ic_memo": {
            "thesis": str(memo.get("thesis", "")),
            "supporting_evidence": _strings(memo.get("evidence_ids")),
            "risks": _strings(memo.get("risks")),
            "open_questions": [],
            "valuation_anchor": valuation.get("conclusion") if valuation.get("applicable") else None,
            "invalidation_conditions": _strings(memo.get("invalidation_conditions")),
            "evidence_limitations": limitations,
        },
    }


def evidence(record: Mapping[str, Any], snapshot_record: Mapping[str, Any]) -> dict[str, Any]:
    """Project frozen evidence while excluding raw snapshot and provenance internals."""
    snapshot = _mapping(snapshot_record.get("snapshot"))
    sources = _mappings(snapshot.get("sources"))
    return {
        "report_id": str(record["id"]),
        "sources": [
            {
                "id": str(source.get("source_id", "")),
                "name": str(source.get("origin", "")),
                "grade": source.get("grade"),
                "source_type": str(source.get("origin", "")),
                "retrieved_at": source.get("retrieved_at"),
                "period": source.get("period"),
                "definition": source.get("definition"),
                "independence_group": source.get("independence_group"),
                "reference": _mapping(source.get("provenance")).get("source_locator"),
            }
            for source in sources
        ],
        "material_numbers": [
            {
                "id": str(number.get("number_id", "")),
                "label": str(number.get("definition", number.get("number_id", ""))),
                "value": number.get("value"),
                "unit": str(number.get("unit", "")),
                "period": str(number.get("period", "")),
                "source_count": 1 + len(_strings(number.get("peer_source_ids"))),
                "cross_check": _cross_check(number.get("status"), snapshot.get("context_status")),
                "difference_reason": number.get("comparison_reason"),
            }
            for number in _mappings(snapshot.get("material_numbers"))
        ],
    }


def signal_history(
    *,
    signal: Mapping[str, Any],
    current_state: str,
    events: Sequence[Mapping[str, Any]],
    reviews: Sequence[Mapping[str, Any]],
    plans: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project append-only lifecycle records without reviewer identity or raw evidence."""
    rejected_review_ids = {
        str(review["rejected_review_id"])
        for review in reviews
        if isinstance(review.get("rejected_review_id"), str)
    }
    review_states = {
        str(review.get("id")): _review_status(review, events, rejected_review_ids) for review in reviews
    }
    pending = next((str(review["id"]) for review in reviews if review_states[str(review["id"])] == "pending"), None)
    return {
        "signal_id": str(signal["id"]),
        "current_state": None if current_state == "active" else current_state,
        "events": [
            {
                "state": event.get("next_state"),
                "occurred_at": event.get("occurred_at"),
                "evidence_summary": "confirmed server evidence",
                "source_grade": None,
                "cross_check": None,
            }
            for event in events
        ],
        "pending_review_id": pending,
        "reviews": [
            {
                "id": str(review["id"]),
                "prior_state": review.get("prior_state"),
                "proposed_state": review.get("proposed_state"),
                "status": review_states[str(review["id"])],
                "evidence_ids": _strings(review.get("evidence_ids")),
                "rationale": review.get("rationale"),
                "created_at": review.get("created_at"),
            }
            for review in reviews
        ],
        "plans": list(plans),
        "outcome": _outcome_summary(plans),
    }


def _snapshot(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_mapping(record.get("report")).get("evidence_snapshot"))


def _subject(record: Mapping[str, Any]) -> dict[str, str]:
    kind = str(record["subject_kind"])
    return {"kind": "stock" if kind == "instrument" else "portfolio", "key": str(record["subject_key"])}


def _limitations(snapshot: Mapping[str, Any]) -> list[str]:
    if snapshot.get("context_status") == "context_insufficient":
        return ["证据上下文不足"]
    return [
        f"{number.get('definition', number.get('number_id', '材料数字'))} 的交叉核验{number.get('status')}"
        for number in _mappings(snapshot.get("material_numbers"))
        if number.get("status") in {"conflicting", "unresolved"}
    ]


def _cross_check(status: object, context_status: object) -> str:
    if context_status == "context_insufficient":
        return "context_insufficient"
    return str(status) if status in {"confirmed", "conflicting", "unresolved"} else "unresolved"


def _review_status(
    review: Mapping[str, Any], events: Sequence[Mapping[str, Any]], rejected_review_ids: set[str]
) -> str:
    if review.get("proposed_state") == "rejected" or str(review.get("id")) in rejected_review_ids:
        return "rejected"
    return "confirmed" if any(event.get("review_id") == review.get("id") for event in events) else "pending"


def _outcome_summary(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    outcomes = [outcome for plan in plans for outcome in _mappings(plan.get("outcomes"))]
    return {"status": "recorded", "outcomes": outcomes} if outcomes else {"status": "pending"} if plans else None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: object) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, Sequence) and not isinstance(value, str) else []


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, Sequence) and not isinstance(value, str) else []
