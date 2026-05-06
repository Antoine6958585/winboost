"""History — Historique complet des actions WinBoost (SQLite)."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from winboost.core.config import DEFAULT_CONFIG_DIR

HISTORY_DB = DEFAULT_CONFIG_DIR / "history.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    module_name TEXT NOT NULL,
    action_type TEXT NOT NULL,
    description TEXT,
    risk_level TEXT,
    result_status TEXT NOT NULL,
    result_detail TEXT,
    backup_id TEXT,
    metadata TEXT
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_actions_module ON actions(module_name);
CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions(timestamp);
"""


class HistoryEntry:
    """Represente une entree dans l'historique des actions."""

    def __init__(
        self,
        entry_id: int | None,
        timestamp: str,
        module_name: str,
        action_type: str,
        description: str,
        risk_level: str,
        result_status: str,
        result_detail: str = "",
        backup_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.timestamp = timestamp
        self.module_name = module_name
        self.action_type = action_type  # "scan" | "fix" | "restore"
        self.description = description
        self.risk_level = risk_level
        self.result_status = result_status  # "success" | "partial" | "error"
        self.result_detail = result_detail
        self.backup_id = backup_id
        self.metadata = metadata or {}


class HistoryManager:
    """Gere l'historique des actions dans une base SQLite."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or HISTORY_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialise la base de donnees."""
        conn = self._get_conn()
        conn.execute(CREATE_TABLE_SQL)
        conn.executescript(CREATE_INDEX_SQL)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Retourne la connexion SQLite (lazy init)."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Ferme la connexion."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def log_action(
        self,
        module_name: str,
        action_type: str,
        description: str,
        risk_level: str = "low",
        result_status: str = "success",
        result_detail: str = "",
        backup_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Enregistre une action dans l'historique.

        Returns:
            L'ID de l'entree creee.
        """
        conn = self._get_conn()
        ts = datetime.now(tz=UTC).isoformat()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        cursor = conn.execute(
            """INSERT INTO actions
               (timestamp, module_name, action_type, description,
                risk_level, result_status, result_detail, backup_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, module_name, action_type, description,
             risk_level, result_status, result_detail, backup_id, meta_json),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_history(
        self,
        module_name: str | None = None,
        action_type: str | None = None,
        limit: int = 50,
    ) -> list[HistoryEntry]:
        """Recupere l'historique des actions.

        Args:
            module_name: Filtrer par module.
            action_type: Filtrer par type d'action.
            limit: Nombre max d'entrees.
        """
        conn = self._get_conn()
        query = "SELECT * FROM actions"
        params: list[Any] = []
        conditions: list[str] = []

        if module_name:
            conditions.append("module_name = ?")
            params.append(module_name)
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_entry(self, entry_id: int) -> HistoryEntry | None:
        """Recupere une entree par son ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM actions WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def count(self, module_name: str | None = None) -> int:
        """Compte le nombre d'entrees."""
        conn = self._get_conn()
        if module_name:
            row = conn.execute(
                "SELECT COUNT(*) FROM actions WHERE module_name = ?", (module_name,)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM actions").fetchone()
        return row[0]

    def clear(self, module_name: str | None = None) -> int:
        """Supprime les entrees. Retourne le nombre supprime."""
        conn = self._get_conn()
        if module_name:
            cursor = conn.execute("DELETE FROM actions WHERE module_name = ?", (module_name,))
        else:
            cursor = conn.execute("DELETE FROM actions")
        conn.commit()
        return cursor.rowcount

    def _row_to_entry(self, row: sqlite3.Row) -> HistoryEntry:
        """Convertit une row SQLite en HistoryEntry."""
        meta = {}
        if row["metadata"]:
            with contextlib.suppress(json.JSONDecodeError):
                meta = json.loads(row["metadata"])

        return HistoryEntry(
            entry_id=row["id"],
            timestamp=row["timestamp"],
            module_name=row["module_name"],
            action_type=row["action_type"],
            description=row["description"],
            risk_level=row["risk_level"],
            result_status=row["result_status"],
            result_detail=row["result_detail"] or "",
            backup_id=row["backup_id"] or "",
            metadata=meta,
        )
