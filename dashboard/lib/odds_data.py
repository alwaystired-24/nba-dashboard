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

    Includes opening / pre_game / closing phases. Returns empty DataFrame
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
                        WHEN 'opening'   THEN 1
                        WHEN 'pre_game' THEN 2
                        WHEN 'closing'     THEN 3
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


@st.cache_data(show_spinner=False)
def odds_compact_view(game_id: str, _mtime: float) -> dict:
    """Goaloo-style compact view: opening line + latest line per market.

    Returns a dict shaped like:
    {
        "spreads": {
            "book": "draftkings",
            "open":   {"line": -2.5, "home_price": 1.91, "away_price": 1.91, "fetched_utc": "..."},
            "latest": {"line": -3.0, "home_price": 1.95, "away_price": 1.87, "fetched_utc": "..."},
            "n_phases": 4,
            "moved": True,
        },
        "totals": {...},
        "h2h":    {...} or None if not captured
    }

    Strategy:
        1. Pick the bookmaker whose MOST RECENT snapshot is freshest (covers
           both DK and FD, picks whichever updated last).
        2. Open = earliest snapshot for that book/market on this game.
        3. Latest = most recent snapshot for that book/market on this game.
    """
    if not game_id:
        return {}
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
                ORDER BY fetched_utc ASC
                """,
                conn, params=(game_id,),
            )
    except sqlite3.OperationalError:
        return {}

    if df.empty:
        return {}

    # Pick the bookmaker with most-recent snapshot across any market
    df_sorted = df.sort_values("fetched_utc", ascending=False)
    canonical_book = df_sorted.iloc[0]["bookmaker"]

    out = {}
    for market in ["spreads", "totals", "h2h"]:
        market_df = df[(df["market"] == market) & (df["bookmaker"] == canonical_book)]
        if market_df.empty:
            # Fall back to the OTHER book if canonical doesn't have this market
            market_df = df[df["market"] == market]
            if market_df.empty:
                out[market] = None
                continue
            book_for_this_market = market_df.iloc[0]["bookmaker"]
        else:
            book_for_this_market = canonical_book

        market_df = market_df.sort_values("fetched_utc")
        first = market_df.iloc[0]
        last = market_df.iloc[-1]

        if market == "spreads":
            open_line = first["spread_home"]
            latest_line = last["spread_home"]
            open_home_p = first["home_price"]
            open_away_p = first["away_price"]
            latest_home_p = last["home_price"]
            latest_away_p = last["away_price"]
        elif market == "totals":
            open_line = first["total_line"]
            latest_line = last["total_line"]
            open_home_p = first["over_price"]
            open_away_p = first["under_price"]
            latest_home_p = last["over_price"]
            latest_away_p = last["under_price"]
        else:  # h2h moneyline
            open_line = None
            latest_line = None
            open_home_p = first["home_price"]
            open_away_p = first["away_price"]
            latest_home_p = last["home_price"]
            latest_away_p = last["away_price"]

        line_moved = open_line != latest_line if open_line is not None else False
        price_moved = (open_home_p != latest_home_p) or (open_away_p != latest_away_p)

        out[market] = {
            "book": book_for_this_market,
            "open": {
                "line": open_line,
                "home_price": open_home_p,
                "away_price": open_away_p,
                "fetched_utc": first["fetched_utc"],
                "phase": first["snapshot_phase"],
            },
            "latest": {
                "line": latest_line,
                "home_price": latest_home_p,
                "away_price": latest_away_p,
                "fetched_utc": last["fetched_utc"],
                "phase": last["snapshot_phase"],
            },
            "n_phases": len(market_df),
            "moved": line_moved or price_moved,
        }

    return out
