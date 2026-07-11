"""Parameterized repository for durable operational portfolio records."""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Mapping

from app.operational.migrations import migrate_operational_db


TRADING_STYLES = frozenset({"short", "swing", "long"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    record = dict(row)
    if "enabled" in record:
        record["enabled"] = bool(record["enabled"])
    return record


def _finite_nonnegative(value: float | int, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be a non-negative finite number")
    return float(value)


def _positive(value: float | int, field: str) -> float:
    value = _finite_nonnegative(value, field)
    if value == 0:
        raise ValueError(f"{field} must be positive")
    return value


def _notes(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("notes must be a string")
    return value.strip()


class OperationalRepository:
    """Owns SQLite connections and transaction-safe account/position mutations."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        with self._connection() as connection:
            migrate_operational_db(connection)

    @staticmethod
    def _account_input(name: str, available_funds: float | int) -> tuple[str, float]:
        if not isinstance(name, str) or not (name := name.strip()):
            raise ValueError("name is required")
        return name, _finite_nonnegative(available_funds, "available_funds")

    @staticmethod
    def _position_input(
        instrument_symbol: str,
        cost_price: float | int,
        quantity: float | int,
        invested_amount: float | int,
        trading_style: str,
    ) -> tuple[str, float, float, float, str]:
        if not isinstance(instrument_symbol, str) or not (symbol := instrument_symbol.strip().upper()):
            raise ValueError("instrument_symbol is required")
        if not isinstance(trading_style, str) or trading_style not in TRADING_STYLES:
            raise ValueError("trading_style must be short, swing, or long")
        return (
            symbol,
            _finite_nonnegative(cost_price, "cost_price"),
            _positive(quantity, "quantity"),
            _finite_nonnegative(invested_amount, "invested_amount"),
            trading_style,
        )

    def create_account(self, *, name: str, available_funds: float | int = 0, notes: str = "") -> dict[str, Any]:
        name, available_funds = self._account_input(name, available_funds)
        now = _now()
        with self._connection() as connection, connection:
            cursor = connection.execute(
                """INSERT INTO accounts (name, available_funds, notes, enabled, archived_at, created_at, updated_at)
                   VALUES (?, ?, ?, 1, NULL, ?, ?)""",
                (name, available_funds, _notes(notes), now, now),
            )
            return self._get_account(connection, cursor.lastrowid)

    def update_account(
        self,
        account_id: int,
        *,
        name: str | None = None,
        available_funds: float | int | None = None,
        enabled: bool | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        if self.get_account(account_id) is None:
            return None
        fields: list[str] = []
        values: list[Any] = []
        if name is not None:
            normalized_name, _ = self._account_input(name, 0)
            fields.append("name = ?")
            values.append(normalized_name)
        if available_funds is not None:
            fields.append("available_funds = ?")
            values.append(_finite_nonnegative(available_funds, "available_funds"))
        if enabled is not None:
            fields.append("enabled = ?")
            values.append(int(bool(enabled)))
        if notes is not None:
            fields.append("notes = ?")
            values.append(_notes(notes))
        if not fields:
            return self.get_account(account_id)
        fields.append("updated_at = ?")
        values.extend([_now(), account_id])
        with self._connection() as connection, connection:
            connection.execute(f"UPDATE accounts SET {', '.join(fields)} WHERE id = ?", values)
            return self._get_account(connection, account_id)

    def get_account(self, account_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._get_account(connection, account_id)

    def _get_account(self, connection: sqlite3.Connection, account_id: int) -> dict[str, Any] | None:
        return _record(connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone())

    def list_accounts(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        clause = "" if include_archived else "WHERE archived_at IS NULL"
        with self._connection() as connection:
            return [_record(row) for row in connection.execute(f"SELECT * FROM accounts {clause} ORDER BY id").fetchall()]

    def archive_account(self, account_id: int) -> dict[str, Any] | None:
        now = _now()
        with self._connection() as connection, connection:
            connection.execute(
                "UPDATE accounts SET enabled = 0, archived_at = COALESCE(archived_at, ?), updated_at = ? WHERE id = ?",
                (now, now, account_id),
            )
            return self._get_account(connection, account_id)

    def delete_account(self, account_id: int) -> bool:
        with self._connection() as connection, connection:
            has_positions = connection.execute("SELECT 1 FROM positions WHERE account_id = ? LIMIT 1", (account_id,)).fetchone()
            if has_positions:
                return False
            return connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,)).rowcount == 1

    def create_position(
        self,
        *,
        account_id: int,
        instrument_symbol: str,
        cost_price: float | int,
        quantity: float | int,
        invested_amount: float | int,
        trading_style: str,
        notes: str = "",
    ) -> dict[str, Any]:
        symbol, cost_price, quantity, invested_amount, trading_style = self._position_input(
            instrument_symbol, cost_price, quantity, invested_amount, trading_style
        )
        now = _now()
        try:
            with self._connection() as connection, connection:
                if self._get_account(connection, account_id) is None:
                    raise ValueError("account does not exist")
                cursor = connection.execute(
                    """INSERT INTO positions (
                        account_id, instrument_symbol, cost_price, quantity, invested_amount, trading_style, notes,
                        enabled, archived_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)""",
                    (account_id, symbol, cost_price, quantity, invested_amount, trading_style, _notes(notes), now, now),
                )
                return self._get_position(connection, cursor.lastrowid)
        except sqlite3.IntegrityError as error:
            if "positions.account_id, positions.instrument_symbol" in str(error):
                raise ValueError("instrument already exists in this account") from error
            raise

    def update_position(
        self,
        position_id: int,
        *,
        instrument_symbol: str | None = None,
        cost_price: float | int | None = None,
        quantity: float | int | None = None,
        invested_amount: float | int | None = None,
        trading_style: str | None = None,
        enabled: bool | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        if self.get_position(position_id) is None:
            return None
        fields: list[str] = []
        values: list[Any] = []
        if instrument_symbol is not None:
            symbol, _, _, _, _ = self._position_input(instrument_symbol, 0, 1, 0, "short")
            fields.append("instrument_symbol = ?")
            values.append(symbol)
        if cost_price is not None:
            fields.append("cost_price = ?")
            values.append(_finite_nonnegative(cost_price, "cost_price"))
        if quantity is not None:
            fields.append("quantity = ?")
            values.append(_positive(quantity, "quantity"))
        if invested_amount is not None:
            fields.append("invested_amount = ?")
            values.append(_finite_nonnegative(invested_amount, "invested_amount"))
        if trading_style is not None:
            if trading_style not in TRADING_STYLES:
                raise ValueError("trading_style must be short, swing, or long")
            fields.append("trading_style = ?")
            values.append(trading_style)
        if notes is not None:
            fields.append("notes = ?")
            values.append(_notes(notes))
        if enabled is not None:
            fields.append("enabled = ?")
            values.append(int(bool(enabled)))
        if not fields:
            return self.get_position(position_id)
        fields.append("updated_at = ?")
        values.extend([_now(), position_id])
        try:
            with self._connection() as connection, connection:
                connection.execute(f"UPDATE positions SET {', '.join(fields)} WHERE id = ?", values)
                return self._get_position(connection, position_id)
        except sqlite3.IntegrityError as error:
            if "positions.account_id, positions.instrument_symbol" in str(error):
                raise ValueError("instrument already exists in this account") from error
            raise

    def get_position(self, position_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._get_position(connection, position_id)

    def _get_position(self, connection: sqlite3.Connection, position_id: int) -> dict[str, Any] | None:
        return _record(connection.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone())

    def list_positions(
        self,
        *,
        account_id: int | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        predicates: list[str] = []
        values: list[Any] = []
        if account_id is not None:
            predicates.append("account_id = ?")
            values.append(account_id)
        if not include_archived:
            predicates.append("archived_at IS NULL")
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        with self._connection() as connection:
            return [_record(row) for row in connection.execute(
                f"SELECT * FROM positions {where} ORDER BY account_id, instrument_symbol, id", values
            ).fetchall()]

    def archive_position(self, position_id: int) -> dict[str, Any] | None:
        now = _now()
        with self._connection() as connection, connection:
            connection.execute(
                "UPDATE positions SET enabled = 0, archived_at = COALESCE(archived_at, ?), updated_at = ? WHERE id = ?",
                (now, now, position_id),
            )
            return self._get_position(connection, position_id)

    def delete_position(self, position_id: int) -> bool:
        with self._connection() as connection, connection:
            referenced = connection.execute(
                "SELECT 1 FROM alert_references WHERE position_id = ? LIMIT 1", (position_id,)
            ).fetchone()
            if referenced:
                return False
            return connection.execute("DELETE FROM positions WHERE id = ?", (position_id,)).rowcount == 1

    def record_alert_reference(self, *, position_id: int, rule_id: str) -> dict[str, Any]:
        if not isinstance(rule_id, str) or not (rule_id := rule_id.strip()):
            raise ValueError("rule_id is required")
        now = _now()
        with self._connection() as connection, connection:
            try:
                cursor = connection.execute(
                    "INSERT INTO alert_references (position_id, rule_id, created_at) VALUES (?, ?, ?)",
                    (position_id, rule_id, now),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("position does not exist") from error
            row = connection.execute("SELECT * FROM alert_references WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return _record(row)  # type: ignore[return-value]

    @staticmethod
    def _json_snapshot(value: Any, field: str) -> str:
        try:
            return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field} must be JSON serializable") from error

    def save_monitor_rule(self, rule: Mapping[str, Any]) -> dict[str, Any]:
        """Persist the validated Monitor-domain rule without creating another rule model."""
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("monitor rule id is required")
        now = _now()
        serialized = self._json_snapshot(dict(rule), "monitor rule")
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO monitor_rules (id, rule_json, enabled, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET rule_json = excluded.rule_json,
                                                enabled = excluded.enabled,
                                                updated_at = excluded.updated_at""",
                (rule_id, serialized, int(bool(rule.get("enabled", True))), rule.get("created_at", now), now),
            )
        return dict(rule)

    def delete_monitor_rule(self, rule_id: str) -> bool:
        with self._connection() as connection, connection:
            return connection.execute("DELETE FROM monitor_rules WHERE id = ?", (rule_id,)).rowcount == 1

    def record_alert_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """Atomically retain an immutable alert snapshot before SSE or delivery work."""
        event_id = event.get("id") or uuid.uuid4().hex
        rule_id = event.get("rule_id")
        if not isinstance(event_id, str) or not event_id or not isinstance(rule_id, str) or not rule_id:
            raise ValueError("alert event id and rule_id are required")
        now = _now()
        occurred_at = event.get("occurred_at") or now
        if not isinstance(occurred_at, str) or not occurred_at:
            raise ValueError("alert event occurred_at is required")
        conditions = event.get("conditions", [])
        if not isinstance(conditions, list):
            raise ValueError("alert event conditions must be a list")
        snapshot = dict(event)
        snapshot["id"] = event_id
        snapshot["occurred_at"] = occurred_at
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO alert_events (
                       id, rule_id, source, type, symbol, name, price, change_pct, severity,
                       conditions_json, account_id, position_id, valuation_source, valuation_as_of,
                       occurred_at, created_at, event_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    rule_id,
                    str(event.get("source", "position")),
                    str(event.get("type", "position")),
                    str(event.get("symbol", "")),
                    str(event.get("name", "")),
                    event.get("price"),
                    event.get("change_pct"),
                    str(event.get("severity", "info")),
                    self._json_snapshot(conditions, "alert event conditions"),
                    None if event.get("account_id") is None else str(event["account_id"]),
                    None if event.get("position_id") is None else str(event["position_id"]),
                    event.get("valuation_source"),
                    event.get("valuation_as_of"),
                    occurred_at,
                    now,
                    self._json_snapshot(snapshot, "alert event"),
                ),
            )
        persisted = self.get_alert_event(event_id)
        assert persisted is not None
        return persisted

    def get_alert_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM alert_events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        event = json.loads(record.pop("event_json"))
        event["conditions"] = json.loads(record.pop("conditions_json"))
        event["account_id"] = record.pop("account_id")
        event["position_id"] = record.pop("position_id")
        event["valuation_source"] = record.pop("valuation_source")
        event["valuation_as_of"] = record.pop("valuation_as_of")
        event["occurred_at"] = record.pop("occurred_at")
        event["created_at"] = record.pop("created_at")
        return event

    def list_alert_events(
        self,
        *,
        days: int = 7,
        limit: int = 5000,
        source: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        delivery_status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return durable alert snapshots and safe delivery state for the Monitor history."""
        predicates: list[str] = []
        values: list[Any] = []
        if days > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            predicates.append("occurred_at >= ?")
            values.append(cutoff)
        for column, value in (("source", source), ("type", event_type), ("severity", severity)):
            if value:
                predicates.append(f"{column} = ?")
                values.append(value)
        if delivery_status:
            predicates.append(
                "EXISTS (SELECT 1 FROM notification_deliveries d "
                "WHERE d.event_id = alert_events.id AND d.status = ?)"
            )
            values.append(delivery_status)
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        bounded_limit = max(1, min(limit, 5000))
        with self._connection() as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) FROM alert_events {where}", values,
            ).fetchone()[0])
            rows = connection.execute(
                f"SELECT id FROM alert_events {where} ORDER BY occurred_at DESC LIMIT ?",
                [*values, bounded_limit],
            ).fetchall()
        events = [event for row in rows if (event := self.get_alert_event(str(row["id"]))) is not None]
        for event in events:
            event["deliveries"] = self.delivery_details(event["id"])
        return events, total


    def create_delivery_outcome(
        self,
        *,
        event_id: str,
        channel: str,
        status: str,
        error: str | None,
    ) -> None:
        if channel not in {"feishu", "telegram"} or status not in {"pending", "sent", "failed", "skipped"}:
            raise ValueError("notification delivery outcome is invalid")
        now = _now()
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO notification_deliveries (
                       event_id, channel, status, error, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(event_id, channel) DO UPDATE SET
                       status = excluded.status, error = excluded.error, updated_at = excluded.updated_at""",
                (event_id, channel, status, error, now, now),
            )

    def update_delivery_outcome(
        self,
        *,
        event_id: str,
        channel: str,
        status: str,
        error: str | None,
    ) -> None:
        if status not in {"sent", "failed", "skipped"}:
            raise ValueError("notification delivery status is invalid")
        with self._connection() as connection, connection:
            if connection.execute(
                """UPDATE notification_deliveries
                   SET status = ?, error = ?, updated_at = ?
                   WHERE event_id = ? AND channel = ?""",
                (status, error, _now(), event_id, channel),
            ).rowcount != 1:
                raise ValueError("notification delivery does not exist")

    def list_delivery_outcomes(self, event_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT channel, status, error FROM notification_deliveries
                   WHERE event_id = ? ORDER BY id""",
                (event_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delivery_details(self, event_id: str) -> list[dict[str, Any]]:
        """Expose only sanitized delivery outcome fields suitable for the frontend."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT channel, status, error, created_at, updated_at FROM notification_deliveries
                   WHERE event_id = ? ORDER BY id""",
                (event_id,),
            ).fetchall()
        return [dict(row) for row in rows]


    @staticmethod
    def _decision_snapshot_json(snapshot: Mapping[str, Any]) -> str:
        if not isinstance(snapshot, Mapping):
            raise ValueError("decision snapshot is required")
        return json.dumps(dict(snapshot), default=str, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decision_snapshot(value: str) -> dict[str, Any]:
        snapshot = json.loads(value)
        for field in ("entry_low", "entry_high", "stop", "target1", "target2", "position_pct", "score", "risk_reward"):
            if field in snapshot and snapshot[field] is not None:
                snapshot[field] = Decimal(snapshot[field])
        return snapshot

    @staticmethod
    def _require_run(connection: sqlite3.Connection, run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id is required")
        if connection.execute("SELECT 1 FROM playbooks WHERE run_id = ?", (run_id,)).fetchone() is None:
            raise ValueError("decision run does not exist")

    def persist_decision_baseline(self, baseline: Any) -> dict[str, Any]:
        """Persist immutable baseline and identical initial final plan atomically."""
        snapshot = baseline.to_snapshot()
        run_id = uuid.uuid4().hex
        now = _now()
        data_as_of = getattr(baseline, "data_as_of", None)
        engine_config_version = getattr(baseline, "engine_config_version", None)
        symbol = snapshot.get("symbol")
        if not isinstance(symbol, str) or not symbol or data_as_of is None or not isinstance(engine_config_version, str) or not engine_config_version:
            raise ValueError("baseline provenance is required")
        serialized = self._decision_snapshot_json(snapshot)
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO decision_runs (id, symbol, data_as_of, engine_config_version, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, symbol, str(data_as_of), engine_config_version, now),
            )
            connection.execute(
                "INSERT INTO playbooks (run_id, baseline_json, final_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, serialized, serialized, now, now),
            )
        return {"id": run_id, "symbol": symbol, "data_as_of": str(data_as_of), "engine_config_version": engine_config_version}

    def get_decision_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT runs.id, runs.symbol, runs.data_as_of, runs.engine_config_version, runs.created_at,
                          playbooks.baseline_json, playbooks.final_json
                   FROM decision_runs AS runs JOIN playbooks ON playbooks.run_id = runs.id
                   WHERE runs.id = ?""",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            proposal_row = connection.execute(
                "SELECT provider, model, proposal_json FROM ai_review_proposals WHERE run_id = ?", (run_id,)
            ).fetchone()
            audit_rows = connection.execute(
                """SELECT field, proposed_value, final_value, disposition, rationale
                   FROM adjustment_audit WHERE run_id = ? ORDER BY id""",
                (run_id,),
            ).fetchall()
        return {
            "id": row["id"],
            "symbol": row["symbol"],
            "data_as_of": row["data_as_of"],
            "engine_config_version": row["engine_config_version"],
            "created_at": row["created_at"],
            "baseline": self._decision_snapshot(row["baseline_json"]),
            "final": self._decision_snapshot(row["final_json"]),
            "proposal": None if proposal_row is None else {
                "provider": proposal_row["provider"],
                "model": proposal_row["model"],
                **json.loads(proposal_row["proposal_json"]),
            },
            "adjustments": [dict(record) for record in audit_rows],
        }

    def replace_decision_baseline(self, run_id: str, snapshot: Mapping[str, Any]) -> None:
        """Baseline snapshots are deliberately immutable after a run is created."""
        del run_id, snapshot
        raise ValueError("decision baseline is immutable")

    def replace_decision_final(self, run_id: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        """Update only the independently stored final snapshot for bounded adjustments."""
        serialized = self._decision_snapshot_json(snapshot)
        with self._connection() as connection, connection:
            self._require_run(connection, run_id)
            connection.execute(
                "UPDATE playbooks SET final_json = ?, updated_at = ? WHERE run_id = ?",
                (serialized, _now(), run_id),
            )
        persisted = self.get_decision_run(run_id)
        assert persisted is not None
        return persisted

    def record_ai_review_proposal(
        self,
        *,
        run_id: str,
        provider: str,
        model: str,
        proposal: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(provider, str) or not provider or not isinstance(model, str) or not model:
            raise ValueError("proposal provider and model are required")
        if not isinstance(proposal, Mapping):
            raise ValueError("proposal must be a record")
        proposal_json = json.dumps(dict(proposal), default=str, sort_keys=True, separators=(",", ":"))
        with self._connection() as connection, connection:
            self._require_run(connection, run_id)
            try:
                connection.execute(
                    """INSERT INTO ai_review_proposals (id, run_id, provider, model, proposal_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (uuid.uuid4().hex, run_id, provider, model, proposal_json, _now()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("proposal already exists for decision run") from error
        return {"provider": provider, "model": model, **json.loads(proposal_json)}

    def record_adjustment_audit(
        self,
        *,
        run_id: str,
        field: str,
        proposed_value: str | None,
        final_value: str | None,
        disposition: str,
        rationale: str,
    ) -> dict[str, Any]:
        if not isinstance(field, str) or not field or disposition not in {"applied", "clamped", "rejected"}:
            raise ValueError("adjustment audit is invalid")
        if not isinstance(rationale, str):
            raise ValueError("adjustment rationale is required")
        with self._connection() as connection, connection:
            self._require_run(connection, run_id)
            cursor = connection.execute(
                """INSERT INTO adjustment_audit (
                       run_id, field, proposed_value, final_value, disposition, rationale, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, field, proposed_value, final_value, disposition, rationale, _now()),
            )
            row = connection.execute(
                "SELECT field, proposed_value, final_value, disposition, rationale FROM adjustment_audit WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return dict(row)

    def record_replay_run(
        self,
        *,
        as_of: str,
        engine_config_version: str,
        result_hash: str,
        snapshot: Mapping[str, Any],
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if not all(isinstance(value, str) and value for value in (as_of, engine_config_version, result_hash)):
            raise ValueError("replay provenance is required")
        run_id = uuid.uuid4().hex
        snapshot_json = self._decision_snapshot_json(snapshot)
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO replay_runs (
                       id, as_of, engine_config_version, provider, model, result_hash, snapshot_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, as_of, engine_config_version, provider, model, result_hash, snapshot_json, _now()),
            )
        return {"id": run_id, "as_of": as_of, "engine_config_version": engine_config_version, "result_hash": result_hash, "snapshot": dict(snapshot), "provider": provider, "model": model}

    def get_replay_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM replay_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["snapshot"] = json.loads(record.pop("snapshot_json"))
        return record
