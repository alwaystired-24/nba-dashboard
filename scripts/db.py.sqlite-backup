"""SQLite connection + schema management."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nba.db"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"


@contextmanager
def connect(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with foreign keys + row factory enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    """Apply schema.sql to the database (idempotent — uses CREATE IF NOT EXISTS)."""
    schema_sql = schema_path.read_text()
    with connect(db_path) as conn:
        conn.executescript(schema_sql)


def upsert(conn: sqlite3.Connection, table: str, rows: list[dict], pk: list[str]) -> int:
    """Generic INSERT ... ON CONFLICT ... DO UPDATE for batched dicts.

    Returns number of rows written. Skips silently when rows is empty.
    """
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in pk)
    pk_list = ", ".join(pk)
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT({pk_list}) DO UPDATE SET {update_clause}"
    )
    conn.executemany(sql, rows)
    return len(rows)


def record_etl(conn: sqlite3.Connection, game_id: str, endpoint: str,
               status: str, error: str | None = None) -> None:
    """Log a scrape attempt to etl_runs."""
    from datetime import datetime, timezone
    conn.execute(
        """
        INSERT INTO etl_runs (game_id, endpoint, status, last_attempt_utc, error)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(game_id, endpoint) DO UPDATE SET
            status=excluded.status,
            last_attempt_utc=excluded.last_attempt_utc,
            error=excluded.error
        """,
        (game_id, endpoint, status, datetime.now(timezone.utc).isoformat(), error),
    )


def games_missing_endpoint(conn: sqlite3.Connection, endpoint: str,
                            only_final: bool = True) -> list[str]:
    """Return game_ids that haven't successfully completed `endpoint` yet."""
    status_filter = "AND g.status = 'Final'" if only_final else ""
    rows = conn.execute(
        f"""
        SELECT g.game_id
        FROM games g
        LEFT JOIN etl_runs e
          ON e.game_id = g.game_id AND e.endpoint = ?
        WHERE (e.status IS NULL OR e.status = 'failed')
          {status_filter}
        ORDER BY g.game_date
        """,
        (endpoint,),
    ).fetchall()
    return [r["game_id"] for r in rows]
