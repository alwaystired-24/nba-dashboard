"""Team Stats — 4-layer split with rank toggle and clickable drilldown."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st


from lib.data import db_mtime, league_team_table, team_lookup, team_recent_games
from lib.freshness import show_freshness_banner
from lib.filters import layer_picker, window_picker, season_filter_picker, SEASON_FILTER_LABELS
from lib.format import fmt_num, fmt_pct
from lib.stats import team_layer_columns

st.set_page_config(page_title="Team Stats", page_icon="🏟️", layout="wide")

from lib.theme import inject_theme
inject_theme(active_page="teamstats")
st.title("🏟️ Team Stats")

mtime = db_mtime()
show_freshness_banner(mtime)
tlookup = team_lookup(_mtime=mtime)

LOWER_IS_BETTER = {
    "def_rating", "tov_pct", "tov", "pf",
    "opp_pts", "opp_fg_pct", "opp_fg3_pct", "opp_fg3a", "opp_fga",
    "opp_efg_pct", "opp_ts_pct", "opp_tov_pct", "opp_ast", "opp_reb", "opp_oreb",
    "l",
}

# =========================================================================
# TOP CONTROLS
# =========================================================================
c1, c2, c3 = st.columns([1, 1, 1])
with c1: window = window_picker(default="Season")
with c2: layer = layer_picker(default="Traditional")
with c3:
    show_ranks = st.toggle("Show rank (1 = best)", value=False,
                            help="Adds a rank column for each metric. 1 = league best, 30 = worst.")

season_filter = season_filter_picker()
st.caption(f"Showing **{SEASON_FILTER_LABELS[season_filter]}** stats. "
            "Change at top of any page.")

# =========================================================================
# SIDEBAR FILTERS
# =========================================================================
abbrs = sorted({tlookup[t]["abbreviation"] for t in tlookup})
conferences = sorted({tlookup[t]["conference"] for t in tlookup if tlookup[t].get("conference")})
divisions = sorted({tlookup[t]["division"] for t in tlookup if tlookup[t].get("division")})

# Top-right floating filters popover (replaces sidebar)
filter_cols = st.columns([5, 1])
with filter_cols[1]:
    n_active = 0  # placeholder, computed inside popover
    with st.popover("☰ Filters", width="stretch"):
        st.markdown("### 🎛️ Filters")
        teams_sel = st.multiselect("Team(s)", abbrs, default=[], key="ts_teams")
        conf_sel = st.multiselect("Conference", conferences, default=[], key="ts_conf") if conferences else []
        div_sel = st.multiselect("Division", divisions, default=[], key="ts_div") if divisions else []

        active = []
        if teams_sel: active.append(f"{len(teams_sel)} team(s)")
        if conf_sel: active.append(f"{len(conf_sel)} conf")
        if div_sel: active.append(f"{len(div_sel)} div")
        if active:
            st.markdown(f"**Active:** {', '.join(active)}")
        else:
            st.caption("No filters active (all 30 teams)")

# Show active-filter chip at top so user knows filters are applied
n_active_filters = len([x for x in [teams_sel, conf_sel, div_sel] if x])
if n_active_filters:
    parts = []
    if teams_sel: parts.append(f"{len(teams_sel)} team(s)")
    if conf_sel: parts.append(f"{len(conf_sel)} conf")
    if div_sel: parts.append(f"{len(div_sel)} div")
    st.markdown(
        f'<div style="background:rgba(244,167,66,0.15);color:#F4A742;'
        f'padding:6px 12px;border-radius:6px;font-size:12px;display:inline-block;'
        f'margin-bottom:8px;">🎛️ Active filters: {", ".join(parts)}</div>',
        unsafe_allow_html=True,
    )

# =========================================================================
# DATA — ranks always vs full league
# =========================================================================
df_full = league_team_table(window, season_filter, _mtime=mtime).reset_index(drop=True)

specs = team_layer_columns(layer)
rank_data = {}
for col, _, _ in specs:
    if col not in df_full.columns or col in ("gp", "w"):
        continue
    if col in LOWER_IS_BETTER:
        rank_data[col] = df_full[col].rank(ascending=True, method="min").astype("Int64")
    else:
        rank_data[col] = df_full[col].rank(ascending=False, method="min").astype("Int64")

# Apply filters AFTER rank computation
df = df_full.copy()
df["conference"] = df["team_id"].map(lambda t: tlookup.get(int(t), {}).get("conference"))
df["division"] = df["team_id"].map(lambda t: tlookup.get(int(t), {}).get("division"))

# Hide 0-GP teams when Playoffs filter is on (eliminated/non-qualifying teams)
if season_filter == "playoffs":
    df = df[df["gp"] > 0]

if teams_sel:
    df = df[df["abbr"].isin(teams_sel)]
if conf_sel:
    df = df[df["conference"].isin(conf_sel)]
if div_sel:
    df = df[df["division"].isin(div_sel)]

if df.empty:
    st.warning("No teams match these filters.")
    st.stop()

# Attach ranks
for col, ranks in rank_data.items():
    df[f"{col}_rank"] = ranks.reindex(df.index)

# =========================================================================
# BUILD DISPLAY
# =========================================================================
base_cols = ["abbr", "team"]
stat_cols = [c for c, _, _ in specs if c in df.columns]
df_view = df[base_cols + stat_cols + ["team_id"]].copy().reset_index(drop=True)

if show_ranks:
    for col, _, _ in specs:
        rank_col = f"{col}_rank"
        if rank_col in df.columns:
            df_view[rank_col] = df.reset_index(drop=True)[rank_col]

# League average row
lg_row = {"abbr": "—", "team": "League avg", "team_id": -1}
for col, _, _ in specs:
    if col in df_full.columns:
        lg_row[col] = df_full[col].mean()
    else:
        lg_row[col] = None
if show_ranks:
    for col, _, _ in specs:
        rank_col = f"{col}_rank"
        if rank_col in df_view.columns:
            lg_row[rank_col] = None

df_view = pd.concat([df_view, pd.DataFrame([lg_row])], ignore_index=True)

# Convert ratios to display percentages
for col, _, fn in specs:
    if col in df_view.columns and fn is fmt_pct:
        df_view[col] = df_view[col] * 100

# Order columns: identity → for each stat: value, then rank
ordered = ["abbr", "team"]
for col, _, _ in specs:
    if col in df_view.columns:
        ordered.append(col)
        if show_ranks and f"{col}_rank" in df_view.columns:
            ordered.append(f"{col}_rank")
df_view = df_view[ordered + ["team_id"]]

# Build column_config
col_config = {
    "abbr": st.column_config.TextColumn("Tm"),
    "team": st.column_config.TextColumn("Team"),
    "team_id": None,
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
    rank_col = f"{col}_rank"
    if show_ranks and rank_col in df_view.columns:
        col_config[rank_col] = st.column_config.NumberColumn(
            f"{label}#", format="%d",
            help=f"{label} league rank (1 = best, 30 = worst)",
        )

st.subheader(f"{layer} stats — {window}")
st.caption(f"{len(df_view) - 1} teams + league avg row · ranks always vs full 30 teams.  "
            "Click any column header to sort. Pick a team below to drill in.")

# Render the table — colored if rank columns exist, plain otherwise
if show_ranks:
    # Build {value_col: rank_col} mapping for color helper
    from lib.coloring import style_dataframe_by_ranks
    rank_map = {}
    for col, _, _ in specs:
        if col in df_view.columns and f"{col}_rank" in df_view.columns:
            rank_map[col] = f"{col}_rank"

    # Drop team_id from display, but keep it for drilldown lookup
    df_render = df_view.drop(columns=["team_id"])
    styler = style_dataframe_by_ranks(df_render, rank_map, n_total=30)
    st.dataframe(
        styler,
        column_config=col_config,
        hide_index=True,
        width="stretch",
        height=620,
    )
    # Selectbox-based drilldown (Styler is incompatible with on_select)
    st.markdown("**Drill into a team**")
    team_options = ["—"] + [
        f"{row['abbr']} · {row['team']}"
        for _, row in df_view.iterrows()
        if int(row["team_id"]) != -1
    ]
    chosen = st.selectbox("Pick a team", team_options, label_visibility="collapsed",
                            key="ts_drill_select")
    sel_team_id = None
    if chosen != "—":
        sel_abbr = chosen.split(" · ")[0]
        match = df_view[df_view["abbr"] == sel_abbr]
        if not match.empty:
            sel_team_id = int(match.iloc[0]["team_id"])
else:
    # Plain table with row-click drilldown
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
    sel_team_id = None
    if sel_rows:
        row_idx = sel_rows[0]
        row = df_view.iloc[row_idx]
        if int(row["team_id"]) != -1:
            sel_team_id = int(row["team_id"])

# =========================================================================
# DRILLDOWN
# =========================================================================
if sel_team_id is not None:
    team_id = sel_team_id
    team_row = df_view[df_view["team_id"] == team_id].iloc[0]
    team_name = team_row["team"]

    st.divider()
    st.subheader(f"📋 {team_name} — last 20 games")

    games = team_recent_games(team_id, last_n=20, season_filter=season_filter, _mtime=mtime)
    if games.empty:
        st.caption("No games found.")
    else:
        games = games.copy()
        games["opp"] = games["opp_id"].map(
            lambda x: tlookup.get(int(x), {}).get("abbreviation", "—")
        )
        games["score"] = games.apply(
            lambda r: f"{int(r['pts'])}-{int(r['opp_pts'])}" if pd.notna(r["pts"]) else "—",
            axis=1,
        )
        for c in ("fg_pct", "fg3_pct", "efg_pct", "ts_pct"):
            if c in games.columns:
                games[c] = games[c] * 100

        drill_view = games[["game_date", "site", "opp", "score",
                             "off_rating", "def_rating", "net_rating", "pace",
                             "efg_pct", "ts_pct", "fg_pct", "fg3_pct"]]
        drill_config = {
            "game_date": st.column_config.TextColumn("Date"),
            "site": st.column_config.TextColumn("H/A"),
            "opp": st.column_config.TextColumn("OPP"),
            "score": st.column_config.TextColumn("Score"),
            "off_rating": st.column_config.NumberColumn("ORtg", format="%.1f"),
            "def_rating": st.column_config.NumberColumn("DRtg", format="%.1f"),
            "net_rating": st.column_config.NumberColumn("Net", format="%.1f"),
            "pace": st.column_config.NumberColumn("Pace", format="%.1f"),
            "efg_pct": st.column_config.NumberColumn("eFG%", format="%.1f"),
            "ts_pct": st.column_config.NumberColumn("TS%", format="%.1f"),
            "fg_pct": st.column_config.NumberColumn("FG%", format="%.1f"),
            "fg3_pct": st.column_config.NumberColumn("3P%", format="%.1f"),
        }
        st.dataframe(drill_view, column_config=drill_config, hide_index=True, width="stretch")
