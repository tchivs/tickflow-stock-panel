"""Server-owned scoped authorizations for advanced work."""
from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import MappingProxyType

from app.advanced.repository import AdvancedRepository


@dataclass
class OperatorPolicy:
    """Deployment-derived allowlist used only by server-side services."""

    revision: str
    task_types: frozenset[str]
    markets: frozenset[str]
    instruments: frozenset[str]
    rate_limits: Mapping[str, int]

    def __post_init__(self) -> None:
        limits = dict(self.rate_limits)
        if set(limits) != set(self.task_types) or any(
            not isinstance(task_type, str)
            or not task_type
            or task_type == "__legacy_rate_window__"
            or type(quota) is not int
            or quota <= 0
            for task_type, quota in limits.items()
        ):
            raise ValueError("advanced policy task quotas are invalid")
        self.rate_limits = MappingProxyType(limits)

    def quota_for(self, task_type: str) -> int:
        if not isinstance(task_type, str) or task_type not in self.task_types:
            raise ValueError("task type denied")
        try:
            return self.rate_limits[task_type]
        except KeyError as error:
            raise ValueError("task type denied") from error

    def snapshot(self) -> dict[str, object]:
        return {
            "instruments": sorted(self.instruments),
            "markets": sorted(self.markets),
            "rate_limits": dict(self.rate_limits),
            "task_types": sorted(self.task_types),
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode()).hexdigest()


class AdvancedAuthorizationService:
    """Issues opaque, short-lived authorization records and validates their scope."""

    def __init__(
        self,
        *,
        repository: AdvancedRepository,
        policy_loader: Callable[[], OperatorPolicy],
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._policy_loader = policy_loader
        self._clock = clock

    def issue(
        self,
        *,
        principal: str,
        task_types: set[str],
        markets: set[str],
        instruments: set[str],
        expires_in: timedelta,
    ) -> dict[str, object]:
        policy = self._policy()
        if not principal or expires_in <= timedelta(0):
            raise ValueError("authorization issuance is invalid")
        if not task_types <= policy.task_types or not markets <= policy.markets or not self._instruments_allowed(instruments, policy):
            raise ValueError("authorization scope is not permitted")
        token = secrets.token_urlsafe(32)
        policy_record = self._persist_policy(policy)
        expires_at = self._now() + expires_in
        record = self._repository.create_authorization(
            principal=principal,
            token_hash=self._token_hash(token),
            policy_revision_id=policy_record["id"],
            scope={
                "instruments": sorted(instruments),
                "markets": sorted(markets),
                "task_types": sorted(task_types),
            },
            expires_at=expires_at.isoformat(),
        )
        return {"id": record["id"], "token": token, "expires_at": record["expires_at"]}

    def revoke(self, token: str) -> None:
        record = self._repository.get_authorization_by_token_hash(self._token_hash(token))
        if record is None:
            raise ValueError("authorization is unknown")
        self._repository.revoke_authorization(authorization_id=record["id"])

    def validate_token(
        self,
        *,
        token: str,
        principal: str,
        task_type: str,
        market: str,
        instrument: str,
    ) -> dict[str, object]:
        record = self._repository.get_authorization_by_token_hash(self._token_hash(token))
        if record is None:
            raise ValueError("authorization is invalid")
        return self.validate_record(
            record=record,
            principal=principal,
            task_type=task_type,
            market=market,
            instrument=instrument,
        )

    def validate_record(
        self,
        *,
        record: dict[str, object],
        principal: str,
        task_type: str,
        market: str,
        instrument: str,
    ) -> dict[str, object]:
        if record["principal"] != principal:
            raise ValueError("authorization principal is invalid")
        if record["revoked_at"] is not None:
            raise ValueError("authorization revoked")
        expires_at = datetime.fromisoformat(str(record["expires_at"])).astimezone(UTC)
        if expires_at <= self._now():
            raise ValueError("authorization expired")
        scope = json.loads(str(record["scope_json"]))
        if task_type not in scope["task_types"]:
            raise ValueError("authorization task type denied")
        if market not in scope["markets"] or instrument not in scope["instruments"]:
            raise ValueError("authorization scope denied")
        policy = self._policy()
        policy.quota_for(task_type)
        if market not in policy.markets or not self._instruments_allowed({instrument}, policy):
            raise ValueError("scope denied")
        return record

    def current_policy(self) -> OperatorPolicy:
        return self._policy()

    def _persist_policy(self, policy: OperatorPolicy) -> dict[str, object]:
        return self._repository.record_policy_revision(
            revision=policy.revision,
            fingerprint=policy.fingerprint,
            snapshot=policy.snapshot(),
        )

    def _policy(self) -> OperatorPolicy:
        return self._policy_loader()

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)

    @staticmethod
    def _token_hash(token: str) -> str:
        return sha256(token.encode()).hexdigest()

    @staticmethod
    def _instruments_allowed(instruments: set[str], policy: OperatorPolicy) -> bool:
        """Allow deployment policy to delegate instrument selection to server scope."""
        return "*" in policy.instruments or instruments <= policy.instruments
