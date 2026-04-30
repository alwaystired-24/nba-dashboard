"""Team Stats — 4-layer split with rank toggle (1-30) and league average row."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from lib.data import db_mtime, league_team_table, team_lookup, team_recent_games
from lib.filters import layer_picker, window_picker
from lib.format import fmt_num, fmt_pct
from lib.stats import team_layer_columns

st.set_page_config(page_title="Team Stats", page_icon="🏟️", layout="wide")
st.title("🏟️ Team Stats")

mtime = db_mtime()

# Defense-y / lower-is-better columns — rank inverted
LOWER_IS_BETTER = {
    "def_rating", "tov_pct", "tov", "pf",
    "opp_pts", "opp_fg_pct", "opp_fg3_pct", "opp_fg3a", "opp_fga",
    "opp_efg_pct", "opp_ts_pct", "opp_tov_pct", "opp_ast", "opp_reb",
    "opp_oreb",
    "l",  # losses — lower is better
}


c1, c2, c3 = st.columns([1, 1, 1])
with c1: window = window_picker(default="Season")
with c2: layer = layer_picker(default="Traditional")
with c3:
    show_ranks = st.toggle("Show rank (1–30)", value=False,
                            help="Show each team's rank for each metric.")

# Build the table
df = league_team_table(window, _mtime=mtime)
specs = team_layer_columns(layer)
keep = ["abbr", "team"] + [c for c, _, _ in specs]
df_full = df[keep + ["team_id"]].copy()  # keep team_id for drilldown

# Compute ranks if requested (even if not shown, used for color)
ranks = {}
for col, _, _ in specs:
    if col not in df_full.columns:
        continue
    if col in ("gp", "w"):
        # neutral — don't rank
        continue
    if col in LOWER_IS_BETTER:
        ranks[col] = df_full[col].rank(ascending=True, method="min")
    else:
        ranks[col] = df_full[col].rank(ascending=False, method="min")

# Format display values
df_disp = df_full.copy()
for col, label, fn in specs:
    if col in df_disp.columns:
        if show_ranks and col in ranks:
            df_disp[col] = [
                f"{fn(v)}  ({int(r)})" if pd.notna(r) else fn(v)
                for v, r in zip(df_disp[col], ranks[col])
            ]
        else:
            df_disp[col] = df_disp[col].apply(fn)

# Append league average row
lg_row = {"abbr": "—", "team": "League avg", "team_id": -1}
for col, _, fn in specs:
    if col in df_full.columns and col not in ("w", "l", "gp"):
        lg_row[col] = fn(df_full[col].mean())
    elif col in ("w", "l", "gp"):
        lg_row[col] = fn(df_full[col].mean())
    else:
        lg_row[col] = "—"

df_disp_with_avg = pd.concat([df_disp, pd.DataFrame([lg_row])], ignore_index=True)

# Drop team_id from view, rename headers
df_view = df_disp_with_avg.drop(columns=["team_id"]).rename(columns={
    "abbr": "Tm", "team": "Team",
    **{c: lbl for c, lbl, _ in specs},
})

st.subheader(f"{layer} stats — {window}")
st.caption(f"30 teams + league average row · sortable · click a row to see that team's last 20 games")

event = st.dataframe(
    df_view, hide_index=True, width="stretch", height=620,
    on_select="rerun", selection_mode="single-row",
)

# Drilldown
sel_rows = event.selection.rows if hasattr(event, "selection") else []
if sel_rows:
    row_idx = sel_rows[0]
    if row_idx < len(df_full):  # not the league-avg row
        row = df_full.iloc[row_idx]
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
            games["score"] = games.apply(
                lambda r: f"{int(r['pts'])}-{int(r['opp_pts'])}" if pd.notna(r["pts"]) else "—",
                axis=1,
            )
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
