"""Principal-scoped issue + inspect + consume routes for research promotion tickets.

Routes resolve the shared promotion collaborators (``research_repository``,
``factor_registry``, ``experiment_catalog``) from ``app.state`` and never execute
SQL directly. The server-resolved principal is the only identity source;
cross-principal access returns the same 404 boundary as an unknown resource
(T-45-12). No route imports provider, factor evaluation, OOS (as a re-scoring
path), broker, order, portfolio, monitor, or live-execution collaborators — the
research-only action surface is inspect / register (AF-REQ-17 SC4).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.research.promotion_service import (
    PromotionTicketConflict,
    PromotionTicketExpired,
    PromotionTicketUnavailable,
    consume_promotion_ticket,
    issue_promotion_ticket,
)

router = APIRouter(prefix="/api/research", tags=["research-promotion"])

_KEY_PATTERN = r"^[A-Za-z0-9._:-]+$"


def _collaborators(request: Request) -> tuple[Any, Any, Any]:
    """Resolve (repo, registry, catalog) from app.state; 503 if uninitialized."""
    repo = getattr(request.app.state, "research_repository", None)
    registry = getattr(request.app.state, "factor_registry", None)
    catalog = getattr(request.app.state, "experiment_catalog", None)
    if repo is None or registry is None or catalog is None:
        raise HTTPException(
            status_code=503, detail="promotion service not initialized"
        )
    return repo, registry, catalog


def _principal(request: Request) -> str:
    """Resolve the server-owned principal from the host authentication context.

    The auth middleware sets ``request.state.reviewer_principal`` from the
    validated session; this is the only principal source (T-45-12).
    """
    principal = getattr(request.state, "reviewer_principal", None)
    if not isinstance(principal, str) or not principal:
        raise HTTPException(status_code=401, detail="authenticated principal required")
    return principal


def _ticket_projection(ticket: Any) -> dict[str, Any]:
    """Hand-built, deny-by-default read-only projection of a promotion ticket."""
    return {
        "id": ticket.id,
        "run_id": ticket.run_id,
        "candidate_id": ticket.candidate_id,
        "candidate_digest": ticket.candidate_digest,
        "canonical_expression": ticket.canonical_expression,
        "status": ticket.status,
        "reviewer": ticket.reviewer,
        "issued_at": ticket.issued_at,
        "expires_at": ticket.expires_at,
        "idempotency_key": ticket.idempotency_key,
        "admission_verdict": ticket.admission_verdict,
        "policy_version": ticket.policy_version,
        "selection_oos_status": ticket.selection_oos_status,
        "consumed_at": ticket.consumed_at,
        "produced_factor_revision_id": ticket.produced_factor_revision_id,
        "conflict_reason": (
            None if not ticket.conflict_reason_json else dict(ticket.conflict_reason_json)
        ),
        "created_at": ticket.created_at,
    }


class _StrictModel(BaseModel):
    """Reject undeclared fields at the trust boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PromotionTicketIssueRequest(_StrictModel):
    """Bounded researcher issue intent. The server binds the full evidence triple."""

    expires_at: str = Field(min_length=20, max_length=40)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=_KEY_PATTERN)


class PromotionTicketConsumeRequest(_StrictModel):
    """Bounded researcher register intent. The server resolves the ticket by key."""

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=_KEY_PATTERN)


class PromotionTicketDTO(BaseModel):
    """Safe public ticket projection — no policy internals, only bound digests."""

    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    candidate_id: str
    candidate_digest: str
    canonical_expression: str
    status: str
    reviewer: str
    issued_at: str
    expires_at: str
    idempotency_key: str
    admission_verdict: str
    policy_version: str
    selection_oos_status: str
    consumed_at: str | None = None
    produced_factor_revision_id: str | None = None
    conflict_reason: dict[str, Any] | None = None
    created_at: str


class PromotedFactorDTO(BaseModel):
    """The consumed formal revision + preserved lineage provenance."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    revision_id: str
    factor_id: str
    revision_number: int
    canonical_expression: str
    provenance: dict[str, Any]
    experiment_id: str | None = None


@router.post(
    "/runs/{run_id}/candidates/{candidate_id}/promotion-ticket",
    response_model=PromotionTicketDTO,
    status_code=201,
)
async def issue_promotion_ticket_route(
    request: Request,
    run_id: str,
    candidate_id: str,
    body: PromotionTicketIssueRequest,
) -> PromotionTicketDTO:
    """Issue one ticket bound to the server-resolved principal (SC1)."""
    repo, registry, catalog = _collaborators(request)
    principal = _principal(request)
    # Cross-principal access returns the same 404 boundary as an unknown run.
    if repo.get_alpha_run(run_id, principal=principal) is None:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"})
    try:
        ticket = issue_promotion_ticket(
            repo,
            run_id=run_id,
            candidate_id=candidate_id,
            reviewer=principal,
            expires_at=body.expires_at,
            idempotency_key=body.idempotency_key,
        )
    except PromotionTicketUnavailable:
        raise HTTPException(
            status_code=422,
            detail={"code": "not_promotable", "reason": "candidate is not ready for promotion"},
        )
    return PromotionTicketDTO(**_ticket_projection(ticket))


@router.get(
    "/promotion-tickets/{ticket_id}",
    response_model=PromotionTicketDTO,
)
async def inspect_promotion_ticket_route(
    request: Request, ticket_id: str
) -> PromotionTicketDTO:
    """Return one principal-scoped ticket projection (SC4 'inspect')."""
    repo, _registry, _catalog = _collaborators(request)
    principal = _principal(request)
    ticket = repo.get_promotion_ticket(ticket_id)
    if ticket is None or ticket.reviewer != principal:
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    return PromotionTicketDTO(**_ticket_projection(ticket))


@router.post(
    "/promotion-tickets/{ticket_id}:consume",
    response_model=PromotedFactorDTO,
    status_code=200,
)
async def consume_promotion_ticket_route(
    request: Request,
    ticket_id: str,
    body: PromotionTicketConsumeRequest,
) -> PromotedFactorDTO:
    """Register one formal research factor from a current exact-bound ticket (SC4 'register')."""
    repo, registry, catalog = _collaborators(request)
    principal = _principal(request)
    scoped = repo.get_promotion_ticket_by_key(body.idempotency_key)
    if scoped is not None and scoped.reviewer != principal:
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    try:
        result = consume_promotion_ticket(
            repo, registry, catalog, idempotency_key=body.idempotency_key
        )
    except PromotionTicketUnavailable:
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    except PromotionTicketExpired as error:
        raise HTTPException(
            status_code=409, detail={"code": "expired", "reason": dict(error.reason)}
        )
    except PromotionTicketConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "conflict", "reason": dict(error.reason)}
        )
    return PromotedFactorDTO(
        ticket_id=result.ticket_id,
        revision_id=result.revision.id,
        factor_id=result.revision.factor_id,
        revision_number=result.revision.revision_number,
        canonical_expression=result.revision.canonical_expression,
        provenance=dict(result.revision.provenance),
        experiment_id=result.experiment_id,
    )
