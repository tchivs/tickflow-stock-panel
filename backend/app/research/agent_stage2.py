"""Stage 2 contract for the FactorResearchAgent (AF-REQ-13, AF-REQ-21).

A read-only :class:`StageTwoRequest` (frozen snapshot + server-produced
evidence), a strict (``extra='forbid'``) output schema that structurally forbids
ANY mutable field (caveats + a bounded advisory recommendation -- no
expression/metric/threshold/OOS/admission), a referential-integrity check that
rejects any cited candidate/evaluation/gate/artifact ID that does not resolve
within the same run, and a :class:`Stage2Service` that runs over the Wave 1
seam and writes a contiguous stage-boundary checkpoint.

Invariants (research §4, §6.2):

* Stage 2 receives ONLY the frozen ``ResearchInputSnapshot`` (read-only) and
  server-produced candidate/evaluation/gate evidence read from the Phase 47
  ledger. The model authors nothing it later consumes.
* The output schema (``factor-stage2-v1``) carries caveats + a bounded advisory
  recommendation and NO mutable field. ``disposition`` is the only "action" and
  it is advisory -- ``propose_new_run`` never spawns a run (no autonomous loop).
* Every cited ``evidence_refs[].id`` resolves within the same run
  (referential integrity, OQ-2: a ``gate`` ref cites the admission verdict ROW
  bound to a candidate in the run). An unresolvable or cross-run reference is a
  permanent validation failure with no fallback review.
* A provider/decode/referential failure produces ZERO validated rows and a
  failed analysis attempt -- there is no code path that synthesizes a fallback
  review (SC4, ``hypotheses.py:157-160`` pattern).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal

from app.research.run_contract import (
    MAX_JSON_STRING_CHARS,
    canonical_bounded_json,
    validate_bounded_json,
)

STAGE_TWO_SCHEMA_VERSION = "factor-stage2-v1"
STAGE_TWO_PROMPT_TEMPLATE_VERSION = "factor-stage2-v1"

# Bounded output budget (reusing the MAX_JSON_* discipline, run_contract.py:25-28).
MAX_STAGE2_CAVEATS = 12
MAX_STAGE2_CLAIM_CHARS = 2000
MAX_STAGE2_RATIONALE_CHARS = 2000
MAX_STAGE2_FOLLOW_UP_DIMS = 8
MAX_STAGE2_EVIDENCE_REFS = 16

_EVIDENCE_REF_KINDS: frozenset[str] = frozenset(
    {"candidate", "evaluation", "gate", "artifact"}
)
_CAVEAT_KINDS: frozenset[str] = frozenset(
    {
        "missing_assumption",
        "contradictory_metric",
        "gate_failure",
        "narrow_coverage",
        "redundancy",
    }
)
_DISPOSITIONS: frozenset[str] = frozenset(
    {"inspect", "retain", "propose_new_run", "no_action"}
)

# Second-layer mutable-field rejection (T-48-03a). The primary defense is the
# closed ``extra='forbid'`` allowlist below; this set is the symmetric constraint
# to ``assert_admission_no_edit`` (alpha_scoring.py:479-505) so a model cannot
# smuggle authority through an aliased name. No allowed field name contains any
# of these as a substring, so the scan never rejects a well-formed payload.
MUTABLE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "expression",
        "metric",
        "threshold",
        "oos",
        "admission",
        "score",
        "override",
    }
)

_TOP_ALLOWED: frozenset[str] = frozenset({"schema_version", "caveats", "recommendation"})
_CAVEAT_ALLOWED: frozenset[str] = frozenset({"kind", "claim", "evidence_refs"})
_REF_ALLOWED: frozenset[str] = frozenset({"kind", "id"})
_RECOMMENDATION_ALLOWED: frozenset[str] = frozenset(
    {"disposition", "rationale", "follow_up_run_dims"}
)


def _sha256_hex(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not (text := value.strip()):
        raise ValueError(f"{field} is required")
    return text


def _reject_mutable_fields(node: object, path: str = "payload") -> None:
    """Reject any key whose name carries a mutable vocabulary token (T-48-03a).

    Runs before the closed allowlist so a smuggled authority field is reported
    with a precise ``forbidden mutable field`` reason. The scan is structural --
    it never inspects values, only keys -- so an oversized or oddly-typed value
    is still caught later by the allowlist decode.
    """
    if isinstance(node, Mapping):
        for key, child in node.items():
            key_text = str(key).lower()
            for token in MUTABLE_FIELD_NAMES:
                if token in key_text:
                    raise ValueError(
                        f"stage2 {path}.{key} is a forbidden mutable field"
                    )
            _reject_mutable_fields(child, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_mutable_fields(item, f"{path}[{index}]")


# ------------------------------------------------------------------
# Bounded request (frozen snapshot ref + read-only server evidence)
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """One cited evidence reference (resolves within the same run)."""

    kind: Literal["candidate", "evaluation", "gate", "artifact"]
    id: str


@dataclass(frozen=True, slots=True)
class Caveat:
    """One schema-valid Stage 2 caveat, linked to same-run evidence."""

    kind: Literal[
        "missing_assumption",
        "contradictory_metric",
        "gate_failure",
        "narrow_coverage",
        "redundancy",
    ]
    claim: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A bounded advisory recommendation (disposition is the only action)."""

    disposition: Literal["inspect", "retain", "propose_new_run", "no_action"]
    rationale: str
    follow_up_run_dims: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class ServerEvidence:
    """Read-only projection of the Phase 47 evidence ledger for one run.

    Assembled exclusively from server-owned reads (``list_candidates`` /
    ``list_alpha_fold_evidence`` / admission verdict rows / derived selection
    summary). The model authors nothing it consumes here.
    """

    candidates: tuple[Mapping[str, Any], ...]
    fold_evidence: tuple[Mapping[str, Any], ...]
    admission_verdicts: tuple[Mapping[str, Any], ...]
    selection_summary: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class StageTwoRequest:
    """Bounded Stage 2 input: a frozen snapshot ref + read-only server evidence."""

    snapshot_ref: Mapping[str, Any]
    evidence: ServerEvidence
    budget_hints: Mapping[str, Any]

    def __post_init__(self) -> None:
        for label, value in (
            ("snapshot_ref", self.snapshot_ref),
            ("budget_hints", self.budget_hints),
        ):
            if not isinstance(value, Mapping):
                raise ValueError(f"{label} must be a mapping")
            validate_bounded_json(value, f"StageTwoRequest.{label}")
        if not isinstance(self.evidence, ServerEvidence):
            raise ValueError("evidence must be a ServerEvidence projection")

    def as_request_scope(self) -> dict[str, Any]:
        """Bounded canonical request scope (provenance digest + prompt source).

        The full server evidence is reduced to bounded counts + the frozen
        snapshot digests so the prompt stays within the MAX_JSON_* bounds; the
        authoritative evidence rows live in the Phase 47 ledger, not the prompt.
        """
        candidates = tuple(self.evidence.candidates)
        return {
            "snapshot_ref": dict(self.snapshot_ref),
            "evidence_counts": {
                "candidates": len(candidates),
                "fold_evidence": len(self.evidence.fold_evidence),
                "admission_verdicts": len(self.evidence.admission_verdicts),
                "has_selection_summary": self.evidence.selection_summary is not None,
            },
            "candidate_ids": [str(c.get("id")) for c in candidates if c.get("id")],
            "budget_hints": dict(self.budget_hints),
        }


# ------------------------------------------------------------------
# Strict versioned output schema (extra='forbid' at every nesting level)
# ------------------------------------------------------------------


def _decode_evidence_ref(item: object, index: int) -> EvidenceRef:
    if not isinstance(item, dict):
        raise ValueError(
            f"stage2 caveat evidence_ref[{index}] must be a JSON object"
        )
    unknown = sorted(set(item) - _REF_ALLOWED)
    missing = sorted(_REF_ALLOWED - set(item))
    if unknown:
        raise ValueError(
            f"stage2 caveat evidence_ref[{index}] has unsupported field(s): "
            f"{', '.join(unknown)}"
        )
    if missing:
        raise ValueError(
            f"stage2 caveat evidence_ref[{index}] is missing field(s): "
            f"{', '.join(missing)}"
        )
    kind = item["kind"]
    if kind not in _EVIDENCE_REF_KINDS:
        raise ValueError(
            f"stage2 caveat evidence_ref[{index}].kind must be one of "
            f"{sorted(_EVIDENCE_REF_KINDS)}"
        )
    ref_id = item["id"]
    if not isinstance(ref_id, str) or not ref_id.strip():
        raise ValueError(
            f"stage2 caveat evidence_ref[{index}].id is required"
        )
    if len(ref_id) > MAX_JSON_STRING_CHARS:
        raise ValueError(
            f"stage2 caveat evidence_ref[{index}].id exceeds the maximum length"
        )
    return EvidenceRef(kind=kind, id=ref_id.strip())  # type: ignore[arg-type]


def _decode_caveat(item: object, index: int) -> Caveat:
    if not isinstance(item, dict):
        raise ValueError(f"stage2 caveat[{index}] must be a JSON object")
    unknown = sorted(set(item) - _CAVEAT_ALLOWED)
    missing = sorted(_CAVEAT_ALLOWED - set(item))
    if unknown:
        raise ValueError(
            f"stage2 caveat[{index}] has unsupported field(s): {', '.join(unknown)}"
        )
    if missing:
        raise ValueError(
            f"stage2 caveat[{index}] is missing field(s): {', '.join(missing)}"
        )
    kind = item["kind"]
    if kind not in _CAVEAT_KINDS:
        raise ValueError(
            f"stage2 caveat[{index}].kind must be one of {sorted(_CAVEAT_KINDS)}"
        )
    claim = _required_text(item["claim"], f"stage2 caveat[{index}].claim")
    if len(claim) > MAX_STAGE2_CLAIM_CHARS:
        raise ValueError(
            f"stage2 caveat[{index}].claim exceeds the maximum length"
        )
    refs_raw = item["evidence_refs"]
    if not isinstance(refs_raw, list):
        raise ValueError(f"stage2 caveat[{index}].evidence_refs must be an array")
    if not refs_raw:
        raise ValueError(
            f"stage2 caveat[{index}].evidence_refs must link to at least one "
            f"same-run evidence id"
        )
    if len(refs_raw) > MAX_STAGE2_EVIDENCE_REFS:
        raise ValueError(
            f"stage2 caveat[{index}].evidence_refs exceed the maximum of "
            f"{MAX_STAGE2_EVIDENCE_REFS}"
        )
    refs = tuple(_decode_evidence_ref(ref, index) for index, ref in enumerate(refs_raw))
    return Caveat(kind=kind, claim=claim, evidence_refs=refs)  # type: ignore[arg-type]


def _decode_recommendation(item: object) -> Recommendation:
    if not isinstance(item, dict):
        raise ValueError("stage2 recommendation must be a JSON object")
    unknown = sorted(set(item) - _RECOMMENDATION_ALLOWED)
    missing = sorted(_RECOMMENDATION_ALLOWED - set(item))
    if unknown:
        raise ValueError(
            f"stage2 recommendation has unsupported field(s): {', '.join(unknown)}"
        )
    if missing:
        raise ValueError(
            f"stage2 recommendation is missing field(s): {', '.join(missing)}"
        )
    disposition = item["disposition"]
    if disposition not in _DISPOSITIONS:
        raise ValueError(
            f"stage2 recommendation.disposition must be one of {sorted(_DISPOSITIONS)}"
        )
    rationale = _required_text(item["rationale"], "stage2 recommendation.rationale")
    if len(rationale) > MAX_STAGE2_RATIONALE_CHARS:
        raise ValueError(
            "stage2 recommendation.rationale exceeds the maximum length"
        )
    follow_up = item["follow_up_run_dims"]
    if follow_up is None:
        follow_up_dims: tuple[str, ...] | None = None
    elif isinstance(follow_up, list):
        if disposition != "propose_new_run":
            raise ValueError(
                "stage2 recommendation.follow_up_run_dims may only accompany "
                "disposition='propose_new_run'"
            )
        if not follow_up:
            raise ValueError(
                "stage2 recommendation.follow_up_run_dims must be non-empty when present"
            )
        if len(follow_up) > MAX_STAGE2_FOLLOW_UP_DIMS:
            raise ValueError(
                f"stage2 recommendation.follow_up_run_dims exceed the maximum of "
                f"{MAX_STAGE2_FOLLOW_UP_DIMS}"
            )
        if any(not isinstance(dim, str) or not dim.strip() for dim in follow_up):
            raise ValueError(
                "stage2 recommendation.follow_up_run_dims must be an array of text"
            )
        follow_up_dims = tuple(dim.strip() for dim in follow_up)
    else:
        raise ValueError(
            "stage2 recommendation.follow_up_run_dims must be an array or null"
        )
    return Recommendation(
        disposition=disposition,  # type: ignore[arg-type]
        rationale=rationale,
        follow_up_run_dims=follow_up_dims,
    )


def decode_stage2_payload(raw: str) -> tuple[tuple[Caveat, ...], Recommendation]:
    """Decode provider text into schema-validated caveats + a recommendation.

    Generalizes ``_decode_provider_draft`` (hypotheses.py:80-101) to the Stage 2
    schema. Unknown/missing fields at every nesting level raise a field-specific
    ``ValueError`` (the caller classifies it as a permanent
    ``schema_violation`` / ``malformed_json``). A second-layer mutable-field scan
    (T-48-03a) rejects any key carrying a mutable vocabulary token before the
    closed allowlist decode. Pure: it never calls the provider and never mutates
    its input.
    """
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("provider returned malformed JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("stage2 payload must be a JSON object")
    _reject_mutable_fields(payload)
    unknown = sorted(set(payload) - _TOP_ALLOWED)
    missing = sorted(_TOP_ALLOWED - set(payload))
    if unknown:
        raise ValueError(f"stage2 payload has unsupported field(s): {', '.join(unknown)}")
    if missing:
        raise ValueError(f"stage2 payload is missing field(s): {', '.join(missing)}")
    if payload["schema_version"] != STAGE_TWO_SCHEMA_VERSION:
        raise ValueError("stage2 schema_version mismatch")
    caveats_raw = payload["caveats"]
    if not isinstance(caveats_raw, list):
        raise ValueError("stage2 caveats must be an array")
    if len(caveats_raw) > MAX_STAGE2_CAVEATS:
        raise ValueError(
            f"stage2 caveats exceed the maximum of {MAX_STAGE2_CAVEATS}"
        )
    caveats = tuple(_decode_caveat(item, index) for index, item in enumerate(caveats_raw))
    recommendation = _decode_recommendation(payload["recommendation"])
    return caveats, recommendation
