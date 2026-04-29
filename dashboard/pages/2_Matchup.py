"""Matchup deep dive — the podcast-prep page."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.data import (
    db_mtime,
    games_in_window,
    head_to_head,
    last_starting_lineup,
    team_aggregate,
    team_lookup,
    team_opponent_aggregate,
    team_recent_games,
    team_record,
)
from lib.filters import window_picker
from lib.format import (
    fmt_int,
    fmt_num,
    fmt_pct,
    hkt_to_et_date,
    hkt_today,
    matchup_label,
    status_badge,
)

st.set_page_config(page_title="Matchup", page_icon="🥊", layout="wide")
st.title("🥊 Matchup")

mtime = db_mtime()
tlookup = team_lookup(_mtime=mtime)

# --- Game selector -------------------------------------------------------
sel = st.columns([2, 1, 1])
with sel[0]:
    today_hkt = hkt_today()
    pick_date = st.date_input("Browse games near (HKT)",
                               value=date.fromisoformat(today_hkt))
with sel[1]:
    days_back = st.number_input("Days back", 0, 14, value=2, step=1)
with sel[2]:
    days_forward = st.number_input("Days ahead", 0, 14, value=2, step=1)

start = (pick_date - timedelta(days=int(days_back))).isoformat()
end = (pick_date + timedelta(days=int(days_forward))).isoformat()
games = games_in_window(hkt_to_et_date(start), hkt_to_et_date(end), _mtime=mtime)

if games.empty:
    st.warning("No games found in this window. Widen the days, or pick a different date.")
    st.stop()

# Build a label per game for the dropdown
def _label(row) -> str:
    score = ""
    if row["status"] == "Final":
        score = f" — {int(row['away_score'])}-{int(row['home_score'])}"
    return f"{row['game_date']}  {matchup_label(row['home_abbr'], row['away_abbr'])}  ({row['season_type']}){score}"

games = games.assign(label=games.apply(_label, axis=1))
default_idx = len(games) - 1  # most recent first
chosen_label = st.selectbox("Pick a game", games["label"].tolist(), index=default_idx)
g = games[games["label"] == chosen_label].iloc[0]

window = window_picker(default="L10")

home_id, away_id = int(g["home_team_id"]), int(g["away_team_id"])
home, away = tlookup[home_id], tlookup[away_id]

# =========================================================================
# Section A — Header
# =========================================================================
hdr = st.container(border=True)
with hdr:
    cols = st.columns([2, 1, 2])
    with cols[0]:
        st.markdown(f"### {away['full_name']}")
        wA, lA = team_record(away_id, "Season", _mtime=mtime)
        wA_w, lA_w = team_record(away_id, window, _mtime=mtime)
        st.markdown(f"Season `{wA}-{lA}`  ·  {window} `{wA_w}-{lA_w}`")
    with cols[1]:
        st.markdown(f"<h2 style='text-align:center;margin-top:1rem'>@</h2>",
                     unsafe_allow_html=True)
        st.caption(f"{g['game_date']} · {g['season_type']}")
        st.caption(status_badge(g["status"]))
        if g["status"] == "Final":
            st.markdown(
                f"<h3 style='text-align:center'>{int(g['away_score'])} – {int(g['home_score'])}</h3>",
                unsafe_allow_html=True,
            )
    with cols[2]:
        st.markdown(f"### {home['full_name']}")
        wH, lH = team_record(home_id, "Season", _mtime=mtime)
        wH_w, lH_w = team_record(home_id, window, _mtime=mtime)
        st.markdown(f"Season `{wH}-{lH}`  ·  {window} `{wH_w}-{lH_w}`")

# H2H
h2h = head_to_head(away_id, home_id, _mtime=mtime)
if not h2h.empty:
    st.markdown("**Head-to-head this season**")
    home_wins = sum(1 for _, r in h2h.iterrows()
                     if r["home_score"] is not None and r["away_score"] is not None
                     and ((r["home_team_id"] == home_id and r["home_score"] > r["away_score"])
                          or (r["away_team_id"] == home_id and r["away_score"] > r["home_score"])))
    away_wins = len(h2h) - home_wins
    st.caption(f"{away['abbreviation']} {away_wins} – {home_wins} {home['abbreviation']}  "
                f"({len(h2h)} games)")
    h2h_disp = h2h.assign(
        score=lambda d: d.apply(lambda r: f"{int(r['away_score'])}-{int(r['home_score'])}"
                                  if pd.notna(r['away_score']) else "—", axis=1)
    )[["game_date", "away_abbr", "home_abbr", "score", "season_type"]]
    h2h_disp.columns = ["Date", "Away", "Home", "Score", "Type"]
    st.dataframe(h2h_disp, hide_index=True, width="stretch")

st.divider()

# =========================================================================
# Section B — Form snapshot
# =========================================================================
st.subheader(f"📊 Form snapshot — {window}")

def _form_block(team_id: int, team_name: str):
    agg = team_aggregate(team_id, window, _mtime=mtime)
    opp = team_opponent_aggregate(team_id, window, _mtime=mtime)
    st.markdown(f"#### {team_name}")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("ORtg", fmt_num(agg.get("off_rating")))
    g2.metric("DRtg", fmt_num(agg.get("def_rating")))
    g3.metric("NetRtg", fmt_num(agg.get("net_rating")))
    g4.metric("Pace", fmt_num(agg.get("pace")))
    g5, g6, g7, g8 = st.columns(4)
    g5.metric("eFG%", fmt_pct(agg.get("efg_pct")))
    g6.metric("TS%",  fmt_pct(agg.get("ts_pct")))
    g7.metric("TOV%", fmt_num(agg.get("tov_pct")))
    g8.metric("OPP eFG%", fmt_pct(opp.get("opp_efg_pct")))

bcols = st.columns(2)
with bcols[0]: _form_block(away_id, away["full_name"])
with bcols[1]: _form_block(home_id, home["full_name"])

st.divider()

# =========================================================================
# Section C — Trend charts
# =========================================================================
st.subheader("📈 Last 20 games — trends")

def _trend(team_id: int, team_name: str, color: str):
    df = team_recent_games(team_id, last_n=20, _mtime=mtime).sort_values("game_date")
    if df.empty:
        st.caption(f"No data for {team_name}")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["game_date"], y=df["off_rating"], name="ORtg",
                              line=dict(color=color, width=2), mode="lines+markers"))
    fig.add_trace(go.Scatter(x=df["game_date"], y=df["def_rating"], name="DRtg",
                              line=dict(color=color, width=2, dash="dash"),
                              mode="lines+markers"))
    fig.update_layout(
        title=team_name, height=300, margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", y=1.1), xaxis_title=None, yaxis_title="Rating",
    )
    st.plotly_chart(fig, width="stretch")

ccols = st.columns(2)
with ccols[0]: _trend(away_id, away["full_name"], "#1f77b4")
with ccols[1]: _trend(home_id, home["full_name"], "#d62728")

st.divider()

# =========================================================================
# Section D — Strength matchup grid
# =========================================================================
st.subheader("⚔️ Edge finder")
st.caption(
    f"Each team's offence vs the other team's defence ({window} averages). "
    "Bigger gaps = bigger edges."
)

a_off = team_aggregate(away_id, window, _mtime=mtime)
a_def = team_opponent_aggregate(away_id, window, _mtime=mtime)
h_off = team_aggregate(home_id, window, _mtime=mtime)
h_def = team_opponent_aggregate(home_id, window, _mtime=mtime)

edge_data = [
    ("ORtg vs DRtg", a_off.get("off_rating"), h_off.get("def_rating"),
     h_off.get("off_rating"), a_off.get("def_rating")),
    ("eFG% vs OPP eFG%", a_off.get("efg_pct"), h_def.get("opp_efg_pct"),
     h_off.get("efg_pct"), a_def.get("opp_efg_pct")),
    ("TS% vs OPP TS%", a_off.get("ts_pct"), h_def.get("opp_ts_pct"),
     h_off.get("ts_pct"), a_def.get("opp_ts_pct")),
    ("Pace", a_off.get("pace"), None, h_off.get("pace"), None),
]

def _fmt_pair(metric: str, val):
    if "%" in metric:
        return fmt_pct(val)
    return fmt_num(val)

edge_rows = []
for metric, ao, hd, ho, ad in edge_data:
    edge_rows.append({
        "Metric": metric,
        f"{away['abbreviation']} OFF": _fmt_pair(metric, ao),
        f"{home['abbreviation']} DEF allowed": _fmt_pair(metric, hd) if hd is not None else "—",
        f"{home['abbreviation']} OFF": _fmt_pair(metric, ho),
        f"{away['abbreviation']} DEF allowed": _fmt_pair(metric, ad) if ad is not None else "—",
    })
st.dataframe(pd.DataFrame(edge_rows), hide_index=True, width="stretch")

st.divider()

# =========================================================================
# Section E — Player availability
# =========================================================================
st.subheader("👥 Likely starters (last game)")

def _starters_block(team_id: int, team_name: str):
    df = last_starting_lineup(team_id, _mtime=mtime)
    st.markdown(f"#### {team_name}")
    if df.empty:
        st.caption("No recent starters found.")
        return
    df = df.copy()
    df["minutes"] = df["minutes"].apply(fmt_num)
    df = df.rename(columns={"player": "Player", "minutes": "MIN",
                              "pts": "PTS", "reb": "REB", "ast": "AST"})
    st.dataframe(df, hide_index=True, width="stretch")

scols = st.columns(2)
with scols[0]: _starters_block(away_id, away["full_name"])
with scols[1]: _starters_block(home_id, home["full_name"])

st.caption("Note: starters shown are from the team's most recent completed game — "
           "actual starters tonight may vary based on injuries / coach decisions.")
