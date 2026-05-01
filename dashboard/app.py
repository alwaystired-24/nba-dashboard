"""NBA Dashboard — Home page.

Run from project root:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from lib.data import DB_PATH, db_mtime, latest_loaded_date
from lib.format import HKT, hkt_now_label
from lib.freshness import show_freshness_banner

st.set_page_config(
    page_title="NBA Dashboard — Home",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
mtime_dt = datetime.fromtimestamp(mtime, tz=HKT)

# Stale-data warnings (schedule + orphan odds)
show_freshness_banner(mtime)

with st.container(border=True):
    cols = st.columns(3)
    cols[0].metric("Last DB update (HKT)", mtime_dt.strftime("%a %d %b %H:%M"))
    cols[1].metric("Latest game date in DB", last_data_date or "—")
    cols[2].metric("Now", hkt_now_label())

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
