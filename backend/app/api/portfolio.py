"""Authenticated account, position, and quote-projected portfolio endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.operational.repository import OperationalRepository
from app.portfolio.service import PortfolioService


router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _repository(request: Request) -> OperationalRepository:
    return request.app.state.operational


def _service(request: Request) -> PortfolioService:
    return request.app.state.portfolio_service


def _notify_portfolio_updated(request: Request) -> None:
    notifier = getattr(request.app.state.quote_service, "notify_portfolio_updated", None)
    if callable(notifier):
        notifier()


class AccountCreate(BaseModel):
    name: str
    available_funds: float = 0


class AccountUpdate(BaseModel):
    name: str | None = None
    available_funds: float | None = None
    enabled: bool | None = None


class PositionCreate(BaseModel):
    account_id: int
    instrument_symbol: str
    cost_price: float
    quantity: float
    invested_amount: float
    trading_style: str


class PositionUpdate(BaseModel):
    instrument_symbol: str | None = None
    cost_price: float | None = None
    quantity: float | None = None
    invested_amount: float | None = None
    trading_style: str | None = None
    enabled: bool | None = None


def _invalid(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.get("/accounts")
def list_accounts(request: Request, include_archived: bool = False) -> dict[str, list[dict[str, Any]]]:
    return {"accounts": _repository(request).list_accounts(include_archived=include_archived)}


@router.post("/accounts", status_code=201)
def create_account(payload: AccountCreate, request: Request) -> dict[str, Any]:
    try:
        account = _repository(request).create_account(**payload.model_dump())
    except ValueError as error:
        raise _invalid(error) from error
    _notify_portfolio_updated(request)
    return {"account": account}


@router.put("/accounts/{account_id}")
def update_account(account_id: int, payload: AccountUpdate, request: Request) -> dict[str, Any]:
    try:
        account = _repository(request).update_account(account_id, **payload.model_dump(exclude_unset=True))
    except ValueError as error:
        raise _invalid(error) from error
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    _notify_portfolio_updated(request)
    return {"account": account}


@router.post("/accounts/{account_id}/archive")
def archive_account(account_id: int, request: Request) -> dict[str, Any]:
    account = _repository(request).archive_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    _notify_portfolio_updated(request)
    return {"account": account}


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, request: Request) -> dict[str, bool]:
    repository = _repository(request)
    if repository.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    if not repository.delete_account(account_id):
        raise HTTPException(status_code=400, detail="account has positions or operational history and must be archived")
    _notify_portfolio_updated(request)
    return {"ok": True}


@router.get("/positions")
def list_positions(
    request: Request,
    account_id: int | None = None,
    include_archived: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    return {"positions": _service(request).valued_positions(account_id=account_id, include_archived=include_archived)}


@router.post("/positions", status_code=201)
def create_position(payload: PositionCreate, request: Request) -> dict[str, Any]:
    try:
        position = _repository(request).create_position(**payload.model_dump())
    except ValueError as error:
        raise _invalid(error) from error
    _notify_portfolio_updated(request)
    return {"position": position}


@router.put("/positions/{position_id}")
def update_position(position_id: int, payload: PositionUpdate, request: Request) -> dict[str, Any]:
    try:
        position = _repository(request).update_position(position_id, **payload.model_dump(exclude_unset=True))
    except ValueError as error:
        raise _invalid(error) from error
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")
    _notify_portfolio_updated(request)
    return {"position": position}


@router.post("/positions/{position_id}/archive")
def archive_position(position_id: int, request: Request) -> dict[str, Any]:
    position = _repository(request).archive_position(position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")
    _notify_portfolio_updated(request)
    return {"position": position}


@router.delete("/positions/{position_id}")
def delete_position(position_id: int, request: Request) -> dict[str, bool]:
    repository = _repository(request)
    if repository.get_position(position_id) is None:
        raise HTTPException(status_code=404, detail="position not found")
    if not repository.delete_position(position_id):
        raise HTTPException(status_code=400, detail="position has operational history and must be archived")
    _notify_portfolio_updated(request)
    return {"ok": True}


@router.get("/summary")
def portfolio_summary(
    request: Request,
    account_id: int | None = None,
    include_archived: bool = False,
) -> dict[str, Any]:
    if account_id is not None and _repository(request).get_account(account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    return _service(request).portfolio_summary(account_id=account_id, include_archived=include_archived)
