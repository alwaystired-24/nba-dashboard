"""Team Stats — 4-layer split (Traditional / Advanced / Offence / Defence)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from lib.data import db_mtime, league_team_table, team_recent_games, team_lookup
from lib.filters import layer_picker, window_picker
from lib.format import fmt_num, fmt_pct
from lib.stats import team_layer_columns

st.set_page_config(page_title="Team Stats", page_icon="🏟️", layout="wide")
st.title("🏟️ Team Stats")

mtime = db_mtime()

c1, c2 = st.columns([1, 1])
with c1: window = window_picker(default="Season")
with c2: layer = layer_picker(default="Traditional")

# Build the table
df = league_team_table(window, _mtime=mtime)
specs = team_layer_columns(layer)
keep = ["abbr", "team"] + [c for c, _, _ in specs]
df_disp = df[keep].copy()

# Apply formatters
for col, label, fn in specs:
    df_disp[col] = df_disp[col].apply(fn)

# Rename headers
df_disp = df_disp.rename(columns={
    "abbr": "Tm", "team": "Team",
    **{c: lbl for c, lbl, _ in specs},
})

st.subheader(f"{layer} stats — {window}")
st.caption(f"30 teams · sortable · click a row to see that team's last 20 games")

# Native dataframe with row selection
event = st.dataframe(
    df_disp, hide_index=True, width="stretch", height=600,
    on_select="rerun", selection_mode="single-row",
)

# Drilldown
sel_rows = event.selection.rows if hasattr(event, "selection") else []
if sel_rows:
    row_idx = sel_rows[0]
    row = df.iloc[row_idx]
    team_id = int(row["team_id"])
    team_name = row["team"]
    tlookup = team_lookup(_mtime=mtime)

    st.divider()
    st.subheader(f"📋 {team_name} — last 20 games")

    games = team_recent_games(team_id, last_n=20, _mtime=mtime)
    if games.empty:
        st.caption("No games found.")
    else:
        games = games.copy()
        games["opp"] = games["opp_id"].map(lambda x: tlookup.get(int(x), {}).get("abbreviation", "—"))
        games["score"] = games.apply(lambda r: f"{int(r['pts'])}-{int(r['opp_pts'])}"
                                       if pd.notna(r["pts"]) else "—", axis=1)
        games["fg_pct"] = games["fg_pct"].apply(fmt_pct)
        games["fg3_pct"] = games["fg3_pct"].apply(fmt_pct)
        games["efg_pct"] = games["efg_pct"].apply(fmt_pct)
        games["ts_pct"] = games["ts_pct"].apply(fmt_pct)
        for c in ("off_rating", "def_rating", "net_rating", "pace"):
            games[c] = games[c].apply(fmt_num)

        disp = games[["game_date", "site", "opp", "score",
                       "off_rating", "def_rating", "net_rating", "pace",
                       "efg_pct", "ts_pct", "fg_pct", "fg3_pct"]].rename(columns={
            "game_date": "Date", "site": "H/A", "opp": "OPP", "score": "Score",
            "off_rating": "ORtg", "def_rating": "DRtg", "net_rating": "Net",
            "pace": "Pace", "efg_pct": "eFG%", "ts_pct": "TS%",
            "fg_pct": "FG%", "fg3_pct": "3P%",
        })
        st.dataframe(disp, hide_index=True, width="stretch")
