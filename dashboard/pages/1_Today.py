"""Today's Games + upcoming schedule."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

# Make `lib` importable when Streamlit runs this file directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from lib.data import (
    db_mtime,
    games_in_window,
    games_on_date,
    latest_loaded_date,
    team_record,
    team_aggregate,
)
from lib.format import (
    fmt_int,
    fmt_num,
    hkt_to_et_date,
    hkt_today,
    matchup_label,
    status_badge,
)

st.set_page_config(page_title="Today's Games", page_icon="📅", layout="wide")
st.title("📅 Today's Games")

mtime = db_mtime()

# --- Date picker ---------------------------------------------------------
left, right = st.columns([1, 3])
with left:
    today_hkt = hkt_today()
    picked_hkt = st.date_input(
        "Date (HKT)",
        value=date.fromisoformat(today_hkt),
        help="NBA games on ET date X show up here on HKT date X+1.",
    )
with right:
    use_hkt = st.toggle("Map ET → HKT date", value=True,
                        help="Off = look up by raw ET date instead.")

# Translate the picked HKT date to the ET date the games are stored under
target_et = hkt_to_et_date(picked_hkt.isoformat()) if use_hkt else picked_hkt.isoformat()
st.caption(f"Looking up ET date: **{target_et}**")

# --- Today's games -------------------------------------------------------
games_today = games_on_date(target_et, _mtime=mtime)
if games_today.empty:
    last = latest_loaded_date(_mtime=mtime)
    st.info(
        f"No games found for ET date {target_et}. "
        f"Latest game date in your database: **{last or '—'}**. "
        "If today is an NBA off-day, this is normal. Otherwise, run `python -m scripts.run daily`."
    )
else:
    st.subheader(f"{len(games_today)} game{'s' if len(games_today) != 1 else ''}")

    for _, g in games_today.iterrows():
        with st.container(border=True):
            top = st.columns([3, 1, 1, 1])
            top[0].markdown(f"### {matchup_label(g['home_abbr'], g['away_abbr'])}")
            top[1].markdown(f"**{g['season_type']}**")
            top[2].markdown(status_badge(g["status"]))
            if g["status"] == "Final":
                top[3].markdown(f"**{int(g['away_score'])} – {int(g['home_score'])}**")

            # For finished or scheduled games, show a quick form line per team
            mid = st.columns(2)
            for col, side in zip(mid, ("away", "home")):
                tid = int(g[f"{side}_team_id"])
                name = g[f"{side}_name"]
                w, l = team_record(tid, "L10", _mtime=mtime)
                agg = team_aggregate(tid, "L10", _mtime=mtime)
                col.markdown(
                    f"**{name}**  ·  L10: `{w}-{l}`  ·  "
                    f"ORtg `{fmt_num(agg.get('off_rating'))}`  ·  "
                    f"DRtg `{fmt_num(agg.get('def_rating'))}`  ·  "
                    f"Pace `{fmt_num(agg.get('pace'))}`"
                )

            st.page_link("pages/2_Matchup.py", label="🔍 Open Matchup view",
                          help="Deep dive on this game", width="content")

# --- Upcoming next 3 days ------------------------------------------------
st.divider()
st.subheader("Next 3 days")

start = (date.fromisoformat(target_et) + timedelta(days=1)).isoformat()
end = (date.fromisoformat(target_et) + timedelta(days=3)).isoformat()
upcoming = games_in_window(start, end, _mtime=mtime)

if upcoming.empty:
    st.caption("No games scheduled in the next 3 days, or schedule not yet loaded.")
else:
    for d, group in upcoming.groupby("game_date"):
        st.markdown(f"#### {d}")
        for _, g in group.iterrows():
            line = (f"- **{matchup_label(g['home_abbr'], g['away_abbr'])}** "
                    f"({g['season_type']})  ·  {status_badge(g['status'])}")
            if g["status"] == "Final":
                line += f"  ·  **{int(g['away_score'])} – {int(g['home_score'])}**"
            st.markdown(line)
