"""Parameterized repository for durable operational portfolio records."""
from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

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

    def create_account(self, *, name: str, available_funds: float | int = 0) -> dict[str, Any]:
        name, available_funds = self._account_input(name, available_funds)
        now = _now()
        with self._connection() as connection, connection:
            cursor = connection.execute(
                """INSERT INTO accounts (name, available_funds, enabled, archived_at, created_at, updated_at)
                   VALUES (?, ?, 1, NULL, ?, ?)""",
                (name, available_funds, now, now),
            )
            return self._get_account(connection, cursor.lastrowid)

    def update_account(
        self,
        account_id: int,
        *,
        name: str | None = None,
        available_funds: float | int | None = None,
        enabled: bool | None = None,
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
                        account_id, instrument_symbol, cost_price, quantity, invested_amount, trading_style,
                        enabled, archived_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)""",
                    (account_id, symbol, cost_price, quantity, invested_amount, trading_style, now, now),
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
