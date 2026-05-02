"""Player Stats — 4-layer split with sidebar filters and clickable drilldown."""
from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from lib.data import DB_PATH, db_mtime, league_player_table, team_lookup
from lib.freshness import show_freshness_banner
from lib.filters import layer_picker, window_picker, season_filter_picker, SEASON_FILTER_LABELS
from lib.format import fmt_num, fmt_pct
from lib.stats import player_layer_columns

st.set_page_config(page_title="Player Stats", page_icon="🧍", layout="wide")
st.title("🧍 Player Stats")

mtime = db_mtime()
show_freshness_banner(mtime)
tlookup = team_lookup(_mtime=mtime)

LOWER_IS_BETTER = {"def_rating", "tov", "pf"}


@st.cache_data(show_spinner=False)
def _player_demographics(_mtime: float) -> pd.DataFrame:
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(players)")}
        select_cols = ["player_id"]
        for c in ("position", "birthdate", "height", "weight", "season_exp"):
            if c in cols:
                select_cols.append(c)
        df = pd.read_sql_query(f"SELECT {', '.join(select_cols)} FROM players", conn)
    if "birthdate" in df.columns:
        today = pd.Timestamp.today()
        df["age"] = pd.to_datetime(df["birthdate"], errors="coerce").apply(
            lambda d: int((today - d).days / 365.25) if pd.notna(d) else None
        )
    else:
        df["age"] = None
    return df


# =========================================================================
# TOP CONTROLS
# =========================================================================
c1, c2, c3 = st.columns([1, 1, 1])
with c1: window = window_picker(default="Season", key="player_window")
with c2: layer = layer_picker(default="Traditional", key="player_layer")
with c3:
    show_pcts = st.toggle("Show percentile (100 = best)", value=False, key="player_pcts",
                            help="Adds a percentile column for each metric. 100 = best, 0 = worst.")

season_filter = season_filter_picker()
st.caption(f"Showing **{SEASON_FILTER_LABELS[season_filter]}** stats. "
            "Change at top of any page.")

# =========================================================================
# SIDEBAR FILTERS
# =========================================================================
demo = _player_demographics(mtime)
abbrs = sorted({tlookup[t]["abbreviation"] for t in tlookup})
available_pos = sorted([p for p in demo["position"].dropna().unique() if p]) if "position" in demo.columns else []

with st.sidebar:
    st.markdown("### 🎛️ Filters")
    teams_sel = st.multiselect("Team(s)", abbrs, default=[], key="ps_teams")
    pos_sel = st.multiselect("Position", available_pos, default=[], key="ps_pos")
    if "age" in demo.columns and demo["age"].notna().any():
        age_min = int(demo["age"].dropna().min())
        age_max = int(demo["age"].dropna().max())
        age_range = st.slider("Age range", age_min, age_max, (age_min, age_max), key="ps_age")
    else:
        age_range = None
        st.caption("Age data unavailable — run `python -m scripts.run demographics`")
    # Defaults adapt to season type — playoffs has fewer games, so lower threshold
    if season_filter == "playoffs":
        default_gp, default_min = 1, 0.0
        gp_help = "Min playoff games. Default lowered to 1 since playoffs are short."
    else:
        default_gp, default_min = 5, 12.0
        gp_help = None
    min_gp = st.number_input("Min GP", min_value=1, max_value=82,
                              value=default_gp, key=f"ps_mingp_{season_filter}",
                              help=gp_help)
    min_min = st.number_input("Min MIN", min_value=0.0, max_value=48.0,
                                value=default_min, step=1.0,
                                key=f"ps_minmin_{season_filter}")

    active = []
    if teams_sel: active.append(f"{len(teams_sel)} team(s)")
    if pos_sel: active.append(f"{len(pos_sel)} pos")
    if age_range and (age_range[0] != age_min or age_range[1] != age_max):
        active.append(f"age {age_range[0]}–{age_range[1]}")
    if min_gp != default_gp: active.append(f"GP≥{min_gp}")
    if min_min != default_min: active.append(f"MIN≥{min_min}")
    if active:
        st.markdown(f"**Active:** {', '.join(active)}")
    else:
        st.caption("No filters active (defaults shown)")

# =========================================================================
# DATA
# =========================================================================
df = league_player_table(window, min_games=int(min_gp), min_minutes=float(min_min),
                          season_filter=season_filter, _mtime=mtime)
df = df.merge(demo, on="player_id", how="left")

if teams_sel:
    df = df[df["team"].isin(teams_sel)]
if pos_sel and "position" in df.columns:
    df = df[df["position"].isin(pos_sel)]
if age_range is not None and "age" in df.columns:
    df = df[df["age"].between(age_range[0], age_range[1]) | df["age"].isna()]

if df.empty:
    st.warning("No players match these filters. Try widening them.")
    st.stop()

# =========================================================================
# BUILD DISPLAY DATAFRAME
# =========================================================================
specs = player_layer_columns(layer)

base_cols = ["player", "team"]
if "position" in df.columns: base_cols.append("position")
if "age" in df.columns: base_cols.append("age")
stat_cols = [c for c, _, _ in specs if c in df.columns]
df_view = df[base_cols + stat_cols + ["player_id"]].copy().reset_index(drop=True)

# Percentile computation — 100 = best
if show_pcts:
    for col, _, _ in specs:
        if col in df_view.columns and col not in ("gp", "starts"):
            if col in LOWER_IS_BETTER:
                pct = df_view[col].rank(pct=True, ascending=False) * 100
            else:
                pct = df_view[col].rank(pct=True, ascending=True) * 100
            df_view[f"{col}_pct"] = pct.round(0).astype("Int64")

# Convert ratio columns to display percentages (for shooting %)
for col, _, fn in specs:
    if col in df_view.columns and fn is fmt_pct:
        df_view[col] = df_view[col] * 100

# Order columns: identity → for each stat: value, then pct (if on)
ordered = ["player", "team"]
if "position" in df_view.columns: ordered.append("position")
if "age" in df_view.columns: ordered.append("age")
for col, _, _ in specs:
    if col in df_view.columns:
        ordered.append(col)
        if show_pcts and f"{col}_pct" in df_view.columns:
            ordered.append(f"{col}_pct")
df_view = df_view[ordered + ["player_id"]]

# Build column_config — clickable rows means we use NumberColumn formats per column
col_config = {
    "player": st.column_config.TextColumn("Player"),
    "team": st.column_config.TextColumn("Tm"),
    "position": st.column_config.TextColumn("Pos"),
    "age": st.column_config.NumberColumn("Age", format="%d"),
    "player_id": None,
}

for col, label, fn in specs:
    if col not in df_view.columns:
        continue
    if fn is fmt_pct:
        col_config[col] = st.column_config.NumberColumn(label, format="%.1f")
    elif fn is fmt_num:
        col_config[col] = st.column_config.NumberColumn(label, format="%.1f")
    else:
        col_config[col] = st.column_config.NumberColumn(label, format="%d")
    # Percentile column gets a unique internal name but displays as "#"
    pct_internal = f"{col}_pct"
    if show_pcts and pct_internal in df_view.columns:
        col_config[pct_internal] = st.column_config.NumberColumn(
            f"{label}#", format="%d",
            help=f"{label} percentile rank (100 = best in league among filtered players)",
        )

st.subheader(f"{layer} stats — {window}  ·  {len(df_view)} players")
st.caption("Click any column header to sort. Pick a player below to drill in.")

if show_pcts:
    # Build {value_col: pct_col} mapping
    from lib.coloring import style_dataframe_by_percentiles
    pct_map = {}
    for col, _, _ in specs:
        if col in df_view.columns and f"{col}_pct" in df_view.columns:
            pct_map[col] = f"{col}_pct"

    df_render = df_view.drop(columns=["player_id"])
    styler = style_dataframe_by_percentiles(df_render, pct_map)
    st.dataframe(
        styler,
        column_config=col_config,
        hide_index=True,
        width="stretch",
        height=620,
    )
    # Selectbox drilldown
    st.markdown("**Drill into a player**")
    player_options = ["—"] + [
        f"{row['player']} · {row['team']}"
        for _, row in df_view.iterrows()
    ]
    chosen = st.selectbox("Pick a player", player_options, label_visibility="collapsed",
                            key="ps_drill_select")
    sel_player_id = None
    if chosen != "—":
        sel_player_name = chosen.split(" · ")[0]
        match = df_view[df_view["player"] == sel_player_name]
        if not match.empty:
            sel_player_id = int(match.iloc[0]["player_id"])
            sel_player_name_actual = match.iloc[0]["player"]
else:
    event = st.dataframe(
        df_view,
        column_config=col_config,
        hide_index=True,
        width="stretch",
        height=620,
        on_select="rerun",
        selection_mode="single-row",
    )
    sel_rows = event.selection.rows if hasattr(event, "selection") else []
    sel_player_id = None
    sel_player_name_actual = None
    if sel_rows:
        row_idx = sel_rows[0]
        row = df_view.iloc[row_idx]
        sel_player_id = int(row["player_id"])
        sel_player_name_actual = row["player"]

# =========================================================================
# DRILLDOWN
# =========================================================================
if sel_player_id is not None:
    player_id = sel_player_id
    player_name = sel_player_name_actual

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
        for c in ("fg_pct", "fg3_pct", "ft_pct", "efg_pct", "ts_pct"):
            if c in games.columns:
                games[c] = games[c] * 100

        drill_config = {
            "game_date": st.column_config.TextColumn("Date"),
            "site": st.column_config.TextColumn("H/A"),
            "opp": st.column_config.TextColumn("OPP"),
            "minutes": st.column_config.NumberColumn("MIN", format="%.1f"),
            "pts": st.column_config.NumberColumn("PTS", format="%.0f"),
            "reb": st.column_config.NumberColumn("REB", format="%.0f"),
            "ast": st.column_config.NumberColumn("AST", format="%.0f"),
            "stl": st.column_config.NumberColumn("STL", format="%.0f"),
            "blk": st.column_config.NumberColumn("BLK", format="%.0f"),
            "tov": st.column_config.NumberColumn("TOV", format="%.0f"),
            "fg_pct": st.column_config.NumberColumn("FG%", format="%.1f"),
            "fg3_pct": st.column_config.NumberColumn("3P%", format="%.1f"),
            "ft_pct": st.column_config.NumberColumn("FT%", format="%.1f"),
            "usg_pct": st.column_config.NumberColumn("USG%", format="%.1f"),
            "efg_pct": st.column_config.NumberColumn("eFG%", format="%.1f"),
            "ts_pct": st.column_config.NumberColumn("TS%", format="%.1f"),
            "pie": st.column_config.NumberColumn("PIE", format="%.2f"),
            "off_rating": st.column_config.NumberColumn("ORtg", format="%.1f"),
            "def_rating": st.column_config.NumberColumn("DRtg", format="%.1f"),
        }
        st.dataframe(games, column_config=drill_config, hide_index=True, width="stretch")
