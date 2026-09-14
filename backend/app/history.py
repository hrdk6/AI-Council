"""Small SQLite store for durable decision history and outcome feedback.

All functions are synchronous; call them from async code via ``asyncio.to_thread``
so disk I/O never blocks the event loop.
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from .config import cfg
from .schemas import CouncilResult, DecisionRecord

DATABASE_PATH = Path(cfg.database_path)

_schema_lock = threading.Lock()
_initialized_paths: set[Path] = set()


def _ensure_schema(connection: sqlite3.Connection, path: Path) -> None:
    with _schema_lock:
        if path in _initialized_paths:
            return
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, question TEXT NOT NULL,
                result_json TEXT NOT NULL, rating INTEGER, outcome_note TEXT
            )"""
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions (created_at DESC)")
        connection.commit()
        _initialized_paths.add(path)


def _get_connection() -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure the schema exists.

    IMPORTANT: Callers are responsible for closing the returned connection.
    ``sqlite3.Connection`` used as a context manager only wraps transactions —
    it does NOT close the connection on exit.
    """
    path = DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection, path)
    return connection


def check_database() -> bool:
    """Return True when the database is reachable and writable enough to answer a query."""
    try:
        conn = _get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return True
    except (sqlite3.Error, OSError):
        return False


def save_decision(result: CouncilResult) -> None:
    if not result.request_id:
        return
    conn = _get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO decisions (id, created_at, question, result_json) VALUES (?, ?, ?, ?)",
                (result.request_id, datetime.now(UTC).isoformat(), result.question, result.model_dump_json()),
            )
    finally:
        conn.close()


def _to_record(row: sqlite3.Row) -> DecisionRecord:
    return DecisionRecord(
        id=row["id"], created_at=row["created_at"], question=row["question"],
        result=json.loads(row["result_json"]), rating=row["rating"], outcome_note=row["outcome_note"],
    )


def list_decisions(limit: int = 30) -> list[DecisionRecord]:
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT id, created_at, question, result_json, rating, outcome_note FROM decisions "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [_to_record(row) for row in rows]


def get_decision(decision_id: str) -> DecisionRecord | None:
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT id, created_at, question, result_json, rating, outcome_note FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
    finally:
        conn.close()
    return _to_record(row) if row is not None else None


def save_feedback(decision_id: str, rating: int | None, outcome_note: str | None) -> bool:
    conn = _get_connection()
    try:
        with conn:
            cursor = conn.execute(
                "UPDATE decisions SET rating = ?, outcome_note = ? WHERE id = ?",
                (rating, (outcome_note or "").strip() or None, decision_id),
            )
        return cursor.rowcount == 1
    finally:
        conn.close()
