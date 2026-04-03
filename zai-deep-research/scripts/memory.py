from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from collections.abc import Iterator

_DB_PATH: Path | None = None
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


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


@contextmanager
def _managed_connection() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


def is_available() -> bool:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(content)")
        connection.execute("DROP TABLE fts_probe")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        if connection is not None:
            connection.close()


def _create_fts_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS iterations_fts USING fts5(
            title,
            query,
            summary_md,
            session_id UNINDEXED,
            iteration UNINDEXED
        )
        """
    )


def _ensure_iterations_title_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(iterations)")
    }
    if "title" not in columns:
        connection.execute("ALTER TABLE iterations ADD COLUMN title TEXT")


def _replace_fts_row(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    iteration: int,
    title: str | None,
    query: str,
    summary_md: str,
) -> None:
    connection.execute(
        "DELETE FROM iterations_fts WHERE session_id = ? AND iteration = ?",
        (session_id, iteration),
    )
    connection.execute(
        """
        INSERT INTO iterations_fts (
            title,
            query,
            summary_md,
            session_id,
            iteration
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (title or "", query, summary_md, session_id, iteration),
    )


def _rebuild_fts_index(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM iterations_fts")
    rows = connection.execute(
        """
        SELECT session_id, iteration, title, query, summary_md
        FROM iterations
        ORDER BY session_id, iteration
        """
    ).fetchall()
    for row in rows:
        _replace_fts_row(
            connection,
            session_id=str(row["session_id"]),
            iteration=int(row["iteration"]),
            title=str(row["title"]) if row["title"] is not None else None,
            query=str(row["query"]),
            summary_md=str(row["summary_md"]),
        )


def _build_match_query(query: str) -> str | None:
    terms: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(query):
        normalized = token.strip()
        if not normalized:
            continue
        lowered = normalized.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        escaped = normalized.replace('"', '""')
        terms.append(f'"{escaped}"')
    if not terms:
        return None
    return " OR ".join(terms)


def init_memory() -> None:
    if not is_available():
        raise RuntimeError("SQLite FTS5 is unavailable")
    with _managed_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS iterations (
                session_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                title TEXT,
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
        _ensure_iterations_title_column(connection)
        _create_fts_table(connection)
        _rebuild_fts_index(connection)
        connection.commit()


def save_iteration(
    session_id: str,
    iteration: int,
    query: str,
    summary_md: str,
    findings: list[dict[str, Any]],
    title: str | None = None,
) -> None:
    payload = json.dumps(findings, ensure_ascii=False)
    with _managed_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO iterations (
                session_id,
                iteration,
                title,
                query,
                summary_md,
                findings_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, iteration, title, query, summary_md, payload),
        )
        _replace_fts_row(
            connection,
            session_id=session_id,
            iteration=iteration,
            title=title,
            query=query,
            summary_md=summary_md,
        )
        connection.commit()


def save_report(
    session_id: str,
    title: str,
    report_path: str,
    report_md: str,
) -> None:
    with _managed_connection() as connection:
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
        connection.execute(
            "UPDATE iterations SET title = ? WHERE session_id = ?",
            (title, session_id),
        )
        rows = connection.execute(
            """
            SELECT session_id, iteration, title, query, summary_md
            FROM iterations
            WHERE session_id = ?
            ORDER BY iteration
            """,
            (session_id,),
        ).fetchall()
        for row in rows:
            _replace_fts_row(
                connection,
                session_id=str(row["session_id"]),
                iteration=int(row["iteration"]),
                title=str(row["title"]) if row["title"] is not None else None,
                query=str(row["query"]),
                summary_md=str(row["summary_md"]),
            )
        connection.commit()


def save_artifact(
    session_id: str,
    artifact_type: str,
    artifact_path: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = json.dumps(metadata or {}, ensure_ascii=False)
    with _managed_connection() as connection:
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


def search_iterations(
    query: str,
    *,
    limit: int = 5,
    exclude_session_id: str | None = None,
) -> list[dict[str, Any]]:
    if not query.strip() or limit <= 0:
        return []

    match_query = _build_match_query(query)
    if match_query is None:
        return []

    with _managed_connection() as connection:
        clauses = ["iterations_fts MATCH ?"]
        params: list[Any] = [match_query]
        if exclude_session_id:
            clauses.append("session_id != ?")
            params.append(exclude_session_id)
        params.append(limit)
        rows = connection.execute(
            f"""
            SELECT
                title,
                query,
                summary_md,
                session_id,
                iteration,
                bm25(iterations_fts) AS score
            FROM iterations_fts
            WHERE {' AND '.join(clauses)}
            ORDER BY score ASC, iteration DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "title": str(row["title"]).strip(),
                "query": str(row["query"]),
                "summary_md": str(row["summary_md"]),
                "session_id": str(row["session_id"]),
                "iteration": int(row["iteration"]),
                "score": float(row["score"]),
            }
        )
    return results
