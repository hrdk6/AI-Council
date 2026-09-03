"""Small SQLite store for durable decision history and outcome feedback."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .schemas import CouncilResult, DecisionRecord

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "ai_council.db"


def _get_connection() -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure the schema exists.

    IMPORTANT: Callers are responsible for closing the returned connection.
    ``sqlite3.Connection`` used as a context manager only wraps transactions —
    it does NOT close the connection on exit.
    """
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, question TEXT NOT NULL,
            result_json TEXT NOT NULL, rating INTEGER, outcome_note TEXT
        )"""
    )
    return connection


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


def list_decisions(limit: int = 30) -> list[DecisionRecord]:
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT id, created_at, question, result_json, rating, outcome_note FROM decisions "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [
        DecisionRecord(
            id=row["id"], created_at=row["created_at"], question=row["question"],
            result=json.loads(row["result_json"]), rating=row["rating"], outcome_note=row["outcome_note"],
        )
        for row in rows
    ]


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

