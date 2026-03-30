from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_DB_PATH: Path | None = None


def configure(db_path: str | Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(db_path).expanduser().resolve()


def _require_db_path() -> Path:
    if _DB_PATH is None:
        raise RuntimeError("memory storage is not configured")
    return _DB_PATH


def _connect() -> sqlite3.Connection:
    db_path = _require_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_memory() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS iterations (
                session_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                query TEXT NOT NULL,
                summary_md TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, iteration)
            );

            CREATE TABLE IF NOT EXISTS reports (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                report_path TEXT NOT NULL,
                report_md TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.commit()


def save_iteration(
    session_id: str,
    iteration: int,
    query: str,
    summary_md: str,
    findings: list[dict[str, Any]],
) -> None:
    payload = json.dumps(findings, ensure_ascii=False)
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO iterations (
                session_id,
                iteration,
                query,
                summary_md,
                findings_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, iteration, query, summary_md, payload),
        )
        connection.commit()


def save_report(
    session_id: str,
    title: str,
    report_path: str,
    report_md: str,
) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO reports (
                session_id,
                title,
                report_path,
                report_md
            ) VALUES (?, ?, ?, ?)
            """,
            (session_id, title, report_path, report_md),
        )
        connection.commit()


def save_artifact(
    session_id: str,
    artifact_type: str,
    artifact_path: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = json.dumps(metadata or {}, ensure_ascii=False)
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO artifacts (
                session_id,
                artifact_type,
                artifact_path,
                metadata_json
            ) VALUES (?, ?, ?, ?)
            """,
            (session_id, artifact_type, artifact_path, payload),
        )
        connection.commit()
