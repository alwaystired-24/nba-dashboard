"""Fetch per-team per-quarter scoring data from NBA stats.

Uses the boxscoresummaryv2 endpoint, which returns multiple result sets.
We pull the LineScore set, which has PTS_QTR1..QTR4 + PTS_OT1..OT10 per team.

Usage:
    # Apply the schema migration (run once)
    python -m scripts.run quarters_init

    # Backfill ALL Final games not yet captured
    python -m scripts.run quarters

    # Backfill only N games (smoke test before full backfill)
    python -m scripts.run quarters --limit 10

The command is also wired into the nightly `daily` run so newly-Final games
get their quarter scores after the box score ETL finishes.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from nba_api.stats.endpoints import boxscoresummaryv2

from .db import upsert
from .nba import call_with_retry

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "sql" / "migrations" / "004_quarter_scoring.sql"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_quarter_schema(conn: sqlite3.Connection) -> None:
    """Apply migration 004 if not already applied."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Migration file missing: {SCHEMA_PATH}")
    sql = SCHEMA_PATH.read_text()
    conn.executescript(sql)
    conn.commit()


# ---------------------------------------------------------------------------
# Single-game fetch
# ---------------------------------------------------------------------------

# NBA's LineScore columns we care about. Others (TEAM_NICKNAME, TEAM_CITY_NAME, ...)
# are present but we just ignore them.
_QTR_COLS = ["PTS_QTR1", "PTS_QTR2", "PTS_QTR3", "PTS_QTR4"]
_OT_COLS = ["PTS_OT1", "PTS_OT2", "PTS_OT3", "PTS_OT4"]


def fetch_quarter_scores(game_id: str) -> list[dict] | None:
    """Pull line score for one game. Returns 2 rows (home + away) or None on failure.

    The NBA API expects game_id as a 10-char zero-padded string. We pass through
    whatever the caller gives — game_id values in our DB are already in that
    form.
    """
    try:
        ep = call_with_retry(
            boxscoresummaryv2.BoxScoreSummaryV2,
            game_id=game_id,
        )
        # boxscoresummaryv2 returns multiple data frames; LineScore is among them.
        # Use the named accessor to be robust to column-order changes.
        df = ep.line_score.get_data_frame()
    except Exception as exc:
        logger.warning("Failed to fetch quarter scores for game %s: %s",
                        game_id, exc)
        return None

    if df.empty:
        return None

    fetched = datetime.now(timezone.utc).isoformat()
    rows = []
    try:
        for _, r in df.iterrows():
            row = {
                "game_id": str(r["GAME_ID"]) if r.get("GAME_ID") is not None else game_id,
                "team_id": _safe_int(r.get("TEAM_ID")),
                "fetched_utc": fetched,
            }
            # Skip rows with no team_id — corrupt response
            if row["team_id"] is None:
                logger.warning("Skipping row with no TEAM_ID for game %s", game_id)
                continue
            # Quarter columns
            for i, col in enumerate(_QTR_COLS, start=1):
                row[f"pts_q{i}"] = _safe_int(r.get(col))
            # OT columns (may be missing if no OT)
            for i, col in enumerate(_OT_COLS, start=1):
                row[f"pts_ot{i}"] = _safe_int(r.get(col))
            # Total
            row["pts_total"] = _safe_int(r.get("PTS"))
            rows.append(row)
    except Exception as exc:
        logger.warning("Failed parsing quarter rows for game %s: %s",
                        game_id, exc)
        return None

    return rows if rows else None


def _safe_int(v) -> int | None:
    """Convert anything to int, returning None for None / NaN / unparseable."""
    if v is None:
        return None
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _is_nan(v) -> bool:
    """Safe NaN check for both pandas NaN and Python None."""
    try:
        import math
        return isinstance(v, float) and math.isnan(v)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def find_missing_games(conn: sqlite3.Connection, limit: int | None = None) -> list[str]:
    """Return Final games that don't yet have quarter scores stored.

    Excludes non-Final games — we only want completed ones.
    """
    query = """
        SELECT g.game_id
        FROM games g
        LEFT JOIN team_quarter_scores qs ON qs.game_id = g.game_id
        WHERE g.status = 'Final'
          AND qs.game_id IS NULL
        ORDER BY g.game_date DESC
    """
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    return [r[0] for r in rows]


def store_quarter_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert rows into team_quarter_scores. Returns number stored."""
    if not rows:
        return 0
    cols = ["game_id", "team_id",
            "pts_q1", "pts_q2", "pts_q3", "pts_q4",
            "pts_ot1", "pts_ot2", "pts_ot3", "pts_ot4",
            "pts_total", "fetched_utc"]
    placeholders = ", ".join("?" * len(cols))
    sql = f"""
        INSERT OR REPLACE INTO team_quarter_scores ({", ".join(cols)})
        VALUES ({placeholders})
    """
    n = 0
    for r in rows:
        try:
            conn.execute(sql, [r.get(c) for c in cols])
            n += 1
        except sqlite3.Error as exc:
            logger.warning("Failed to insert qtr row for %s/%s: %s",
                            r.get("game_id"), r.get("team_id"), exc)
    return n


def backfill_quarter_scores(conn: sqlite3.Connection,
                              limit: int | None = None,
                              sleep_between: float = 0.6) -> dict:
    """Backfill quarter scores for all Final games not yet captured.

    Args:
        conn: open SQLite connection
        limit: max games to process (None = all). Use a small number first
               to validate before doing the full ~1300-game backfill.
        sleep_between: seconds to sleep between API calls to avoid rate-limit.
                        NBA stats throttles aggressively; 0.6s is conservative.

    Returns dict with counts: {games_processed, games_succeeded, games_failed,
    rows_stored}.
    """
    ensure_quarter_schema(conn)
    missing = find_missing_games(conn, limit=limit)

    total = len(missing)
    succeeded = 0
    failed = 0
    rows_stored = 0

    if total == 0:
        logger.info("No missing games — quarter scores up to date.")
        return {"games_processed": 0, "games_succeeded": 0,
                 "games_failed": 0, "rows_stored": 0}

    logger.info("Backfilling quarter scores for %d game(s)...", total)

    for i, gid in enumerate(missing, start=1):
        try:
            rows = fetch_quarter_scores(gid)
            if rows is None:
                failed += 1
            else:
                n = store_quarter_rows(conn, rows)
                rows_stored += n
                succeeded += 1
        except Exception as exc:
            # Catch-all so one bad game can't crash the entire backfill
            logger.warning("Unexpected error processing game %s: %s", gid, exc)
            failed += 1

        # Commit every 25 games so partial progress survives an interruption
        if i % 25 == 0:
            conn.commit()
            logger.info("  [%d/%d] succeeded=%d failed=%d rows=%d",
                         i, total, succeeded, failed, rows_stored)

        # Be polite to NBA's API
        if i < total:
            time.sleep(sleep_between)

    conn.commit()
    logger.info("Backfill complete: %d games processed (succeeded=%d, failed=%d), "
                 "%d rows stored.", total, succeeded, failed, rows_stored)
    return {
        "games_processed": total,
        "games_succeeded": succeeded,
        "games_failed": failed,
        "rows_stored": rows_stored,
    }
