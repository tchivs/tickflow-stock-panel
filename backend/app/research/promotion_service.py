"""Phase 49 wave 1 — Promotion Ticket: create, bind, refresh/expire/conflict.

A ``PromotionTicket`` is a frozen value object bound, at issue time, to the
complete candidate/evidence/policy triple (AF-REQ-15 SC1). Issue gathers every
binding from frozen/append-only rows plus the single live admission policy
fingerprint — it NEVER re-computes (R2). Refresh re-reads those same persisted
immutable facts and re-verifies them byte-for-byte, routing divergence into the
ratified expire (re-issueable) vs conflict (hard reject) taxonomy (SC2
expire/conflict half). Consume (49-02) atomically flips an issued ticket to
``consumed`` while minting the formal ``FactorRevision`` + catalog entry; the
partial consumed-candidate unique index enforces at-most-one revision per
candidate even across distinct tickets.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.research.run_contract import digest_bytes

# NOTE: admission is imported lazily inside the functions that need it. A
# top-level import would close the cycle admission -> factor_registry ->
# repository -> promotion_service -> admission (factor_registry imports
# repository at module load).

# The selection-OOS status bound when the reserved OOS fold evidence exists for
# the candidate (set by ``evaluate_selection_oos``). Refresh re-asserts it.
_SELECTION_OOS_EVALUATED = "evaluated"

# Provenance kind marking a formal catalog factor minted by an explicit,
# reviewed promotion consume (Phase 49). Only ``kind != alpha_exploratory``
# revisions appear in ``FactorRegistry.list_current`` — so a formal
# ``alpha_promoted`` revision is the ONLY path that produces a catalog factor
# (SC3: unreviewed output is structurally absent from the formal catalog).
ALPHA_PROMOTED_KIND: str = "alpha_promoted"

# Catalog discriminator for the promotion ExperimentSnapshot (mirrors the
# ``admitted-factor`` summary_kind used by ``record_admitted_factor_summary``).
_PROMOTION_SUMMARY_KIND = "promoted-factor"


@dataclass(frozen=True, slots=True)
class PromotionTicket:
    """A frozen promotion ticket bound to the complete evidence triple."""

    id: str
    run_id: str
    candidate_id: str
    candidate_digest: str
    canonical_expression: str
    ast_signature: str
    shape_signature: str
    dsl_version: str
    stage1_proposal_digest: str | None
    stage2_review_digest: str | None
    snapshot_sha256: str
    manifest_sha256: str
    vocabulary_fingerprint: str
    grammar_fingerprint: str
    membership_fingerprint: str
    data_fingerprint: str
    admission_verdict_id: str | None
    admission_verdict: str
    policy_version: str
    policy_fingerprint: str
    gate_trail_digest: str | None
    selection_oos_status: str
    selection_oos_fold_evidence_id: str | None
    reviewer: str
    issued_at: str
    expires_at: str
    idempotency_key: str
    status: str
    conflict_reason_json: Mapping[str, Any] | None
    consumed_at: str | None
    produced_factor_revision_id: str | None
    created_at: str

    @classmethod
    def from_record(cls, row: Mapping[str, Any] | Any) -> PromotionTicket:
        """Materialize a ticket from a persisted row (mirrors FactorRevision)."""
        import json

        conflict_raw = row["conflict_reason_json"]
        conflict = (
            json.loads(conflict_raw) if isinstance(conflict_raw, str) else conflict_raw
        )
        return cls(
            id=row["id"],
            run_id=row["run_id"],
            candidate_id=row["candidate_id"],
            candidate_digest=row["candidate_digest"],
            canonical_expression=row["canonical_expression"],
            ast_signature=row["ast_signature"],
            shape_signature=row["shape_signature"],
            dsl_version=row["dsl_version"],
            stage1_proposal_digest=row["stage1_proposal_digest"],
            stage2_review_digest=row["stage2_review_digest"],
            snapshot_sha256=row["snapshot_sha256"],
            manifest_sha256=row["manifest_sha256"],
            vocabulary_fingerprint=row["vocabulary_fingerprint"],
            grammar_fingerprint=row["grammar_fingerprint"],
            membership_fingerprint=row["membership_fingerprint"],
            data_fingerprint=row["data_fingerprint"],
            admission_verdict_id=row["admission_verdict_id"],
            admission_verdict=row["admission_verdict"],
            policy_version=row["policy_version"],
            policy_fingerprint=row["policy_fingerprint"],
            gate_trail_digest=row["gate_trail_digest"],
            selection_oos_status=row["selection_oos_status"],
            selection_oos_fold_evidence_id=row["selection_oos_fold_evidence_id"],
            reviewer=row["reviewer"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            idempotency_key=row["idempotency_key"],
            status=row["status"],
            conflict_reason_json=conflict,
            consumed_at=row["consumed_at"],
            produced_factor_revision_id=row["produced_factor_revision_id"],
            created_at=row["created_at"],
        )


class PromotionTicketUnavailable(RuntimeError):
    """A ticket cannot be issued: a required frozen/admission/OOS fact is missing."""


class PromotionTicketExpired(RuntimeError):
    """Refresh found a re-issueable expiry (wall clock or a superseding proposal)."""

    def __init__(self, reason: Mapping[str, Any]) -> None:
        super().__init__(str(dict(reason)))
        self.reason = dict(reason)


class PromotionTicketConflict(RuntimeError):
    """Refresh found a hard-reject conflict: a bound evidence value drifted."""

    def __init__(self, reason: Mapping[str, Any]) -> None:
        super().__init__(str(dict(reason)))
        self.reason = dict(reason)


# ---------------------------------------------------------------------
# Helpers — pure reads of frozen/append-only facts (no re-computation).
# ---------------------------------------------------------------------


def _admission_verdict_for_candidate(
    repo: Any, *, run_id: str, candidate_id: str
) -> dict[str, Any] | None:
    """Read the admission verdict row bound to ``(run_id, candidate_id)``."""
    for verdict in repo.list_admission_verdicts_for_run(run_id):
        if verdict.get("candidate_id") == candidate_id:
            return verdict
    return None


def _latest_stage1_digest(
    repo: Any, *, run_id: str, canonical_expression: str
) -> str | None:
    """Read the latest Stage 1 proposal digest for a candidate expression."""
    matches = [
        proposal
        for proposal in repo.list_stage1_proposals(run_id)
        if proposal.get("canonical_expression") == canonical_expression
    ]
    if not matches:
        return None
    return matches[-1]["proposal_digest"]


def _selection_oos_evidence(
    repo: Any, *, run_id: str, candidate_digest: str
) -> dict[str, Any] | None:
    """Read the reserved selection-OOS fold evidence row for a candidate."""
    rows = repo.list_alpha_fold_evidence(
        run_id=run_id, candidate_digest=candidate_digest, is_oos=True
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------
# issue_promotion_ticket — bind the full evidence triple (SC1).
# ---------------------------------------------------------------------


def issue_promotion_ticket(
    repo: Any,
    *,
    run_id: str,
    candidate_id: str,
    reviewer: str,
    expires_at: str,
    idempotency_key: str,
) -> PromotionTicket:
    """Issue a ticket bound to the complete candidate/evidence/policy triple.

    Every binding is sourced from a persisted row or a live module constant —
    there is NO ``run_admission``, panel load, chain compute, or scoring call
    (R2). Fail-closed: any missing frozen/admission/OOS/draft fact raises
    :class:`PromotionTicketUnavailable` and writes NO ticket.
    """
    import uuid

    candidate = repo.get_candidate_attempt(run_id, candidate_id)
    if candidate is None or candidate.get("status") != "admitted":
        raise PromotionTicketUnavailable("candidate is not admitted")

    snapshot = repo.get_run_snapshot(run_id)
    if snapshot is None:
        raise PromotionTicketUnavailable("frozen input snapshot is missing")

    verdict = _admission_verdict_for_candidate(repo, run_id=run_id, candidate_id=candidate_id)
    if verdict is None or verdict.get("verdict") != "admitted":
        raise PromotionTicketUnavailable("candidate has no admitted verdict")

    oos = _selection_oos_evidence(
        repo, run_id=run_id, candidate_digest=candidate["candidate_digest"]
    )
    if oos is None:
        raise PromotionTicketUnavailable("candidate has no selection-OOS evidence")

    stage1_digest = _latest_stage1_digest(
        repo, run_id=run_id, canonical_expression=candidate["canonical_expression"]
    )

    from app.research.admission import ADMISSION_POLICY_FINGERPRINT

    return repo.issue_promotion_ticket(
        ticket_id="aptk_" + uuid.uuid4().hex,
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_digest=candidate["candidate_digest"],
        canonical_expression=candidate["canonical_expression"],
        ast_signature=candidate["ast_signature"],
        shape_signature=candidate["shape_signature"],
        dsl_version=candidate["dsl_version"],
        stage1_proposal_digest=stage1_digest,
        stage2_review_digest=None,
        snapshot_sha256=snapshot["snapshot_sha256"],
        manifest_sha256=snapshot["manifest_sha256"],
        vocabulary_fingerprint=snapshot["vocabulary_fingerprint"],
        grammar_fingerprint=snapshot["grammar_fingerprint"],
        membership_fingerprint=snapshot["membership_fingerprint"],
        data_fingerprint=snapshot["data_fingerprint"],
        admission_verdict_id=verdict["id"],
        admission_verdict=verdict["verdict"],
        policy_version=verdict["policy_version"],
        policy_fingerprint=ADMISSION_POLICY_FINGERPRINT,
        gate_trail_digest=digest_bytes(verdict["gates"]),
        selection_oos_status=_SELECTION_OOS_EVALUATED,
        selection_oos_fold_evidence_id=oos["id"],
        reviewer=reviewer,
        issued_at=repo._now(),
        expires_at=expires_at,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------
# refresh_promotion_ticket — re-read + re-verify, expire/conflict (SC2).
# ---------------------------------------------------------------------


def refresh_promotion_ticket(repo: Any, ticket_id: str) -> PromotionTicket:
    """Re-read and re-verify every bound immutable fact (plus the live policy).

    Performs ZERO re-computation (R2): no ``run_admission``, no panel load, no
    chain compute, no scoring. Divergence is routed into the ratified taxonomy
    — wall-clock / superseding proposal ⇒ ``expired`` (re-issueable); any
    candidate/snapshot/manifest/policy/vocabulary/grammar/membership/verdict/
    OOS/draft drift ⇒ ``conflicted`` (hard reject). A terminal ticket is
    returned unchanged; a valid current ticket is returned unchanged.
    """
    ticket = repo.get_promotion_ticket(ticket_id)
    if ticket is None:
        raise PromotionTicketUnavailable("promotion ticket does not exist")
    if ticket.status != "issued":
        return ticket

    # (2) Expiry first — re-issueable.
    if repo._now() > ticket.expires_at:
        reason = {"kind": "expired", "binding": "expires_at", "expires_at": ticket.expires_at}
        repo.set_promotion_ticket_status(
            ticket_id=ticket_id, status="expired", conflict_reason_json=reason
        )
        raise PromotionTicketExpired(reason)

    if ticket.stage1_proposal_digest is not None:
        latest = _latest_stage1_digest(
            repo, run_id=ticket.run_id, canonical_expression=ticket.canonical_expression
        )
        if latest is not None and latest != ticket.stage1_proposal_digest:
            reason = {
                "kind": "expired",
                "binding": "stage1_proposal_digest",
                "expected": ticket.stage1_proposal_digest,
                "observed": latest,
            }
            repo.set_promotion_ticket_status(
                ticket_id=ticket_id, status="expired", conflict_reason_json=reason
            )
            raise PromotionTicketExpired(reason)

    # (3) Conflict checks — hard reject. Any failure terminalizes the ticket.
    conflict = _verify_conflicts(repo, ticket)
    if conflict is not None:
        repo.set_promotion_ticket_status(
            ticket_id=ticket_id, status="conflicted", conflict_reason_json=conflict
        )
        raise PromotionTicketConflict(conflict)

    # (4) All re-verify — return the unchanged issued ticket.
    return ticket


def _verify_conflicts(repo: Any, ticket: PromotionTicket) -> Mapping[str, Any] | None:
    """Re-verify every bound fact; return a conflict reason mapping or None."""
    # Frozen context (snapshot + component digests) re-read from the append-only
    # snapshot record and compared byte-for-byte to the bound values.
    snapshot = repo.get_run_snapshot(ticket.run_id)
    if snapshot is None:
        return {"kind": "conflict", "binding": "snapshot", "reason": "snapshot_missing"}
    for binding in (
        "snapshot_sha256",
        "manifest_sha256",
        "vocabulary_fingerprint",
        "grammar_fingerprint",
        "membership_fingerprint",
        "data_fingerprint",
    ):
        observed = snapshot[binding]
        expected = getattr(ticket, binding)
        if observed != expected:
            return {
                "kind": "conflict",
                "binding": binding,
                "expected": expected,
                "observed": observed,
            }

    # Candidate identity re-read from the append-only candidate ledger.
    candidate = repo.get_candidate_attempt(ticket.run_id, ticket.candidate_id)
    if candidate is None:
        return {"kind": "conflict", "binding": "candidate", "reason": "candidate_missing"}
    for binding in ("candidate_digest", "canonical_expression", "ast_signature"):
        observed = candidate[binding]
        expected = getattr(ticket, binding)
        if observed != expected:
            return {
                "kind": "conflict",
                "binding": binding,
                "expected": expected,
                "observed": observed,
            }

    # The ONE live check: the admission policy code may have drifted between
    # issue and refresh. AdmissionPolicyMismatchError ⇒ conflict.
    from app.research.admission import (
        AdmissionPolicyMismatchError,
        admission_policy_fingerprint,
        verify_admission_policy_fingerprint,
    )

    try:
        verify_admission_policy_fingerprint(ticket.policy_fingerprint)
    except AdmissionPolicyMismatchError:
        return {
            "kind": "conflict",
            "binding": "policy_fingerprint",
            "expected": ticket.policy_fingerprint,
            "observed": admission_policy_fingerprint(),
        }

    # Admission verdict still admitted with matching policy_version + gate trail.
    verdict = _admission_verdict_for_candidate(
        repo, run_id=ticket.run_id, candidate_id=ticket.candidate_id
    )
    if verdict is None:
        return {"kind": "conflict", "binding": "admission_verdict", "reason": "verdict_missing"}
    if verdict["id"] != ticket.admission_verdict_id:
        return {
            "kind": "conflict",
            "binding": "admission_verdict_id",
            "expected": ticket.admission_verdict_id,
            "observed": verdict["id"],
        }
    if verdict["verdict"] != ticket.admission_verdict:
        return {
            "kind": "conflict",
            "binding": "admission_verdict",
            "expected": ticket.admission_verdict,
            "observed": verdict["verdict"],
        }
    if verdict["policy_version"] != ticket.policy_version:
        return {
            "kind": "conflict",
            "binding": "policy_version",
            "expected": ticket.policy_version,
            "observed": verdict["policy_version"],
        }
    gate_digest = digest_bytes(verdict["gates"])
    if ticket.gate_trail_digest is None or gate_digest != ticket.gate_trail_digest:
        return {
            "kind": "conflict",
            "binding": "gate_trail_digest",
            "expected": ticket.gate_trail_digest,
            "observed": gate_digest,
        }

    # Selection-OOS status + evidence id re-asserted from the append-only fold
    # evidence ledger.
    oos = _selection_oos_evidence(
        repo, run_id=ticket.run_id, candidate_digest=ticket.candidate_digest
    )
    if oos is None:
        return {
            "kind": "conflict",
            "binding": "selection_oos_status",
            "reason": "selection_oos_evidence_missing",
        }
    if oos["id"] != ticket.selection_oos_fold_evidence_id:
        return {
            "kind": "conflict",
            "binding": "selection_oos_fold_evidence_id",
            "expected": ticket.selection_oos_fold_evidence_id,
            "observed": oos["id"],
        }
    if ticket.selection_oos_status != _SELECTION_OOS_EVALUATED:
        return {
            "kind": "conflict",
            "binding": "selection_oos_status",
            "expected": _SELECTION_OOS_EVALUATED,
            "observed": ticket.selection_oos_status,
        }

    # Issued-draft digests re-compared against the persisted draft rows. A
    # bound Stage 1 digest must still be present among the append-only proposals
    # (supersession is an expire case, handled above).
    if ticket.stage1_proposal_digest is not None:
        digests = {
            proposal["proposal_digest"]
            for proposal in repo.list_stage1_proposals(ticket.run_id)
            if proposal.get("canonical_expression") == ticket.canonical_expression
        }
        if ticket.stage1_proposal_digest not in digests:
            return {
                "kind": "conflict",
                "binding": "stage1_proposal_digest",
                "expected": ticket.stage1_proposal_digest,
                "reason": "issued_draft_digest_not_found",
            }

    return None

# ---------------------------------------------------------------------
# consume_promotion_ticket — atomic consume → formal FactorRevision (49-02).
# ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PromotionTicketConsumed:
    """The outcome of consuming a ticket: the formal revision + catalog handoff.

    ``revision`` is the newly-minted (or, on idempotent reconnect, the existing)
    formal ``FactorRevision``. ``experiment_id`` is the promotion catalog
    snapshot (``None`` on reconnect, where only the revision id is persisted on
    the ticket).
    """

    revision: Any  # FactorRevision (typed lazily to avoid an import cycle)
    ticket_id: str
    experiment_id: str | None


def _mint_promoted_factor(
    repo: Any, registry: Any, catalog: Any, *, ticket: PromotionTicket
) -> PromotionTicketConsumed:
    """Step 6 of consume: mint the formal revision + snapshot and flip consumed.

    Resolves the exploratory revision (cited as ``source_exploratory_revision_id``),
    mints a NEW formal factor (``revision_number=1``, ``alpha_promoted``) via the
    atomic repository handoff — NOT ``revise_factor`` on the exploratory
    factor_id (OQ-1) — and records the promotion ``ExperimentSnapshot`` bound to
    ``originating_run_id='promotion:{ticket_id}'`` (R6). The mint + flip share
    ONE ``BEGIN IMMEDIATE`` so the partial consumed-candidate unique index is the
    final at-most-one gate (T-49-02a): a losing concurrent consume rolls back its
    uncommitted revision + snapshot and this ticket goes to ``conflicted``.

    Re-reads verdicts; it does NOT re-compute (R2). The formal revision's parsed
    features are sourced from the exploratory revision (the same expression) so
    no DSL parse/re-score is performed on the promotion path.
    """
    import uuid

    from app.research.catalog import FactorEvidencePackage
    from app.research.factor_registry import FactorRevision

    exploratory = registry.find_exploratory_revision(
        ticket.run_id, ticket.candidate_digest
    )
    if exploratory is None:
        raise PromotionTicketUnavailable("source exploratory revision is missing")
    snapshot = repo.get_run_snapshot(ticket.run_id)
    if snapshot is None:
        raise PromotionTicketUnavailable("frozen input snapshot is missing")

    factor_id = uuid.uuid4().hex
    revision_id = uuid.uuid4().hex
    experiment_id = uuid.uuid4().hex
    provenance = {
        "kind": ALPHA_PROMOTED_KIND,
        "source_run_id": ticket.run_id,
        "candidate_id": ticket.candidate_id,
        "candidate_digest": ticket.candidate_digest,
        "source_exploratory_revision_id": exploratory.id,
        "admission_verdict_id": ticket.admission_verdict_id,
        "selection_oos_fold_evidence_id": ticket.selection_oos_fold_evidence_id,
        "promotion_ticket_id": ticket.id,
        "reviewer": ticket.reviewer,
    }
    metrics = {
        "summary_kind": _PROMOTION_SUMMARY_KIND,
        "admission_verdict": {
            "verdict_id": ticket.admission_verdict_id,
            "verdict": ticket.admission_verdict,
            "policy_version": ticket.policy_version,
            "gate_trail_digest": ticket.gate_trail_digest,
            "input_snapshot_sha256": ticket.snapshot_sha256,
        },
        "selection_oos": {
            "status": ticket.selection_oos_status,
            "fold_evidence_id": ticket.selection_oos_fold_evidence_id,
        },
        "factor_signature": {
            "ast_signature": exploratory.ast_signature,
            "shape_signature": exploratory.shape_signature,
        },
        "factor_lineage": {
            "factor_id": factor_id,
            "revision_id": revision_id,
            "revision_number": 1,
        },
    }
    # The trusted boundary payload structures the package before the atomic
    # INSERT; persistence is one transaction with the ticket flip (T-49-02a).
    package = FactorEvidencePackage(
        evaluation_run_id=f"promotion:{ticket.id}",
        factor_revision_id=revision_id,
        resolved_config=snapshot["snapshot"],
        input_manifest=snapshot["manifest"],
        metrics=metrics,
        prediction_signals={},
        artifacts=(),
        diagnostics={"summary_kind": _PROMOTION_SUMMARY_KIND},
    )
    result = repo.consume_promotion_ticket_atomic(
        ticket_id=ticket.id,
        factor_id=factor_id,
        revision_id=revision_id,
        experiment_id=experiment_id,
        name=f"alpha-promoted:{ticket.run_id}:{ticket.candidate_digest}",
        provenance=provenance,
        resolved_config=package.resolved_config,
        input_manifest=package.input_manifest,
        metrics=package.metrics,
        canonical_expression=ticket.canonical_expression,
        dsl_version=exploratory.dsl_version,
        ast_signature=exploratory.ast_signature,
        shape_signature=exploratory.shape_signature,
        fields=exploratory.fields,
        operators=exploratory.operators,
        functions=exploratory.functions,
    )
    outcome = result["outcome"]
    if outcome == "concurrent_loss":
        # A distinct ticket won this candidate; the mint rolled back.
        reason = {
            "kind": "conflict",
            "binding": "consumed_candidate_unique",
            "reason": "concurrent_consume",
        }
        repo.set_promotion_ticket_status(
            ticket_id=ticket.id, status="conflicted", conflict_reason_json=reason
        )
        raise PromotionTicketConflict(reason)
    if outcome == "terminal":
        raise PromotionTicketUnavailable("promotion ticket is no longer issued")
    if outcome == "consumed_reconnect":
        revision = registry.get_revision(result["revision_id"])
        if revision is None:
            raise PromotionTicketUnavailable("consumed revision is missing")
        return PromotionTicketConsumed(
            revision=revision, ticket_id=ticket.id, experiment_id=None
        )
    return PromotionTicketConsumed(
        revision=FactorRevision.from_record(result["revision"]),
        ticket_id=ticket.id,
        experiment_id=result["experiment_id"],
    )


def consume_promotion_ticket(
    repo: Any,
    registry: Any,
    catalog: Any,
    *,
    idempotency_key: str,
    _mint: Any = _mint_promoted_factor,
) -> PromotionTicketConsumed:
    """Atomically consume a current, exact-bound ticket into ONE formal revision.

    The §3.1 8-step transaction:
    (2) load the ticket by ``idempotency_key`` — fail-closed if absent;
    (3) idempotent reconnect — a consumed ticket returns its existing revision
        verbatim (no second mint);
    (4) an expired/conflicted ticket raises ``PromotionTicketUnavailable``;
    (5) re-verify every bound immutable fact + the live policy fingerprint
        (delegates to the 49-01 predicate) — expiry ⇒ ``PromotionTicketExpired``,
        divergence ⇒ ``PromotionTicketConflict``;
    (6-8) mint the formal ``FactorRevision`` + promotion snapshot and flip the
        ticket to ``consumed`` under ONE ``BEGIN IMMEDIATE``; the partial
        consumed-candidate unique index is the final at-most-one gate.

    Performs ZERO re-computation (R2). The server-resolved ``reviewer`` bound at
    issue time is the only identity carried into the formal provenance.
    """
    ticket = repo.get_promotion_ticket_by_key(idempotency_key)
    if ticket is None:
        raise PromotionTicketUnavailable("promotion ticket does not exist")
    if ticket.status == "consumed":
        # Idempotent reconnect (sequential repeat): return the existing revision.
        revision = registry.get_revision(ticket.produced_factor_revision_id)
        if revision is None:
            raise PromotionTicketUnavailable("consumed revision is missing")
        return PromotionTicketConsumed(
            revision=revision, ticket_id=ticket.id, experiment_id=None
        )
    if ticket.status != "issued":
        raise PromotionTicketUnavailable(f"promotion ticket is {ticket.status}")

    # (5a) Expiry — re-issueable (wall clock past expires_at).
    if repo._now() > ticket.expires_at:
        reason = {
            "kind": "expired",
            "binding": "expires_at",
            "expires_at": ticket.expires_at,
        }
        repo.set_promotion_ticket_status(
            ticket_id=ticket.id, status="expired", conflict_reason_json=reason
        )
        raise PromotionTicketExpired(reason)
    # (5b) Stage-1 supersession — re-issueable (a newer proposal displaced the
    # bound issued draft).
    if ticket.stage1_proposal_digest is not None:
        latest = _latest_stage1_digest(
            repo, run_id=ticket.run_id, canonical_expression=ticket.canonical_expression
        )
        if latest is not None and latest != ticket.stage1_proposal_digest:
            reason = {
                "kind": "expired",
                "binding": "stage1_proposal_digest",
                "expected": ticket.stage1_proposal_digest,
                "observed": latest,
            }
            repo.set_promotion_ticket_status(
                ticket_id=ticket.id, status="expired", conflict_reason_json=reason
            )
            raise PromotionTicketExpired(reason)
    # (5c) Conflict re-verify — hard reject (any bound fact drifted).
    conflict = _verify_conflicts(repo, ticket)
    if conflict is not None:
        repo.set_promotion_ticket_status(
            ticket_id=ticket.id, status="conflicted", conflict_reason_json=conflict
        )
        raise PromotionTicketConflict(conflict)

    # (6-8) Atomic mint + flip; concurrent_loss ⇒ conflicted (inside _mint).
    return _mint(repo, registry, catalog, ticket=ticket)


# Lexically clear alias for the research-only register action (SC4 'register').
register_research_factor = consume_promotion_ticket
