"""Today's Games + upcoming schedule, grouped by HKT date."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from lib.data import (
    db_mtime,
    games_in_window,
    latest_loaded_date,
    team_aggregate,
    team_record,
    all_team_injury_counts,
)
from lib.freshness import show_freshness_banner
from lib.filters import season_filter_picker, SEASON_FILTER_LABELS
from lib.format import (
    fmt_num,
    hkt_to_et_date,
    hkt_today,
    matchup_label,
    status_badge,
)

st.set_page_config(page_title="Today's Games", page_icon="📅", layout="wide")
st.title("📅 Today & Upcoming")

mtime = db_mtime()
show_freshness_banner(mtime)

season_filter = season_filter_picker()
st.caption(f"Showing **{SEASON_FILTER_LABELS[season_filter]}** form previews. "
            "Change at top of any page.")

injury_counts = all_team_injury_counts(_mtime=mtime)

# --- Range we want: yesterday, today, tomorrow, +5 more ----------------
today = date.fromisoformat(hkt_today())
hkt_window_start = today - timedelta(days=1)
hkt_window_end = today + timedelta(days=7)
et_window_start = hkt_to_et_date(hkt_window_start.isoformat())
et_window_end = hkt_to_et_date(hkt_window_end.isoformat())

games = games_in_window(et_window_start, et_window_end, _mtime=mtime)
if games.empty:
    last = latest_loaded_date(_mtime=mtime)
    st.info(
        f"No games found in this date range. "
        f"Latest game date in your database: **{last or '—'}**. "
        "Run `python -m scripts.run daily` to refresh."
    )
    st.stop()

# --- Bucket games by HKT date label ------------------------------------
# game_date is ET; HKT date = ET date + 1 (NBA games are evening ET = morning HKT next day)
def _hkt_label(et_date_str: str) -> str:
    et = date.fromisoformat(et_date_str)
    hkt = et + timedelta(days=1)
    delta = (hkt - today).days
    if delta == -1: return "Yesterday"
    if delta == 0:  return "Today"
    if delta == 1:  return "Tomorrow"
    if 2 <= delta <= 7:
        return hkt.strftime("%a %d %b")
    return hkt.isoformat()

games = games.assign(hkt_label=games["game_date"].apply(_hkt_label))

# --- Section per HKT bucket --------------------------------------------
ordering = ["Yesterday", "Today", "Tomorrow"]
seen_labels: list[str] = []
for lbl in ordering:
    sub = games[games["hkt_label"] == lbl]
    if not sub.empty:
        seen_labels.append(lbl)
# Then add the rest in date order
other = sorted(
    {l for l in games["hkt_label"].unique() if l not in ordering},
    key=lambda l: games[games["hkt_label"] == l]["game_date"].min(),
)
seen_labels.extend(other)

for label in seen_labels:
    bucket = games[games["hkt_label"] == label].sort_values("game_id")
    finished = (bucket["status"] == "Final").sum()
    total = len(bucket)
    st.subheader(f"{label}  ·  {total} game{'s' if total != 1 else ''}"
                  + (f"  ·  {finished} final" if finished else ""))

    # Two-column card layout
    cols = st.columns(2)
    for i, (_, g) in enumerate(bucket.iterrows()):
        with cols[i % 2]:
            with st.container(border=True):
                top = st.columns([3, 1])
                top[0].markdown(f"### {matchup_label(g['home_abbr'], g['away_abbr'])}")
                top[1].markdown(status_badge(g["status"]))

                if g["status"] == "Final" and g["home_score"] is not None:
                    st.markdown(
                        f"**Final:**  {g['away_abbr']} {int(g['away_score'])} — "
                        f"{int(g['home_score'])} {g['home_abbr']}"
                    )
                else:
                    # Show form preview for upcoming
                    away_w, away_l = team_record(int(g["away_team_id"]), "L10", season_filter, _mtime=mtime)
                    home_w, home_l = team_record(int(g["home_team_id"]), "L10", season_filter, _mtime=mtime)
                    away_agg = team_aggregate(int(g["away_team_id"]), "L10", season_filter, _mtime=mtime)
                    home_agg = team_aggregate(int(g["home_team_id"]), "L10", season_filter, _mtime=mtime)
                    st.markdown(
                        f"**{g['away_abbr']}** L10 `{away_w}-{away_l}`  ·  "
                        f"ORtg `{fmt_num(away_agg.get('off_rating'))}`  ·  "
                        f"DRtg `{fmt_num(away_agg.get('def_rating'))}`"
                    )
                    st.markdown(
                        f"**{g['home_abbr']}** L10 `{home_w}-{home_l}`  ·  "
                        f"ORtg `{fmt_num(home_agg.get('off_rating'))}`  ·  "
                        f"DRtg `{fmt_num(home_agg.get('def_rating'))}`"
                    )

                # Injury counts (Out/Doubtful/Suspended only — actionable)
                away_inj = injury_counts.get(int(g["away_team_id"]), 0)
                home_inj = injury_counts.get(int(g["home_team_id"]), 0)
                if away_inj or home_inj:
                    inj_parts = []
                    if away_inj:
                        emoji = "🚨" if away_inj >= 3 else "⚠️"
                        inj_parts.append(f"{emoji} {g['away_abbr']}: {away_inj}")
                    else:
                        inj_parts.append(f"✅ {g['away_abbr']}: 0")
                    if home_inj:
                        emoji = "🚨" if home_inj >= 3 else "⚠️"
                        inj_parts.append(f"{emoji} {g['home_abbr']}: {home_inj}")
                    else:
                        inj_parts.append(f"✅ {g['home_abbr']}: 0")
                    st.caption("Injuries — " + "  ·  ".join(inj_parts))

                meta = []
                if g["season_type"] != "Regular":
                    meta.append(g["season_type"])
                meta.append(f"ET {g['game_date']}")
                st.caption("  ·  ".join(meta))
    st.divider()
