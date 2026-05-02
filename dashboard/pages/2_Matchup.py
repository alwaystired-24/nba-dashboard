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
    team_rest_days,
    team_injuries,
    team_news,
)
from lib.freshness import show_freshness_banner
from lib.filters import window_picker, season_filter_picker, SEASON_FILTER_LABELS
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

filter_col1, filter_col2 = st.columns(2)
with filter_col1:
    window = window_picker(default="L10")
with filter_col2:
    season_filter = season_filter_picker()
st.caption(f"Showing **{SEASON_FILTER_LABELS[season_filter]}** stats. "
            "Change at top of any page.")

home_id, away_id = int(g["home_team_id"]), int(g["away_team_id"])
home, away = tlookup[home_id], tlookup[away_id]
is_upcoming = g["status"] != "Final"


# =========================================================================
# Compact header strip
# =========================================================================
def _rest_label(team_id: int, game_date: str) -> str:
    rd = team_rest_days(team_id, game_date, _mtime=mtime)
    if rd is None:
        return "Rest: —"
    if rd == 0:
        return "Rest: 🔴 BTB (0)"
    if rd == 1:
        return f"Rest: 1 day"
    if rd >= 3:
        return f"Rest: 🟢 {rd} days"
    return f"Rest: {rd} days"


def _record_pill(w: int, l: int, label: str) -> str:
    """Color a record pill based on win pct."""
    if w + l == 0:
        bg, color = "#25304a", "#8B95A8"
    else:
        win_pct = w / (w + l)
        if win_pct >= 0.55:
            bg, color = "rgba(62,168,102,0.18)", "#5FBE85"
        elif win_pct <= 0.45:
            bg, color = "rgba(200,70,70,0.18)", "#E37070"
        else:
            bg, color = "#25304a", "#E5E9F0"
    return (
        f'<span style="padding:2px 7px;background:{bg};color:{color};'
        f'border-radius:4px;font-size:11px;">{label} {w}-{l}</span>'
    )


# Big-logo header card with team logos
from lib.branding import team_logo_url

wA, lA = team_record(away_id, "Season", season_filter, _mtime=mtime)
wA_w, lA_w = team_record(away_id, window, season_filter, _mtime=mtime)
wH, lH = team_record(home_id, "Season", season_filter, _mtime=mtime)
wH_w, lH_w = team_record(home_id, window, season_filter, _mtime=mtime)

away_logo = team_logo_url(away_id, size=500)
home_logo = team_logo_url(home_id, size=500)

# Center column content depends on game state
if g["status"] == "Final" and pd.notna(g["away_score"]):
    center_top = f'<div style="font-size:11px;color:#8B95A8;letter-spacing:0.05em;text-transform:uppercase;margin-bottom:6px;">{g["season_type"]} · {g["game_date"]}</div>'
    center_main = f'<div style="font-size:32px;color:#E5E9F0;font-weight:500;letter-spacing:0.02em;">{int(g["away_score"])} – {int(g["home_score"])}</div>'
    center_sub = '<div style="font-size:11px;color:#8B95A8;margin-top:4px;">🏁 Final</div>'
else:
    center_top = f'<div style="font-size:11px;color:#8B95A8;letter-spacing:0.05em;text-transform:uppercase;margin-bottom:6px;">{g["season_type"]} · {g["game_date"]}</div>'
    center_main = '<div style="font-size:18px;color:#F4A742;font-weight:500;letter-spacing:0.05em;">VS</div>'
    center_sub = '<div style="font-size:11px;color:#8B95A8;margin-top:4px;">Upcoming</div>'

away_rest = _rest_label(away_id, g["game_date"])
home_rest = _rest_label(home_id, g["game_date"])

header_html = f'''
<div style="background:#172033;border-radius:12px;padding:18px 20px;margin-bottom:1rem;">
  <div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:20px;">
    <div style="text-align:center;">
      <img src="{away_logo}" style="width:72px;height:72px;margin-bottom:8px;" alt="{away["abbreviation"]}">
      <div style="font-size:18px;color:#E5E9F0;font-weight:500;margin-bottom:6px;">✈️ {away["full_name"]}</div>
      <div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap;">
        {_record_pill(wA, lA, "Season")}
        {_record_pill(wA_w, lA_w, window)}
      </div>
      <div style="font-size:11px;color:#8B95A8;margin-top:8px;">{away_rest}</div>
    </div>
    <div style="text-align:center;min-width:120px;">
      {center_top}
      {center_main}
      {center_sub}
    </div>
    <div style="text-align:center;">
      <img src="{home_logo}" style="width:72px;height:72px;margin-bottom:8px;" alt="{home["abbreviation"]}">
      <div style="font-size:18px;color:#E5E9F0;font-weight:500;margin-bottom:6px;">🏠 {home["full_name"]}</div>
      <div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap;">
        {_record_pill(wH, lH, "Season")}
        {_record_pill(wH_w, lH_w, window)}
      </div>
      <div style="font-size:11px;color:#8B95A8;margin-top:8px;">{home_rest}</div>
    </div>
  </div>
</div>
'''
st.markdown(header_html, unsafe_allow_html=True)

# =========================================================================
# Injuries + news panel (Phase 7)
# =========================================================================

def _injury_status_color(status: str) -> tuple[str, str]:
    """Return (bg, color) for an injury status pill."""
    s = (status or "").lower()
    if "out" in s or "suspended" in s:
        return ("rgba(200,70,70,0.18)", "#E37070")
    if "doubtful" in s:
        return ("rgba(244,167,66,0.20)", "#F4A742")
    if "questionable" in s or "day-to-day" in s:
        return ("rgba(244,167,66,0.15)", "#F4A742")
    if "probable" in s:
        return ("rgba(62,168,102,0.18)", "#5FBE85")
    return ("#25304a", "#8B95A8")


def _injury_news_card_html(team_id: int, team_label: str) -> str:
    inj = team_injuries(team_id, _mtime=mtime)
    news = team_news(team_id, limit=3, _mtime=mtime)
    logo = team_logo_url(team_id, size=500)

    # Header: logo + name + status pill
    out_count = 0 if inj.empty else int(
        inj["status"].str.lower().str.contains("out|suspended|doubtful").sum()
    )
    if out_count == 0:
        head_pill_bg = "rgba(62,168,102,0.18)"
        head_pill_color = "#5FBE85"
        head_pill_label = "All clear"
    else:
        head_pill_bg = "rgba(200,70,70,0.18)"
        head_pill_color = "#E37070"
        head_pill_label = f"{out_count} out"

    head_html = (
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
        f'<img src="{logo}" style="width:22px;height:22px;" alt="">'
        f'<span style="font-size:13px;color:#E5E9F0;font-weight:500;">{team_label}</span>'
        f'<span style="font-size:11px;padding:1px 6px;border-radius:4px;'
        f'background:{head_pill_bg};color:{head_pill_color};margin-left:auto;">{head_pill_label}</span>'
        f'</div>'
    )

    # Injury rows
    if inj.empty:
        body_html = '<div style="font-size:12px;color:#8B95A8;padding:4px 0;">No injuries reported</div>'
    else:
        rows = []
        for _, row in inj.iterrows():
            bg, color = _injury_status_color(row["status"])
            detail = (row["detail"] or "")[:60]
            if len(row["detail"] or "") > 60:
                detail += "…"
            rows.append(
                f'<div style="font-size:12px;color:#E5E9F0;padding:4px 0;'
                f'display:flex;justify-content:space-between;gap:8px;">'
                f'<span>{row["player_name"]}</span>'
                f'<span style="color:{color};white-space:nowrap;">{row["status"]}</span>'
                f'</div>'
            )
            if detail:
                rows.append(
                    f'<div style="font-size:11px;color:#8B95A8;padding:0 0 6px;line-height:1.4;">{detail}</div>'
                )
        body_html = "".join(rows)

    # News rows (top 3)
    news_html = ""
    if not news.empty:
        items = []
        for _, art in news.iterrows():
            cat_str = f'<span style="font-size:10px;color:#F4A742;margin-right:6px;">{art["category"]}</span>' if art["category"] else ""
            url = art["url"] or "#"
            items.append(
                f'<div style="font-size:11px;color:#E5E9F0;padding:4px 0;line-height:1.4;">'
                f'{cat_str}<a href="{url}" target="_blank" style="color:#E5E9F0;text-decoration:none;">{art["headline"]}</a>'
                f'</div>'
            )
        news_html = (
            f'<div style="margin-top:10px;padding-top:8px;border-top:1px solid #25304a;">'
            f'<div style="font-size:10px;color:#8B95A8;letter-spacing:0.05em;text-transform:uppercase;'
            f'margin-bottom:4px;">📰 Recent news</div>'
            f'{"".join(items)}'
            f'</div>'
        )

    return (
        f'<div style="background:#172033;border-radius:12px;padding:12px 16px;">'
        f'{head_html}{body_html}{news_html}'
        f'</div>'
    )


# Render injury+news cards
st.markdown(
    '<p style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;'
    'color:#8B95A8;margin:1.25rem 0 10px;">Injuries & news</p>',
    unsafe_allow_html=True,
)
inj_cols = st.columns(2)
with inj_cols[0]:
    st.markdown(_injury_news_card_html(away_id, away["full_name"]), unsafe_allow_html=True)
with inj_cols[1]:
    st.markdown(_injury_news_card_html(home_id, home["full_name"]), unsafe_allow_html=True)
st.caption("Injuries refreshed every 4h via GitHub Actions · sourced from ESPN")

# =========================================================================
# League average baseline (used in Edge Finder and key metrics)
# =========================================================================
@st.cache_data(show_spinner=False)
def _league_means(window: str, season_filter: str, _mtime: float):
    df = league_team_table(window, season_filter, _mtime=_mtime)
    return df.mean(numeric_only=True).to_dict()

lg = _league_means(window, season_filter, _mtime=mtime)

st.divider()

# =========================================================================
# Form snapshot — colored metric cards, 4 per row, ranks vs full league
# =========================================================================
st.subheader(f"📊 Form snapshot — {window}")
st.caption("Each card shows team value, delta vs league average, and league rank. "
            "Green = above avg, red = below. Add more metrics later by editing the spec list.")

from lib.coloring import metric_card_html, metric_cards_grid_html
from lib.data import league_team_table, compute_team_ranks

# Build the league table once and compute ranks
@st.cache_data(show_spinner=False)
def _league_table_with_ranks(window: str, season_filter: str, _mtime: float):
    df = league_team_table(window, season_filter, _mtime=_mtime)
    return compute_team_ranks(df)

league_with_ranks = _league_table_with_ranks(window, season_filter, _mtime=mtime)


# Metric specs: (metric_key, label, source, format_fn, lower_is_better, is_neutral)
# - source: "agg" or "opp"
# - format_fn: takes float, returns str
# - lower_is_better: only used to invert delta sign in display
# - is_neutral: True for Pace etc. — no good/bad direction, always shows neutral color
def _fmt_num(v):
    return f"{v:.1f}" if v is not None and pd.notna(v) else "—"

def _fmt_pct(v):
    return f"{v*100:.1f}" if v is not None and pd.notna(v) else "—"

FORM_METRICS = [
    # Row 1
    ("off_rating",    "ORtg",     "agg", _fmt_num, False, False, "raw"),
    ("def_rating",    "DRtg",     "agg", _fmt_num, True,  False, "raw"),
    ("net_rating",    "NetRtg",   "agg", _fmt_num, False, False, "raw"),
    ("pace",          "Pace",     "agg", _fmt_num, False, True,  "raw"),
    # Row 2
    ("efg_pct",       "eFG%",     "agg", _fmt_pct, False, False, "pp"),
    ("ts_pct",        "TS%",      "agg", _fmt_pct, False, False, "pp"),
    ("opp_efg_pct",   "OPP eFG%", "opp", _fmt_pct, True,  False, "pp"),
    ("opp_fg3_pct",   "OPP 3P%",  "opp", _fmt_pct, True,  False, "pp"),
]

def _delta_text(team_val, league_val, kind: str, lower_is_better: bool) -> str | None:
    if team_val is None or league_val is None or pd.isna(team_val) or pd.isna(league_val):
        return None
    diff = team_val - league_val
    if kind == "pp":
        # convert ratio diff to percentage points
        return f"{diff*100:+.1f}pp"
    return f"{diff:+.1f}"

def _form_cards_html(team_id: int) -> str:
    agg = team_aggregate(team_id, window, season_filter, _mtime=mtime)
    opp = team_opponent_aggregate(team_id, window, season_filter, _mtime=mtime)
    team_row = league_with_ranks[league_with_ranks["team_id"] == team_id]

    cards = []
    for metric, label, source, fmt_fn, lower_better, is_neutral, delta_kind in FORM_METRICS:
        src = agg if source == "agg" else opp
        team_val = src.get(metric)
        league_val = lg.get(metric)
        rank = None
        if not team_row.empty and f"{metric}_rank" in team_row.columns:
            r = team_row.iloc[0][f"{metric}_rank"]
            if pd.notna(r):
                rank = int(r)
        delta = _delta_text(team_val, league_val, delta_kind, lower_better)
        cards.append(metric_card_html(
            label=label,
            value=fmt_fn(team_val),
            delta=delta,
            rank=rank,
            n_total=30,
            is_neutral_metric=is_neutral,
        ))
    return metric_cards_grid_html(cards, cols=4)


# Render: per-team header line + grid
for team_id, team_obj, side_emoji in [
    (away_id, away, "✈️"),
    (home_id, home, "🏠"),
]:
    st.markdown(
        f'<p style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;'
        f'color:#8B95A8;margin:0.5rem 0 0.5rem;">{side_emoji} {team_obj["full_name"]}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(_form_cards_html(team_id), unsafe_allow_html=True)

st.divider()

# =========================================================================
# Trend charts — both teams' L20
# =========================================================================
st.subheader("📈 Last 20 games — trend")

def _trend(team_id: int, team_name: str, color: str):
    df = team_recent_games(team_id, last_n=20, season_filter=season_filter, _mtime=mtime).sort_values("game_date")
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

a_off = team_aggregate(away_id, window, season_filter, _mtime=mtime)
a_def = team_opponent_aggregate(away_id, window, season_filter, _mtime=mtime)
h_off = team_aggregate(home_id, window, season_filter, _mtime=mtime)
h_def = team_opponent_aggregate(home_id, window, season_filter, _mtime=mtime)

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
