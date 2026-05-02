"""Matchup deep dive — the cockpit for podcast prep + odds compilation.

Layout optimized for daily repeat use. Most-needed info above the fold,
no hunting for stats.
"""
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
    league_team_table,
    team_aggregate,
    team_lookup,
    team_opponent_aggregate,
    team_recent_games,
    team_record,
)
from lib.freshness import show_freshness_banner
from lib.filters import window_picker
from lib.format import (
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
show_freshness_banner(mtime)
tlookup = team_lookup(_mtime=mtime)

# =========================================================================
# Game selector — two-dropdown design: pick HKT date, then pick game
# =========================================================================
today_hkt = hkt_today()
today_et = hkt_to_et_date(today_hkt)

# Pull a wide window — past 14 days through next 14 days
wide_start = (date.fromisoformat(today_hkt) - timedelta(days=14)).isoformat()
wide_end = (date.fromisoformat(today_hkt) + timedelta(days=14)).isoformat()
all_games = games_in_window(
    hkt_to_et_date(wide_start), hkt_to_et_date(wide_end), _mtime=mtime,
)

if all_games.empty:
    st.warning("No games found in the surrounding 4-week window. "
                "Run `python -m scripts.run schedule` to refresh.")
    st.stop()

# Each ET game date maps to an HKT date by adding 1 day
# (NBA games tip in evening ET = morning/afternoon next day HKT)
def _et_to_hkt_date(et_date: str) -> str:
    return (date.fromisoformat(et_date) + timedelta(days=1)).isoformat()

all_games = all_games.assign(
    hkt_date=all_games["game_date"].apply(_et_to_hkt_date),
)

# --- Date dropdown — only dates that have games -----------------------
hkt_dates_with_games = sorted(all_games["hkt_date"].unique())

# Default: today HKT if it has games, else the next future date with games,
# else the most recent past date with games
def _pick_default_date(dates: list[str]) -> str:
    if today_hkt in dates:
        return today_hkt
    future = [d for d in dates if d > today_hkt]
    if future:
        return future[0]
    return dates[-1]

default_date = _pick_default_date(hkt_dates_with_games)

# Friendly label: "Today (Sat 02 May)" / "Tomorrow (Sun 03 May)" / "Sat 02 May"
def _date_label(d: str) -> str:
    dt = date.fromisoformat(d)
    delta = (dt - date.fromisoformat(today_hkt)).days
    pretty = dt.strftime("%a %d %b")
    if delta == 0:  return f"Today  ·  {pretty}"
    if delta == 1:  return f"Tomorrow  ·  {pretty}"
    if delta == -1: return f"Yesterday  ·  {pretty}"
    return pretty

date_labels = [_date_label(d) for d in hkt_dates_with_games]
default_idx = hkt_dates_with_games.index(default_date)

dcol, gcol = st.columns([1, 2])
with dcol:
    chosen_date_label = st.selectbox("Date (HKT)", date_labels, index=default_idx)
chosen_hkt_date = hkt_dates_with_games[date_labels.index(chosen_date_label)]

# --- Game dropdown — only games on the chosen date --------------------
day_games = all_games[all_games["hkt_date"] == chosen_hkt_date].copy()

def _game_label(row) -> str:
    score = ""
    if row["status"] == "Final" and pd.notna(row["away_score"]):
        score = f" — {int(row['away_score'])}-{int(row['home_score'])}"
    elif row["status"] == "Scheduled":
        score = " — Scheduled"
    elif row["status"] == "Live":
        score = " — 🔴 LIVE"
    return f"{matchup_label(row['home_abbr'], row['away_abbr'])}  ({row['season_type']}){score}"

day_games = day_games.assign(label=day_games.apply(_game_label, axis=1))

with gcol:
    chosen_game_label = st.selectbox("Game", day_games["label"].tolist(), index=0)

g = day_games[day_games["label"] == chosen_game_label].iloc[0]

window = window_picker(default="L10")

home_id, away_id = int(g["home_team_id"]), int(g["away_team_id"])
home, away = tlookup[home_id], tlookup[away_id]
is_upcoming = g["status"] != "Final"


# =========================================================================
# Compact header strip
# =========================================================================
hdr = st.container(border=True)
with hdr:
    cols = st.columns([3, 2, 3])
    with cols[0]:
        wA, lA = team_record(away_id, "Season", _mtime=mtime)
        wA_w, lA_w = team_record(away_id, window, _mtime=mtime)
        st.markdown(f"### ✈️ {away['full_name']}")
        st.markdown(f"Season `{wA}-{lA}`  ·  {window} `{wA_w}-{lA_w}`")
    with cols[1]:
        st.markdown(f"<div style='text-align:center'>"
                     f"<h4>{g['game_date']} · {g['season_type']}</h4>"
                     f"<p>{status_badge(g['status'])}</p>"
                     "</div>", unsafe_allow_html=True)
        if g["status"] == "Final" and pd.notna(g["away_score"]):
            st.markdown(
                f"<h2 style='text-align:center;margin:0'>"
                f"{int(g['away_score'])} – {int(g['home_score'])}</h2>",
                unsafe_allow_html=True,
            )
    with cols[2]:
        wH, lH = team_record(home_id, "Season", _mtime=mtime)
        wH_w, lH_w = team_record(home_id, window, _mtime=mtime)
        st.markdown(f"### 🏠 {home['full_name']}")
        st.markdown(f"Season `{wH}-{lH}`  ·  {window} `{wH_w}-{lH_w}`")

# =========================================================================
# League average baseline (used in Edge Finder and key metrics)
# =========================================================================
@st.cache_data(show_spinner=False)
def _league_means(window: str, _mtime: float):
    df = league_team_table(window, _mtime=_mtime)
    return df.mean(numeric_only=True).to_dict()

lg = _league_means(window, _mtime=mtime)

st.divider()

# =========================================================================
# Form snapshot — both teams side-by-side with league avg comparison
# =========================================================================
st.subheader(f"📊 Form snapshot — {window}")
st.caption("Δ = team value vs league average. Green = better than league, red = worse.")

def _delta_color(team_val, league_val, lower_is_better=False) -> str:
    if team_val is None or league_val is None or pd.isna(team_val) or pd.isna(league_val):
        return "off"
    diff = team_val - league_val
    if lower_is_better:
        diff = -diff
    return "normal" if abs(diff) > 0.01 else "off"

def _delta_str(team_val, league_val, fmt=lambda x: f"{x:+.1f}"):
    if team_val is None or league_val is None or pd.isna(team_val) or pd.isna(league_val):
        return None
    return fmt(team_val - league_val)

def _form_block(team_id: int, team_name: str):
    agg = team_aggregate(team_id, window, _mtime=mtime)
    opp = team_opponent_aggregate(team_id, window, _mtime=mtime)
    st.markdown(f"#### {team_name}")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("ORtg", fmt_num(agg.get("off_rating")),
               _delta_str(agg.get("off_rating"), lg.get("off_rating")))
    g2.metric("DRtg", fmt_num(agg.get("def_rating")),
               _delta_str(agg.get("def_rating"), lg.get("def_rating")),
               delta_color="inverse")
    g3.metric("NetRtg", fmt_num(agg.get("net_rating")),
               _delta_str(agg.get("net_rating"), lg.get("net_rating")))
    g4.metric("Pace", fmt_num(agg.get("pace")),
               _delta_str(agg.get("pace"), lg.get("pace")))
    g5, g6, g7, g8 = st.columns(4)
    g5.metric("eFG%", fmt_pct(agg.get("efg_pct")),
               _delta_str(agg.get("efg_pct"), lg.get("efg_pct"),
                           fmt=lambda x: f"{x*100:+.1f}pp"))
    g6.metric("TS%", fmt_pct(agg.get("ts_pct")),
               _delta_str(agg.get("ts_pct"), lg.get("ts_pct"),
                           fmt=lambda x: f"{x*100:+.1f}pp"))
    g7.metric("OPP eFG%", fmt_pct(opp.get("opp_efg_pct")),
               _delta_str(opp.get("opp_efg_pct"), lg.get("opp_efg_pct"),
                           fmt=lambda x: f"{x*100:+.1f}pp"),
               delta_color="inverse")
    g8.metric("OPP 3P%", fmt_pct(opp.get("opp_fg3_pct")),
               _delta_str(opp.get("opp_fg3_pct"), lg.get("opp_fg3_pct"),
                           fmt=lambda x: f"{x*100:+.1f}pp"),
               delta_color="inverse")

bcols = st.columns(2)
with bcols[0]: _form_block(away_id, away["full_name"])
with bcols[1]: _form_block(home_id, home["full_name"])

st.divider()

# =========================================================================
# Trend charts — both teams' L20
# =========================================================================
st.subheader("📈 Last 20 games — trend")

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
# Edge Finder — expanded with league avg
# =========================================================================
st.subheader("⚔️ Edge Finder")
st.caption(
    f"Each team's offence vs the other team's defence ({window} averages). "
    "League average shown for context. Bigger gaps = bigger edges."
)

a_off = team_aggregate(away_id, window, _mtime=mtime)
a_def = team_opponent_aggregate(away_id, window, _mtime=mtime)
h_off = team_aggregate(home_id, window, _mtime=mtime)
h_def = team_opponent_aggregate(home_id, window, _mtime=mtime)

# (label, away_offense_value, home_defense_allowed, home_offense_value, away_defense_allowed, league_avg, format_fn)
def _pct(x): return fmt_pct(x)
def _num(x): return fmt_num(x)

edge_rows = [
    ("ORtg vs DRtg", a_off.get("off_rating"), h_off.get("def_rating"),
     h_off.get("off_rating"), a_off.get("def_rating"), lg.get("off_rating"), _num),
    ("eFG% vs OPP eFG%", a_off.get("efg_pct"), h_def.get("opp_efg_pct"),
     h_off.get("efg_pct"), a_def.get("opp_efg_pct"), lg.get("efg_pct"), _pct),
    ("TS% vs OPP TS%", a_off.get("ts_pct"), h_def.get("opp_ts_pct"),
     h_off.get("ts_pct"), a_def.get("opp_ts_pct"), lg.get("ts_pct"), _pct),
    ("3P% vs OPP 3P%", a_off.get("fg3_pct"), h_def.get("opp_fg3_pct"),
     h_off.get("fg3_pct"), a_def.get("opp_fg3_pct"), lg.get("fg3_pct"), _pct),
    ("OREB vs OPP OREB", a_off.get("oreb"), h_def.get("opp_oreb"),
     h_off.get("oreb"), a_def.get("opp_oreb"), lg.get("oreb"), _num),
    ("Fouls drawn", a_off.get("pf"), None,  # FT-related; we proxy with personal fouls per team
     h_off.get("pf"), None, lg.get("pf"), _num),
    ("Pace", a_off.get("pace"), None,
     h_off.get("pace"), None, lg.get("pace"), _num),
]

table_rows = []
for metric, ao, hd, ho, ad, lavg, fmtfn in edge_rows:
    table_rows.append({
        "Metric": metric,
        f"{away['abbreviation']} OFF": fmtfn(ao),
        f"{home['abbreviation']} D allowed": fmtfn(hd) if hd is not None else "—",
        f"{home['abbreviation']} OFF": fmtfn(ho),
        f"{away['abbreviation']} D allowed": fmtfn(ad) if ad is not None else "—",
        "League avg": fmtfn(lavg) if lavg is not None else "—",
    })
st.dataframe(pd.DataFrame(table_rows), hide_index=True, width="stretch")

st.divider()

# =========================================================================
# Likely starters
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

st.caption("Starters shown are from the team's most recent completed game — "
           "actual starters tonight may vary based on injuries / coach decisions.")

# =========================================================================
# H2H — collapsed by default
# =========================================================================
st.divider()
with st.expander(f"📋 Head-to-head this season — {away['abbreviation']} vs {home['abbreviation']}", expanded=False):
    h2h = head_to_head(away_id, home_id, _mtime=mtime)
    if h2h.empty:
        st.caption("No prior meetings this season.")
    else:
        home_wins = sum(1 for _, r in h2h.iterrows()
                         if r["home_score"] is not None and r["away_score"] is not None
                         and ((r["home_team_id"] == home_id and r["home_score"] > r["away_score"])
                              or (r["away_team_id"] == home_id and r["away_score"] > r["home_score"])))
        away_wins = len(h2h) - home_wins
        st.caption(f"{away['abbreviation']} {away_wins} – {home_wins} {home['abbreviation']}  ({len(h2h)} games)")
        h2h_disp = h2h.assign(
            score=lambda d: d.apply(lambda r: f"{int(r['away_score'])}-{int(r['home_score'])}"
                                      if pd.notna(r['away_score']) else "—", axis=1)
        )[["game_date", "away_abbr", "home_abbr", "score", "season_type"]]
        h2h_disp.columns = ["Date", "Away", "Home", "Score", "Type"]
        st.dataframe(h2h_disp, hide_index=True, width="stretch")


# =========================================================================
# ODDS — Phase 6 — three tables, raw decimal prices, opener/pre_game/late
# =========================================================================
from lib.odds_data import odds_for_game

st.divider()
st.subheader("💰 Odds")

odds_df = odds_for_game(g["game_id"], _mtime=mtime)

if odds_df.empty:
    st.info(
        "No odds data captured for this game yet. "
        "Odds are fetched 3× daily by the GitHub Actions workflow "
        "(opener / pre_game / late). Check back closer to tip-off."
    )
else:
    # Detect missing phases (until system has been running 3 full days)
    PHASES = ["opener", "pre_game", "late"]
    captured_phases = set(odds_df["snapshot_phase"].dropna().unique())
    missing = [p for p in PHASES if p not in captured_phases]
    if missing:
        st.warning(
            f"⚠️ Partial data — only captured: **{', '.join(sorted(captured_phases)) or 'none'}**. "
            f"Missing: **{', '.join(missing)}**. "
            "This is normal until the system has run 3+ days. "
            "Empty cells (—) below indicate phases not yet collected.",
            icon="⏳",
        )

    # Helper: pivot odds_df to {(book, phase): row} for fast lookup per market
    def _phase_lookup(df_market: pd.DataFrame) -> dict:
        """For one market's df, return {(book, phase): latest_row_in_that_phase}."""
        out = {}
        # If multiple snapshots exist for same (book, phase), take the most recent
        df_market = df_market.sort_values("fetched_utc")
        for (book, phase), grp in df_market.groupby(["bookmaker", "snapshot_phase"]):
            out[(book, phase)] = grp.iloc[-1]
        return out

    def _fmt(x, pat="{:.2f}"):
        if x is None or pd.isna(x):
            return "—"
        return pat.format(x)

    def _fmt_pt(x):
        if x is None or pd.isna(x):
            return "—"
        return f"{x:+g}" if x else "0"

    # ---------------------------------------------------------------
    # Moneyline table
    # ---------------------------------------------------------------
    st.markdown("#### Moneyline")
    h2h_df = odds_df[odds_df["market"] == "h2h"]
    if h2h_df.empty:
        st.caption("No moneyline data captured.")
    else:
        lookup = _phase_lookup(h2h_df)
        books = sorted(h2h_df["bookmaker"].unique())
        rows = []
        for book in books:
            row = {"Book": book.upper()}
            for phase in PHASES:
                r = lookup.get((book, phase))
                if r is None:
                    row[f"{phase} · {away['abbreviation']}"] = "—"
                    row[f"{phase} · {home['abbreviation']}"] = "—"
                else:
                    row[f"{phase} · {away['abbreviation']}"] = _fmt(r["away_price"])
                    row[f"{phase} · {home['abbreviation']}"] = _fmt(r["home_price"])
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    # ---------------------------------------------------------------
    # Spread table
    # ---------------------------------------------------------------
    st.markdown("#### Spread")
    sp_df = odds_df[odds_df["market"] == "spreads"]
    if sp_df.empty:
        st.caption("No spread data captured.")
    else:
        lookup = _phase_lookup(sp_df)
        books = sorted(sp_df["bookmaker"].unique())
        rows = []
        for book in books:
            row = {"Book": book.upper()}
            for phase in PHASES:
                r = lookup.get((book, phase))
                if r is None:
                    row[f"{phase} · line"] = "—"
                    row[f"{phase} · {away['abbreviation']} px"] = "—"
                    row[f"{phase} · {home['abbreviation']} px"] = "—"
                else:
                    # Show line as home perspective (e.g., LAL -4.5)
                    spread_h = r["spread_home"]
                    if pd.notna(spread_h):
                        row[f"{phase} · line"] = f"{home['abbreviation']} {spread_h:+g}"
                    else:
                        row[f"{phase} · line"] = "—"
                    row[f"{phase} · {away['abbreviation']} px"] = _fmt(r["away_price"])
                    row[f"{phase} · {home['abbreviation']} px"] = _fmt(r["home_price"])
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    # ---------------------------------------------------------------
    # Total table
    # ---------------------------------------------------------------
    st.markdown("#### Total")
    tot_df = odds_df[odds_df["market"] == "totals"]
    if tot_df.empty:
        st.caption("No total data captured.")
    else:
        lookup = _phase_lookup(tot_df)
        books = sorted(tot_df["bookmaker"].unique())
        rows = []
        for book in books:
            row = {"Book": book.upper()}
            for phase in PHASES:
                r = lookup.get((book, phase))
                if r is None:
                    row[f"{phase} · line"] = "—"
                    row[f"{phase} · O px"] = "—"
                    row[f"{phase} · U px"] = "—"
                else:
                    line = r["total_line"]
                    row[f"{phase} · line"] = f"{line:g}" if pd.notna(line) else "—"
                    row[f"{phase} · O px"] = _fmt(r["over_price"])
                    row[f"{phase} · U px"] = _fmt(r["under_price"])
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.caption(
        f"All prices in decimal odds. {len(odds_df)} total snapshot rows across "
        f"{len(captured_phases)} phase(s)."
    )
