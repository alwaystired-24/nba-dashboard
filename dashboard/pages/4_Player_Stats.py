"""Player Stats — 4-layer split (Traditional / Advanced / Offence / Defence)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from lib.data import db_mtime, league_player_table, team_lookup
from lib.filters import layer_picker, window_picker
from lib.stats import player_layer_columns

st.set_page_config(page_title="Player Stats", page_icon="🧍", layout="wide")
st.title("🧍 Player Stats")

mtime = db_mtime()
tlookup = team_lookup(_mtime=mtime)

# --- Filters -------------------------------------------------------------
c1, c2 = st.columns([1, 1])
with c1: window = window_picker(default="Season", key="player_window")
with c2: layer = layer_picker(default="Traditional", key="player_layer")

f1, f2, f3 = st.columns([2, 1, 1])
with f1:
    abbrs = sorted({tlookup[t]["abbreviation"] for t in tlookup})
    teams_sel = st.multiselect("Filter by team(s)", abbrs, default=[])
with f2:
    min_gp = st.number_input("Min GP", min_value=1, max_value=82, value=5)
with f3:
    min_min = st.number_input("Min MIN", min_value=0.0, max_value=48.0, value=12.0, step=1.0)

# --- Pull data -----------------------------------------------------------
df = league_player_table(window, min_games=int(min_gp), min_minutes=float(min_min), _mtime=mtime)
if teams_sel:
    df = df[df["team"].isin(teams_sel)]
if df.empty:
    st.warning("No players match these filters. Try lowering Min GP / Min MIN.")
    st.stop()

specs = player_layer_columns(layer)
keep = ["player", "team"] + [c for c, _, _ in specs]
df_disp = df[keep].copy()
df_raw_for_drill = df.copy()

for col, label, fn in specs:
    df_disp[col] = df_disp[col].apply(fn)

df_disp = df_disp.rename(columns={
    "player": "Player", "team": "Tm",
    **{c: lbl for c, lbl, _ in specs},
})

st.subheader(f"{layer} stats — {window}  ·  {len(df_disp)} players")

event = st.dataframe(
    df_disp, hide_index=True, width="stretch", height=620,
    on_select="rerun", selection_mode="single-row",
)

# --- Drilldown -----------------------------------------------------------
sel_rows = event.selection.rows if hasattr(event, "selection") else []
if sel_rows:
    row_idx = sel_rows[0]
    row = df_raw_for_drill.iloc[row_idx]
    player_id = int(row["player_id"])
    player_name = row["player"]

    st.divider()
    st.subheader(f"📋 {player_name} — last 20 games")

    import sqlite3
    from lib.data import DB_PATH
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    games = pd.read_sql_query(
        """
        SELECT g.game_date,
               CASE WHEN g.home_team_id = pbt.team_id THEN 'H' ELSE 'A' END AS site,
               t_opp.abbreviation AS opp,
               pbt.minutes, pbt.pts, pbt.reb, pbt.ast, pbt.stl, pbt.blk, pbt.tov,
               pbt.fg_pct, pbt.fg3_pct, pbt.ft_pct,
               pba.usg_pct, pba.efg_pct, pba.ts_pct, pba.pie,
               pba.off_rating, pba.def_rating
        FROM player_box_traditional pbt
        JOIN games g ON g.game_id = pbt.game_id AND g.status = 'Final'
        LEFT JOIN player_box_advanced pba
          ON pba.game_id = pbt.game_id AND pba.player_id = pbt.player_id
        JOIN teams t_opp ON t_opp.team_id =
            CASE WHEN g.home_team_id = pbt.team_id THEN g.away_team_id ELSE g.home_team_id END
        WHERE pbt.player_id = ?
        ORDER BY g.game_date DESC
        LIMIT 20
        """,
        conn, params=(player_id,),
    )
    conn.close()

    if games.empty:
        st.caption("No games found.")
    else:
        from lib.format import fmt_num, fmt_pct
        for c in ("minutes", "pts", "reb", "ast", "stl", "blk", "tov",
                  "off_rating", "def_rating"):
            games[c] = games[c].apply(fmt_num)
        for c in ("fg_pct", "fg3_pct", "ft_pct", "efg_pct", "ts_pct"):
            games[c] = games[c].apply(fmt_pct)
        for c in ("usg_pct", "pie"):
            games[c] = games[c].apply(fmt_num)

        disp = games.rename(columns={
            "game_date": "Date", "site": "H/A", "opp": "OPP",
            "minutes": "MIN", "pts": "PTS", "reb": "REB", "ast": "AST",
            "stl": "STL", "blk": "BLK", "tov": "TOV",
            "fg_pct": "FG%", "fg3_pct": "3P%", "ft_pct": "FT%",
            "usg_pct": "USG%", "efg_pct": "eFG%", "ts_pct": "TS%", "pie": "PIE",
            "off_rating": "ORtg", "def_rating": "DRtg",
        })
        st.dataframe(disp, hide_index=True, width="stretch")
