"""NBA Dashboard — Home page.

Run from project root:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st


from lib.data import DB_PATH, db_mtime, latest_loaded_date
from lib.filters import season_filter_picker, SEASON_FILTER_LABELS
from lib.format import HKT, hkt_now_label
from lib.freshness import show_freshness_banner

st.set_page_config(
    page_title="NBA Dashboard — Home",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

from lib.theme import inject_theme
inject_theme(active_page="home")

st.title("🏀 NBA Dashboard")
st.caption("Post-game trend analysis · podcast prep · odds compilation")

# --- DB health banner ----------------------------------------------------
if not DB_PATH.exists():
    st.error(
        "**No database found.** Open Terminal, navigate to your project folder, "
        "activate the venv, and run `python -m scripts.run init` followed by "
        "`python -m scripts.run backfill`."
    )
    st.stop()

mtime = db_mtime()
last_data_date = latest_loaded_date(_mtime=mtime)
# mtime is now an ISO timestamp string (Postgres MAX(last_attempt_utc))
# rather than a float (file mtime). Parse to datetime in HKT for display.
try:
    mtime_dt = datetime.fromisoformat(mtime).astimezone(HKT) if mtime else None
except (ValueError, TypeError):
    mtime_dt = None

# Stale-data warnings (schedule + orphan odds)
show_freshness_banner(mtime)

with st.container(border=True):
    cols = st.columns(3)
    cols[0].metric("Last DB update (HKT)", mtime_dt.strftime("%a %d %b %H:%M") if mtime_dt else "unknown")
    cols[1].metric("Latest game date in DB", last_data_date or "—")
    cols[2].metric("Now", hkt_now_label())

# Global season filter — also surfaces in sidebar for visibility
st.markdown("##### 🎛️ Season filter")
season_filter = season_filter_picker()
st.caption(f"Currently filtering by **{SEASON_FILTER_LABELS[season_filter]}** "
            "across all pages. Change it on any page, it persists.")

st.markdown(
    """
    Use the sidebar to navigate:
    - **Today** — games today, tomorrow, and the next 7 days
    - **Matchup** — pick a game, see everything you need before tip-off
    - **Team Stats** — 4-layer split for all 30 teams, with rank toggle
    - **Player Stats** — 4-layer split for individual players, with percentile toggle

    To refresh the data, run `python -m scripts.run daily` in Terminal.
    """
)

st.sidebar.markdown(
    f"""
    **Data**

    DB file: `{DB_PATH.name}`
    Latest game: `{last_data_date or '—'}`
    """
)
