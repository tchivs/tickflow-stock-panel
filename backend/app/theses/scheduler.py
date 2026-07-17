"""Bounded restart-safe scanner for per-condition Thesis evidence checks."""
from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ThesisDueScanner:
    """Lease and evaluate a bounded stable batch without owning evidence authority."""

    def __init__(
        self,
        *,
        repository: Any,
        service: Any,
        batch_limit: int = 32,
        lease_seconds: int = 60,
    ) -> None:
        if isinstance(batch_limit, bool) or not isinstance(batch_limit, int) or not 1 <= batch_limit <= 256:
            raise ValueError("batch_limit must be between 1 and 256")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 3_600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        self._repository = repository
        self._service = service
        self._batch_limit = batch_limit
        self._lease_seconds = lease_seconds

    def assert_ready(self) -> None:
        """Fail closed unless every bounded lease transition collaborator is present."""
        repository_methods = (
            "acquire_due_conditions",
            "get_condition",
            "complete_due_condition",
        )
        if any(not callable(getattr(self._repository, name, None)) for name in repository_methods):
            raise RuntimeError("thesis scanner collaborators are incomplete")
        if not callable(getattr(self._service, "evaluate_due_condition", None)):
            raise RuntimeError("thesis scanner collaborators are incomplete")

    def scan_once(self, *, now: datetime, owner: str) -> list[dict[str, Any]]:
        """Evaluate a bounded batch while isolating each retryable lease."""
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("now must be a timezone-aware datetime")
        self.assert_ready()
        current = now.astimezone(UTC)
        leases = self._repository.acquire_due_conditions(
            now=current,
            owner=owner,
            lease_until=current + timedelta(seconds=self._lease_seconds),
            limit=self._batch_limit,
        )
        completed: list[dict[str, Any]] = []
        for lease in leases:
            condition_id = str(lease["condition_id"])
            due_at = str(lease["due_at"])
            try:
                outcome = self._service.evaluate_due_condition(
                    condition_id=condition_id,
                    due_at=due_at,
                )
                condition = self._repository.get_condition(condition_id)
                if condition is None:
                    raise ValueError("leased thesis condition no longer exists")
                next_due_at = _next_due_at(
                    due_at=due_at,
                    cadence=str(condition["cadence"]),
                    timezone=str(condition["timezone"]),
                )
                advanced = self._repository.complete_due_condition(
                    condition_id=condition_id,
                    due_at=due_at,
                    owner=owner,
                    next_due_at=next_due_at,
                    completed_at=current.isoformat(),
                )
                if not advanced:
                    raise ValueError("thesis schedule lease changed before completion")
            except InterruptedError:
                # A process-interruption signal preserves the original crash/restart
                # semantics: the durable lease expires and the caller sees the crash.
                raise
            except Exception:
                # Acquisition already persisted owner, expiry, and last_attempt_at.
                # Leaving this lease in that bounded retryable state prevents a bad
                # condition from hiding or mutating later work in the acquired batch.
                continue
            completed.append(outcome["check"])
        return completed


def _next_due_at(*, due_at: str, cadence: str, timezone: str) -> str:
    try:
        due = datetime.fromisoformat(due_at)
    except (TypeError, ValueError) as error:
        raise ValueError("due_at must be an ISO timestamp") from error
    if due.tzinfo is None:
        raise ValueError("due_at must include a timezone")
    try:
        local_due = due.astimezone(ZoneInfo(timezone))
    except ZoneInfoNotFoundError as error:
        raise ValueError("condition timezone is unavailable") from error
    if cadence == "daily":
        advanced = local_due + timedelta(days=1)
    elif cadence == "weekly":
        advanced = local_due + timedelta(days=7)
    elif cadence == "monthly":
        advanced = _add_months(local_due, 1)
    elif cadence == "quarterly":
        advanced = _add_months(local_due, 3)
    else:
        raise ValueError("condition cadence is invalid")
    return advanced.astimezone(UTC).isoformat()


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
