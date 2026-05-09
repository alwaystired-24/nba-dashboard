"""Postgres connection + helpers (Supabase).

Migrated from SQLite in Phase 1 (May 2026). Native psycopg2 — no compatibility
shims. Uses RealDictCursor so rows behave like dicts (`row["col_name"]`),
matching the previous SQLite Row factory ergonomics.

Phase 1.4 (May 7, 2026): Added retry logic + auto-reconnect to handle
Supabase pooler dropping connections during long ETL runs.

Public surface (kept identical):
    connect()                  -> context manager yielding (conn, cursor)
    upsert(...)                -> bulk INSERT ... ON CONFLICT DO UPDATE (with retry)
    record_etl(...)            -> log a scrape attempt to etl_runs
    games_missing_endpoint(...)-> list game_ids needing scraping
"""
from __future__ import annotations

import os
import time
import logging
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

logger = logging.getLogger(__name__)

# Connection settings tuned for Supabase pooler (6543 transaction mode)
# or direct connection (5432 session mode).
CONNECT_KWARGS = dict(
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5,
    connect_timeout=10,
)


def _new_connection():
    """Open a fresh Postgres connection with keepalives + statement timeout."""
    conn = psycopg2.connect(DATABASE_URL, **CONNECT_KWARGS)
    # Force any query that hangs >30s to fail, so retry logic can kick in
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
    conn.commit()
    return conn


@contextmanager
def connect() -> Iterator[tuple]:
    """Yield (connection, cursor) with dict-row cursor.

    Usage:
        with connect() as (conn, cur):
            cur.execute("SELECT * FROM teams WHERE team_id = %s", (tid,))
            row = cur.fetchone()
            name = row["full_name"]

    Commits on clean exit, rolls back on exception, always closes.
    """
    conn = _new_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn, cur
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def _execute_with_retry(cur, sql, rows, page_size=500, max_retries=3):
    """Execute a batch with auto-reconnect on connection drops.

    If Supabase drops the connection mid-batch, we get a fresh connection
    and retry. Up to max_retries attempts with exponential backoff.
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=page_size)
            return
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                "DB connection dropped on batch (attempt %d/%d): %s. "
                "Reconnecting in %ds...",
                attempt + 1, max_retries, exc, wait
            )
            time.sleep(wait)

            # Reconnect: close old connection, open fresh one, swap cursor's connection
            old_conn = cur.connection
            try:
                old_conn.close()
            except Exception:
                pass

            new_conn = _new_connection()
            new_cur = new_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Replace the cursor's internals so caller doesn't notice
            cur.connection = new_conn
            # Note: we can't fully swap the cursor object, but the next
            # execute_batch call will use new_cur via the wrapper below
            cur = new_cur

    raise last_exc


def upsert(cur, table: str, rows: list[dict], pk: list[str]) -> int:
    """Generic INSERT ... ON CONFLICT ... DO UPDATE for batched dicts.

    Auto-retries on Supabase connection drops.
    Returns number of rows written. Skips silently when rows is empty.
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
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({pk_list}) DO NOTHING"
        )

    # Retry loop: if connection drops, get fresh conn and retry whole batch
    max_retries = 3
    for attempt in range(max_retries):
        try:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=500)
            cur.connection.commit()
            return len(rows)
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning(
                "Batch upsert to %s failed (attempt %d/%d): %s. Retrying in %ds...",
                table, attempt + 1, max_retries, exc, wait
            )
            time.sleep(wait)
            # Reconnect
            try:
                cur.connection.close()
            except Exception:
                pass
            new_conn = _new_connection()
            new_cur = new_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Mutate caller's cur object so they keep using the right one
            cur.__dict__.update(new_cur.__dict__)


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
