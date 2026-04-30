"""Player Stats — 4-layer split with percentile (100-0) toggle, position/age filters."""
from __future__ import annotations

import sys
import sqlite3
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from lib.data import DB_PATH, db_mtime, league_player_table, team_lookup
from lib.filters import layer_picker, window_picker
from lib.format import fmt_num, fmt_pct
from lib.stats import player_layer_columns

st.set_page_config(page_title="Player Stats", page_icon="🧍", layout="wide")
st.title("🧍 Player Stats")

mtime = db_mtime()
tlookup = team_lookup(_mtime=mtime)

# Defense-y / lower-is-better → percentile inverted
LOWER_IS_BETTER = {"def_rating", "tov", "pf"}


@st.cache_data(show_spinner=False)
def _player_demographics(_mtime: float) -> pd.DataFrame:
    """Pull demographic columns from players table — handles missing columns gracefully."""
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(players)")}
        select_cols = ["player_id"]
        for c in ("position", "birthdate", "height", "weight", "season_exp"):
            if c in cols:
                select_cols.append(c)
        df = pd.read_sql_query(f"SELECT {', '.join(select_cols)} FROM players", conn)
    # Compute age
    if "birthdate" in df.columns:
        today = pd.Timestamp.today()
        df["age"] = pd.to_datetime(df["birthdate"], errors="coerce").apply(
            lambda d: int((today - d).days / 365.25) if pd.notna(d) else None
        )
    else:
        df["age"] = None
    return df


# --- Filters -------------------------------------------------------------
c1, c2, c3 = st.columns([1, 1, 1])
with c1: window = window_picker(default="Season", key="player_window")
with c2: layer = layer_picker(default="Traditional", key="player_layer")
with c3:
    show_pcts = st.toggle("Show percentile (100–0)", value=False, key="player_pcts",
                            help="Each cell shows percentile rank across all players.")

f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
with f1:
    abbrs = sorted({tlookup[t]["abbreviation"] for t in tlookup})
    teams_sel = st.multiselect("Filter by team(s)", abbrs, default=[])
with f2:
    min_gp = st.number_input("Min GP", min_value=1, max_value=82, value=5)
with f3:
    min_min = st.number_input("Min MIN", min_value=0.0, max_value=48.0, value=12.0, step=1.0)
with f4:
    pass

# Pull demographics for filters
demo = _player_demographics(mtime)

f5, f6 = st.columns(2)
with f5:
    available_pos = [p for p in demo["position"].dropna().unique() if p] if "position" in demo.columns else []
    pos_sel = st.multiselect("Position", sorted(available_pos), default=[])
with f6:
    if demo["age"].notna().any():
        age_min = int(demo["age"].dropna().min())
        age_max = int(demo["age"].dropna().max())
        age_range = st.slider("Age range", age_min, age_max, (age_min, age_max))
    else:
        age_range = None
        st.caption("Age data not loaded. Run `python -m scripts.run demographics` to enable filter.")

# --- Pull player data ----------------------------------------------------
df = league_player_table(window, min_games=int(min_gp), min_minutes=float(min_min), _mtime=mtime)
df = df.merge(demo, on="player_id", how="left")

# Apply filters
if teams_sel:
    df = df[df["team"].isin(teams_sel)]
if pos_sel and "position" in df.columns:
    df = df[df["position"].isin(pos_sel)]
if age_range is not None and "age" in df.columns:
    df = df[df["age"].between(age_range[0], age_range[1]) | df["age"].isna()]

if df.empty:
    st.warning("No players match these filters. Try widening them.")
    st.stop()

specs = player_layer_columns(layer)
keep_internal = ["player", "team", "player_id", "position", "age"] + [c for c, _, _ in specs if c not in ("player", "team")]
df_full = df[[c for c in keep_internal if c in df.columns]].copy()

# Compute percentiles for each spec column (over current filtered set)
percentiles = {}
if show_pcts:
    for col, _, _ in specs:
        if col in df_full.columns and col not in ("gp", "starts"):
            ascending = col in LOWER_IS_BETTER
            percentiles[col] = (df_full[col].rank(pct=True, ascending=ascending) * 100).round(0)

# Format display
df_disp = df_full.copy()
for col, label, fn in specs:
    if col in df_disp.columns:
        if show_pcts and col in percentiles:
            df_disp[col] = [
                f"{fn(v)}  ({int(p)})" if pd.notna(p) else fn(v)
                for v, p in zip(df_disp[col], percentiles[col])
            ]
        else:
            df_disp[col] = df_disp[col].apply(fn)

# Add demographic display columns at front (if present)
display_extras = []
if "position" in df_disp.columns:
    display_extras.append("position")
if "age" in df_disp.columns:
    display_extras.append("age")

view_cols = ["player", "team"] + display_extras + [c for c, _, _ in specs]
view_cols = [c for c in view_cols if c in df_disp.columns]
df_view = df_disp[view_cols].rename(columns={
    "player": "Player", "team": "Tm", "position": "Pos", "age": "Age",
    **{c: lbl for c, lbl, _ in specs},
})

st.subheader(f"{layer} stats — {window}  ·  {len(df_view)} players")
st.caption("Click a row to see that player's last 20 games.")

event = st.dataframe(
    df_view, hide_index=True, width="stretch", height=620,
    on_select="rerun", selection_mode="single-row",
)

# --- Drilldown -----------------------------------------------------------
sel_rows = event.selection.rows if hasattr(event, "selection") else []
if sel_rows:
    row_idx = sel_rows[0]
    row = df_full.iloc[row_idx]
    player_id = int(row["player_id"])
    player_name = row["player"]

    st.divider()
    st.subheader(f"📋 {player_name} — last 20 games")

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
        for c in ("minutes", "pts", "reb", "ast", "stl", "blk", "tov", "off_rating", "def_rating"):
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
