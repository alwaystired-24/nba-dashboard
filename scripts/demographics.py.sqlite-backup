"""Pull player demographics (position, age, height, etc.) from CommonPlayerInfo.

This is a ONE-TIME backfill that adds metadata to the players table.
Re-running is safe — it skips already-fetched players and only fetches new ones.

Note: Column names match the existing schema (height as 'height' text,
weight as 'weight' int, etc.).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from nba_api.stats.endpoints import commonplayerinfo

from .nba import call_with_retry

logger = logging.getLogger(__name__)


# =========================================================================
# SCHEMA MIGRATION (legacy — schema already includes these. Kept for older DBs.)
# =========================================================================

_DEMOGRAPHIC_COLUMNS = [
    ("position", "TEXT"),
    ("birthdate", "TEXT"),
    ("height", "TEXT"),
    ("weight", "INTEGER"),
    ("jersey", "TEXT"),
    ("team_id", "INTEGER"),
    ("draft_year", "INTEGER"),
    ("country", "TEXT"),
    ("season_exp", "INTEGER"),
    ("info_fetched", "TEXT"),
]


def ensure_demographic_columns(conn: sqlite3.Connection) -> None:
    """Add demographic columns to the players table if missing. Idempotent."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(players)")}
    for col_name, col_type in _DEMOGRAPHIC_COLUMNS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE players ADD COLUMN {col_name} {col_type}")
            logger.info("Added column players.%s", col_name)


# =========================================================================
# PARSING HELPERS
# =========================================================================

def _safe_int(x: Any) -> int | None:
    if x is None or x == "":
        return None
    try:
        return int(x)
    except (ValueError, TypeError):
        return None


def _normalize_position(pos: Any) -> str | None:
    """Position from API like 'Forward' / 'Guard-Forward'. Map to G/F/C bucket."""
    if not pos or not isinstance(pos, str):
        return None
    p = pos.strip().lower()
    mapping = {
        "guard": "G",
        "forward": "F",
        "center": "C",
        "guard-forward": "G-F",
        "forward-guard": "G-F",
        "forward-center": "F-C",
        "center-forward": "F-C",
    }
    return mapping.get(p, p[:3].upper())


# =========================================================================
# FETCH ONE PLAYER
# =========================================================================

def fetch_player_demographics(player_id: int) -> dict | None:
    info = call_with_retry(commonplayerinfo.CommonPlayerInfo, player_id=player_id)
    df = info.common_player_info.get_data_frame()
    if df.empty:
        return None
    r = df.iloc[0].to_dict()

    return {
        "player_id": int(r["PERSON_ID"]),
        "position": _normalize_position(r.get("POSITION")),
        "birthdate": (str(r.get("BIRTHDATE"))[:10] if r.get("BIRTHDATE") else None),
        "height": str(r.get("HEIGHT") or "") or None,  # "6-7" string
        "weight": _safe_int(r.get("WEIGHT")),
        "jersey": str(r.get("JERSEY") or "") or None,
        "team_id": _safe_int(r.get("TEAM_ID")) or None,
        "draft_year": _safe_int(r.get("DRAFT_YEAR")),
        "country": str(r.get("COUNTRY") or "") or None,
        "season_exp": _safe_int(r.get("SEASON_EXP")),
        "info_fetched": datetime.now(timezone.utc).isoformat(),
    }


# =========================================================================
# DRIVER
# =========================================================================

def players_missing_demographics(conn: sqlite3.Connection) -> list[int]:
    """Player IDs without demographics yet."""
    rows = conn.execute(
        "SELECT player_id FROM players WHERE info_fetched IS NULL ORDER BY player_id"
    ).fetchall()
    return [r["player_id"] if hasattr(r, "keys") else r[0] for r in rows]


def backfill_demographics(conn: sqlite3.Connection,
                            limit: int | None = None,
                            refresh: bool = False) -> tuple[int, int]:
    """Returns (success, fail) counts.

    Skips already-fetched players unless refresh=True.
    """
    ensure_demographic_columns(conn)

    if refresh:
        rows = conn.execute("SELECT player_id FROM players ORDER BY player_id").fetchall()
        ids = [r["player_id"] if hasattr(r, "keys") else r[0] for r in rows]
    else:
        ids = players_missing_demographics(conn)

    if limit:
        ids = ids[:limit]

    success = fail = 0
    for i, pid in enumerate(ids, 1):
        try:
            row = fetch_player_demographics(pid)
            if row is None:
                fail += 1
                logger.warning("No data for player %d", pid)
                continue
            update_cols = [k for k in row.keys() if k != "player_id"]
            placeholders = ", ".join(f"{c} = :{c}" for c in update_cols)
            conn.execute(
                f"UPDATE players SET {placeholders} WHERE player_id = :player_id",
                row,
            )
            conn.commit()
            success += 1
        except Exception as exc:
            fail += 1
            logger.warning("Demographics fetch failed for %d: %s", pid, exc)

        if i % 25 == 0 or i == len(ids):
            print(f"  [{i}/{len(ids)}] success={success}  failed={fail}")

    return success, fail
