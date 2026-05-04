"""Postgres connection + helpers (Supabase).

Migrated from SQLite in Phase 1 (May 2026). Native psycopg2 — no compatibility
shims. Uses RealDictCursor so rows behave like dicts (`row["col_name"]`),
matching the previous SQLite Row factory ergonomics.

Public surface (kept identical to SQLite version where possible):
    connect()                  -> context manager yielding (conn, cursor)
    upsert(...)                -> bulk INSERT ... ON CONFLICT DO UPDATE
    record_etl(...)            -> log a scrape attempt to etl_runs
    games_missing_endpoint(...)-> list game_ids needing scraping
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL not set. Add it to .env "
        "(see .env.example for format)."
    )


@contextmanager
def connect() -> Iterator[tuple]:
    """Yield (connection, cursor) with dict-row cursor.

    Usage:
        with connect() as (conn, cur):
            cur.execute("SELECT * FROM teams WHERE team_id = %s", (tid,))
            row = cur.fetchone()
            name = row["full_name"]   # dict-style access

    Commits on clean exit, rolls back on exception, always closes.
    """
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def upsert(cur, table: str, rows: list[dict], pk: list[str]) -> int:
    """Generic INSERT ... ON CONFLICT ... DO UPDATE for batched dicts.

    Postgres uses %(name)s named-parameter syntax (matches what we generate).
    Returns number of rows written. Skips silently when rows is empty.

    Note: takes a CURSOR now, not a connection (psycopg2 separates these).
    """
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join(f"%({c})s" for c in cols)
    col_list = ", ".join(cols)
    pk_list = ", ".join(pk)
    update_cols = [c for c in cols if c not in pk]
    if update_cols:
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({pk_list}) DO UPDATE SET {update_clause}"
        )
    else:
        # All columns are PK — nothing to update on conflict
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({pk_list}) DO NOTHING"
        )
    psycopg2.extras.execute_batch(cur, sql, rows, page_size=500)
    return len(rows)


def record_etl(cur, game_id: str, endpoint: str,
               status: str, error: str | None = None) -> None:
    """Log a scrape attempt to etl_runs."""
    cur.execute(
        """
        INSERT INTO etl_runs (game_id, endpoint, status, last_attempt_utc, error)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (game_id, endpoint) DO UPDATE SET
            status           = EXCLUDED.status,
            last_attempt_utc = EXCLUDED.last_attempt_utc,
            error            = EXCLUDED.error
        """,
        (game_id, endpoint, status, datetime.now(timezone.utc).isoformat(), error),
    )


def games_missing_endpoint(cur, endpoint: str,
                            only_final: bool = True) -> list[str]:
    """Return game_ids that haven't successfully completed `endpoint` yet."""
    status_filter = "AND g.status = 'Final'" if only_final else ""
    cur.execute(
        f"""
        SELECT g.game_id
        FROM games g
        LEFT JOIN etl_runs e
          ON e.game_id = g.game_id AND e.endpoint = %s
        WHERE (e.status IS NULL OR e.status = 'failed')
          {status_filter}
        ORDER BY g.game_date
        """,
        (endpoint,),
    )
    return [r["game_id"] for r in cur.fetchall()]
