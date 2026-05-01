"""Database queries for odds data — used by Matchup page."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from .data import DB_PATH


@st.cache_data(show_spinner=False)
def odds_for_game(game_id: str, _mtime: float) -> pd.DataFrame:
    """Return all odds snapshots for a game, sorted by phase + book + market.

    Includes opener / pre_game / late phases. Returns empty DataFrame
    if no odds exist for the game (or odds_snapshots table is empty).
    """
    if not game_id:
        return pd.DataFrame()
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            df = pd.read_sql_query(
                """
                SELECT snapshot_phase, bookmaker, market, fetched_utc,
                       home_price, away_price,
                       spread_home, spread_away,
                       total_line, over_price, under_price
                FROM odds_snapshots
                WHERE game_id = ?
                ORDER BY
                    CASE snapshot_phase
                        WHEN 'opener'   THEN 1
                        WHEN 'pre_game' THEN 2
                        WHEN 'late'     THEN 3
                        ELSE 4
                    END,
                    bookmaker, market
                """,
                conn, params=(game_id,),
            )
        return df
    except sqlite3.OperationalError:
        # Table doesn't exist yet — fresh DB
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def odds_event_for_game(game_id: str, _mtime: float) -> dict | None:
    """Get the odds_event_mapping row for a game (gives us the event_id, commence time)."""
    if not game_id:
        return None
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT event_id, commence_utc, home_team_name, away_team_name "
                "FROM odds_event_mapping WHERE game_id = ?",
                (game_id,),
            ).fetchone()
            if row:
                return {"event_id": row[0], "commence_utc": row[1],
                         "home_team_name": row[2], "away_team_name": row[3]}
    except sqlite3.OperationalError:
        return None
    return None
