"""Stale-data warning banner. Shows on every dashboard page.

Detects two conditions:
1. Schedule is stale — latest game date in DB is >2 days before today HKT
2. Odds have orphans — odds_event_mapping has rows where game_id IS NULL
   AND those events have commence_utc within the last 30 days
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import streamlit as st

from .data import DB_PATH, latest_loaded_date
from .format import hkt_today


@st.cache_data(show_spinner=False, ttl=60)  # 60s cache so banner doesn't query on every rerun
def _orphan_odds_count(_mtime: float) -> int:
    """Count unmatched odds events from the last 30 days."""
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM odds_event_mapping
                WHERE game_id IS NULL
                  AND date(commence_utc) >= date('now', '-30 days')
                """
            ).fetchone()
            return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        # Tables don't exist yet (fresh DB) — no orphans to warn about
        return 0


def show_freshness_banner(_mtime: float) -> None:
    """Render warning banner if data is stale. Call at top of every page."""
    today = date.fromisoformat(hkt_today())
    last = latest_loaded_date(_mtime=_mtime)

    warnings = []

    # Schedule freshness check
    if last:
        try:
            last_dt = date.fromisoformat(last)
            days_stale = (today - last_dt).days
            if days_stale > 2:
                warnings.append(
                    f"📅 **Schedule is {days_stale} days stale** "
                    f"(latest game: {last}). "
                    "Run `python -m scripts.run daily` to refresh."
                )
        except ValueError:
            pass
    else:
        warnings.append(
            "📅 **No schedule data found.** "
            "Run `python -m scripts.run init && python -m scripts.run backfill`."
        )

    # Orphan odds check
    orphans = _orphan_odds_count(_mtime)
    if orphans > 0:
        warnings.append(
            f"💰 **{orphans} odds events without matching games.** "
            "Refreshing the schedule + running `python -m scripts.run odds --phase manual` "
            "will rematch them."
        )

    if warnings:
        msg = "  \n".join(warnings)
        st.warning(msg, icon="⚠️")
