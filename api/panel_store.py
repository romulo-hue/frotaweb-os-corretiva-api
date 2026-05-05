from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class PanelStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS panel_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    submitted_by TEXT,
                    source TEXT,
                    linked_order_number TEXT,
                    launched_order_number TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS panel_orders_updated_at
                AFTER UPDATE ON panel_orders
                BEGIN
                    UPDATE panel_orders
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = NEW.id;
                END
                """
            )

    def create_order(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        submitted_by: str = "",
        source: str = "",
        linked_order_number: str = "",
    ) -> dict[str, Any]:
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO panel_orders (kind, status, payload_json, submitted_by, source, linked_order_number)
                VALUES (?, 'PENDING_REVIEW', ?, ?, ?, ?)
                """,
                (kind, payload_json, submitted_by, source, linked_order_number),
            )
            row_id = cursor.lastrowid
        return self.get_order(row_id)

    def list_orders(self, *, kind: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[str] = []
        if kind:
            where.append("kind = ?")
            params.append(kind)
        if status:
            where.append("status = ?")
            params.append(status)
        sql = "SELECT * FROM panel_orders"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_order(self, order_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM panel_orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise KeyError(order_id)
        return self._row_to_dict(row)

    def mark_launched(self, order_id: int, *, order_number: str = "", message: str = "") -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE panel_orders
                SET status = 'LAUNCHED', launched_order_number = ?, error_message = ?
                WHERE id = ?
                """,
                (order_number, message, order_id),
            )
        return self.get_order(order_id)

    def mark_failed(self, order_id: int, message: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                "UPDATE panel_orders SET status = 'FAILED', error_message = ? WHERE id = ?",
                (message, order_id),
            )
        return self.get_order(order_id)

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        return {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "payload": payload,
            "submitted_by": row["submitted_by"] or "",
            "source": row["source"] or "",
            "linked_order_number": row["linked_order_number"] or "",
            "launched_order_number": row["launched_order_number"] or "",
            "error_message": row["error_message"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
