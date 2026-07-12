"""Narrow advanced API routes with server-derived promotion identity."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/advanced", tags=["advanced"])


class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rationale: str = Field(min_length=10, max_length=4_000)


@router.post("/evolution/candidates/{candidate_id}/promote")
def promote_candidate(candidate_id: str, payload: PromotionRequest, request: Request) -> dict[str, object]:
    service = request.app.state.evolution_service
    principal = getattr(request.state, "reviewer_principal", None)
    try:
        return service.approve(candidate_id=candidate_id, principal=principal, rationale=payload.rationale)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="promotion conflict or incomplete gates") from error
