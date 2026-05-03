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
    team_minutes_forecast,
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

from lib.theme import inject_theme
inject_theme(active_page="matchup")
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
# POST-GAME CHARTS (only for Final games)
# =========================================================================
if not is_upcoming:
    from lib.data import game_team_box, game_player_box

    team_box = game_team_box(g["game_id"], _mtime=mtime)
    player_box = game_player_box(g["game_id"], _mtime=mtime)

    if not team_box.empty:
        st.subheader("📊 Team Comparison")
        st.caption("Side-by-side comparison of both teams' final box score numbers.")

        # Pick the right rows for home and away
        home_row = team_box[team_box["is_home"] == 1]
        away_row = team_box[team_box["is_home"] == 0]

        if not home_row.empty and not away_row.empty:
            home_r = home_row.iloc[0]
            away_r = away_row.iloc[0]

            # Comparison stats: mix of traditional + advanced
            COMPARISON_SPECS = [
                ("pts", "Points", ".0f"),
                ("fg_pct", "FG %", ".1%"),
                ("fg3_pct", "3P %", ".1%"),
                ("ft_pct", "FT %", ".1%"),
                ("reb", "Rebounds", ".0f"),
                ("ast", "Assists", ".0f"),
                ("stl", "Steals", ".0f"),
                ("blk", "Blocks", ".0f"),
                ("tov", "Turnovers", ".0f"),
                ("off_rating", "OFF Rating", ".1f"),
                ("def_rating", "DEF Rating", ".1f"),
                ("ts_pct", "TS %", ".1%"),
            ]
            # For "lower is better" stats
            LOWER_BETTER = {"tov", "def_rating"}

            # Build the chart — grouped horizontal bars, away vs home
            import plotly.graph_objects as go

            metric_labels = []
            home_vals = []
            away_vals = []
            home_displays = []
            away_displays = []
            home_better = []  # color flag

            for col, label, fmt in COMPARISON_SPECS:
                if col not in team_box.columns:
                    continue
                hv = home_r[col]
                av = away_r[col]
                if pd.isna(hv) or pd.isna(av):
                    continue
                metric_labels.append(label)
                home_vals.append(float(hv))
                away_vals.append(float(av))
                # Format display (handle %)
                if fmt == ".1%":
                    home_displays.append(f"{hv*100:.1f}%")
                    away_displays.append(f"{av*100:.1f}%")
                elif fmt == ".1f":
                    home_displays.append(f"{hv:.1f}")
                    away_displays.append(f"{av:.1f}")
                else:
                    home_displays.append(f"{int(hv)}")
                    away_displays.append(f"{int(av)}")
                # Determine winner per metric
                if col in LOWER_BETTER:
                    home_better.append(hv < av)
                else:
                    home_better.append(hv > av)

            # Normalize values to 0-1 for the chart so percentages and counts coexist
            # Per row, home_pct = hv / (hv + av), so the bars sum to 100%
            home_pct = []
            away_pct = []
            for hv, av in zip(home_vals, away_vals):
                total = abs(hv) + abs(av)
                if total == 0:
                    home_pct.append(0.5)
                    away_pct.append(0.5)
                else:
                    home_pct.append(abs(hv) / total)
                    away_pct.append(abs(av) / total)

            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=metric_labels,
                x=[-p for p in away_pct],  # negative for left side
                orientation="h",
                name=away["abbreviation"],
                marker=dict(color="#5FBE85", line=dict(width=0)),
                text=away_displays,
                textposition="inside",
                insidetextanchor="end",
                textfont=dict(color="#0E1525", size=11, family="sans-serif"),
                hovertemplate=f"<b>{away['full_name']}</b><br>%{{y}}: %{{text}}<extra></extra>",
            ))
            fig.add_trace(go.Bar(
                y=metric_labels,
                x=home_pct,  # positive for right side
                orientation="h",
                name=home["abbreviation"],
                marker=dict(color="#F4A742", line=dict(width=0)),
                text=home_displays,
                textposition="inside",
                insidetextanchor="start",
                textfont=dict(color="#0E1525", size=11, family="sans-serif"),
                hovertemplate=f"<b>{home['full_name']}</b><br>%{{y}}: %{{text}}<extra></extra>",
            ))
            fig.update_layout(
                barmode="relative",
                height=max(380, 30 * len(metric_labels) + 80),
                margin=dict(l=10, r=10, t=10, b=30),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(
                    title="",
                    color="#8B95A8",
                    gridcolor="rgba(0,0,0,0)",
                    zerolinecolor="#25304a",
                    zerolinewidth=2,
                    showticklabels=False,
                    range=[-1, 1],
                ),
                yaxis=dict(
                    color="#E5E9F0",
                    autorange="reversed",  # first metric on top
                    tickfont=dict(size=12),
                ),
                legend=dict(
                    orientation="h",
                    y=-0.05,
                    x=0.5,
                    xanchor="center",
                    bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#E5E9F0"),
                ),
                hoverlabel=dict(bgcolor="#172033", bordercolor="#25304a",
                                 font=dict(color="#E5E9F0")),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # ---- BOX SCORE — All players who appeared, both teams side by side ----
    if not player_box.empty:
        st.subheader("📋 Box Score")
        st.caption("All players who appeared in the game. Sorted by minutes within each team. "
                    "Click any column header to re-sort.")

        # Filter to players who actually played
        active = player_box[player_box["minutes"].fillna(0) > 0].copy()
        if active.empty:
            st.info("No players with minutes recorded.")
        else:
            def _format_min(v):
                if pd.isna(v):
                    return "—"
                # NBA box scores show like 32:45 typically. Our minutes is decimal.
                m = int(v)
                s = int(round((v - m) * 60))
                return f"{m}:{s:02d}"

            def _format_pm(v):
                if pd.isna(v):
                    return "—"
                return f"{int(v):+d}"

            def _build_team_box(side: str, team_id_val: int, team_name: str):
                tdf = active[active["team_id"] == team_id_val].copy()
                if tdf.empty:
                    return
                tdf = tdf.sort_values(["is_starter", "minutes"], ascending=[False, False])

                rows = []
                for _, r in tdf.iterrows():
                    rows.append({
                        "Player": ("★ " if r["is_starter"] else "  ") + r["player_name"],
                        "MIN": _format_min(r["minutes"]),
                        "PTS": int(r["pts"]) if pd.notna(r["pts"]) else 0,
                        "REB": int(r["reb"]) if pd.notna(r["reb"]) else 0,
                        "AST": int(r["ast"]) if pd.notna(r["ast"]) else 0,
                        "STL": int(r["stl"]) if pd.notna(r["stl"]) else 0,
                        "BLK": int(r["blk"]) if pd.notna(r["blk"]) else 0,
                        "TO": int(r["tov"]) if pd.notna(r["tov"]) else 0,
                        "FG": f"{int(r['fgm'])}-{int(r['fga'])}" if pd.notna(r["fgm"]) else "—",
                        "3P": f"{int(r['fg3m'])}-{int(r['fg3a'])}" if pd.notna(r["fg3m"]) else "—",
                        "FT": f"{int(r['ftm'])}-{int(r['fta'])}" if pd.notna(r["ftm"]) else "—",
                        "+/-": _format_pm(r.get("plus_minus")) if "plus_minus" in r else "—",
                    })
                bdf = pd.DataFrame(rows)

                # Color +/- column green/red
                def _style_pm(row: pd.Series) -> list[str]:
                    styles = [""] * len(row)
                    pm_str = row.get("+/-", "")
                    if pm_str and pm_str not in ("—", "+0", "0"):
                        try:
                            pm_val = int(pm_str.replace("+", ""))
                        except ValueError:
                            return styles
                        col_idx = row.index.get_loc("+/-")
                        if pm_val > 0:
                            styles[col_idx] = "background-color: rgba(62,168,102,0.18); color: #5FBE85; font-weight: 600;"
                        elif pm_val < 0:
                            styles[col_idx] = "background-color: rgba(200,70,70,0.18); color: #E37070; font-weight: 600;"
                    return styles

                styler = bdf.style.apply(_style_pm, axis=1)
                st.markdown(f"#### {team_name}")
                st.dataframe(styler, hide_index=True, width="stretch")

            box_cols = st.columns(2)
            with box_cols[0]:
                _build_team_box("away", away_id, f"✈️ {away['full_name']}")
            with box_cols[1]:
                _build_team_box("home", home_id, f"🏠 {home['full_name']}")

            st.caption("★ = starter. Minutes shown as MM:SS. +/- colored green (positive) or red (negative).")

    # ---- QUARTER-BY-QUARTER SCORING — stacked area chart ----
    from lib.data import quarter_scores_for_game
    qtr_df = quarter_scores_for_game(g["game_id"], _mtime=mtime)
    if not qtr_df.empty and len(qtr_df) >= 2:
        st.subheader("📈 Quarter-by-Quarter Scoring")
        st.caption("Stacked area showing cumulative points by end of each period. "
                    "Each band is one quarter's contribution.")

        import plotly.graph_objects as go

        # Build data: for each team, points scored in each period (Q1-4 + OTs if any)
        # Then cumulative for the running-total area chart
        home_qtr_row = qtr_df[qtr_df["is_home"] == 1]
        away_qtr_row = qtr_df[qtr_df["is_home"] == 0]

        if home_qtr_row.empty or away_qtr_row.empty:
            st.caption("Quarter data incomplete for this game.")
        else:
            home_q = home_qtr_row.iloc[0]
            away_q = away_qtr_row.iloc[0]

            # Detect OT periods present
            periods = ["Q1", "Q2", "Q3", "Q4"]
            for ot_i in range(1, 5):
                col = f"pts_ot{ot_i}"
                hv = home_q.get(col)
                av = away_q.get(col)
                if (pd.notna(hv) and hv > 0) or (pd.notna(av) and av > 0):
                    periods.append(f"OT{ot_i}")

            def _period_pts(team_row, period: str) -> int:
                if period.startswith("Q"):
                    col = f"pts_q{period[1]}"
                else:
                    col = f"pts_ot{period[2]}"
                v = team_row.get(col)
                return int(v) if pd.notna(v) else 0

            # x-axis points: end of each period (0=tip, 1=end of Q1, etc.)
            x_labels = ["Tip"] + periods
            x_indices = list(range(len(x_labels)))

            # Cumulative scores at each x
            home_cum = [0]
            away_cum = [0]
            for p in periods:
                home_cum.append(home_cum[-1] + _period_pts(home_q, p))
                away_cum.append(away_cum[-1] + _period_pts(away_q, p))

            fig = go.Figure()
            # Away team area (filled to zero)
            fig.add_trace(go.Scatter(
                x=x_indices, y=away_cum,
                mode="lines+markers+text",
                name=away["abbreviation"],
                line=dict(color="#5FBE85", width=3),
                marker=dict(size=8, color="#5FBE85"),
                fill="tozeroy",
                fillcolor="rgba(95,190,133,0.18)",
                text=[str(v) if v > 0 else "" for v in away_cum],
                textposition="top center",
                textfont=dict(color="#5FBE85", size=11),
                hovertemplate=f"<b>{away['full_name']}</b><br>%{{x}}: %{{y}} pts<extra></extra>",
            ))
            # Home team area (overlaid, semi-transparent)
            fig.add_trace(go.Scatter(
                x=x_indices, y=home_cum,
                mode="lines+markers+text",
                name=home["abbreviation"],
                line=dict(color="#F4A742", width=3),
                marker=dict(size=8, color="#F4A742"),
                fill="tozeroy",
                fillcolor="rgba(244,167,66,0.18)",
                text=[str(v) if v > 0 else "" for v in home_cum],
                textposition="bottom center",
                textfont=dict(color="#F4A742", size=11),
                hovertemplate=f"<b>{home['full_name']}</b><br>%{{x}}: %{{y}} pts<extra></extra>",
            ))

            fig.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=20, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(
                    title="",
                    tickmode="array",
                    tickvals=x_indices,
                    ticktext=x_labels,
                    color="#E5E9F0",
                    gridcolor="#25304a",
                    zerolinecolor="#25304a",
                ),
                yaxis=dict(
                    title="Cumulative Points",
                    color="#8B95A8",
                    gridcolor="#25304a",
                    zerolinecolor="#25304a",
                ),
                legend=dict(
                    orientation="h", y=1.08, x=0.5, xanchor="center",
                    bgcolor="rgba(0,0,0,0)", font=dict(color="#E5E9F0"),
                ),
                hoverlabel=dict(bgcolor="#172033", bordercolor="#25304a",
                                 font=dict(color="#E5E9F0")),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

            # Per-quarter breakdown table below the chart
            qtr_breakdown = pd.DataFrame({
                "": ["1st", "2nd", "3rd", "4th"] + [p for p in periods if p.startswith("OT")] + ["Final"],
                away["abbreviation"]: (
                    [_period_pts(away_q, p) for p in periods] +
                    [int(away_q["pts_total"]) if pd.notna(away_q["pts_total"]) else 0]
                ),
                home["abbreviation"]: (
                    [_period_pts(home_q, p) for p in periods] +
                    [int(home_q["pts_total"]) if pd.notna(home_q["pts_total"]) else 0]
                ),
            })
            st.dataframe(qtr_breakdown, hide_index=True, width="stretch")
    elif not is_upcoming:
        st.caption("📈 Quarter-by-quarter data not available — run "
                    "`python -m scripts.run quarters` to backfill.")

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
# Trend charts — both teams, respecting selected window
# =========================================================================
from lib.data import WINDOW_TO_LAST_N

# For 'Season' window, cap to 30 games to keep the chart readable
_trend_n = WINDOW_TO_LAST_N.get(window) or 30

st.subheader(f"📈 Trend — {window} ({_trend_n} games)")

def _trend(team_id: int, team_name: str, color: str):
    df = team_recent_games(team_id, last_n=_trend_n,
                            season_filter=season_filter,
                            _mtime=mtime).sort_values("game_date")
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
edge_meta = []  # parallel list: (away_off_diff_norm, home_off_diff_norm) for coloring
for metric, ao, hd, ho, ad, lavg, fmtfn in edge_rows:
    table_rows.append({
        "Metric": metric,
        f"{away['abbreviation']} OFF": fmtfn(ao),
        f"{home['abbreviation']} D allowed": fmtfn(hd) if hd is not None else "—",
        f"{home['abbreviation']} OFF": fmtfn(ho),
        f"{away['abbreviation']} D allowed": fmtfn(ad) if ad is not None else "—",
        "League avg": fmtfn(lavg) if lavg is not None else "—",
    })
    # Compute edge size for coloring: deviation from league avg in both directions
    edge_meta.append({
        "ao": ao, "hd": hd, "ho": ho, "ad": ad, "lavg": lavg,
    })

edge_df = pd.DataFrame(table_rows)


# Color cells based on size of deviation from league avg
def _edge_style(row: pd.Series) -> list[str]:
    """Color row based on how far each cell's value is from league avg."""
    styles = [""] * len(row)
    meta = edge_meta[row.name]  # row.name is the index
    lavg = meta["lavg"]
    if lavg is None or pd.isna(lavg):
        return styles

    # Map column index by name
    col_keys = {
        f"{away['abbreviation']} OFF": ("ao", False),  # higher is better (offense)
        f"{home['abbreviation']} D allowed": ("hd", True),   # lower is better (defense)
        f"{home['abbreviation']} OFF": ("ho", False),
        f"{away['abbreviation']} D allowed": ("ad", True),
    }
    # Pace and Fouls have no clear good/bad direction — neutralize
    is_neutral_metric = row["Metric"] in ("Pace", "Fouls drawn")

    for col_name, (key, lower_better) in col_keys.items():
        if col_name not in row.index:
            continue
        val = meta.get(key)
        if val is None or pd.isna(val):
            continue
        diff = val - lavg
        if lower_better:
            diff = -diff
        # Threshold the deviation: ratio metrics use 0.02 (=2pp), absolute use ~3 units
        # Auto-detect: if league avg < 1.5, treat as ratio
        threshold_big = 0.025 if abs(lavg) < 1.5 else 3.0
        threshold_small = 0.012 if abs(lavg) < 1.5 else 1.5

        col_idx = row.index.get_loc(col_name)
        if is_neutral_metric:
            continue
        if diff > threshold_big:
            styles[col_idx] = "background-color: rgba(62,168,102,0.30); color: #0E1525; font-weight: 600;"
        elif diff > threshold_small:
            styles[col_idx] = "background-color: rgba(62,168,102,0.18); color: #5FBE85; font-weight: 600;"
        elif diff < -threshold_big:
            styles[col_idx] = "background-color: rgba(200,70,70,0.30); color: #0E1525; font-weight: 600;"
        elif diff < -threshold_small:
            styles[col_idx] = "background-color: rgba(200,70,70,0.18); color: #E37070; font-weight: 600;"
    return styles

styler = edge_df.style.apply(_edge_style, axis=1)
st.dataframe(styler, hide_index=True, width="stretch")
st.caption("🟢 = team has edge over league avg · 🔴 = below league avg · brighter = bigger edge")

st.divider()

# =========================================================================
# Minutes Forecast — full roster L5 minutes + plus/minus + injury flags
# =========================================================================
st.subheader("⏱️ Minutes Forecast")
st.caption(
    "L5 average minutes + plus/minus per player who appeared in the last game. "
    "🔴 OUT · 🟠 Doubtful · 🟡 Questionable · ⬆️ likely to absorb minutes from the missing players."
)

def _format_minutes(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.1f}"

def _format_pm(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.1f}"

def _status_emoji(row) -> str:
    if row["is_out"]:
        return "🔴"
    if row["is_doubtful"]:
        return "🟠"
    if row["is_questionable"]:
        return "🟡"
    if row.get("will_absorb"):
        return "⬆️"
    return ""

def _minutes_forecast_block(team_id: int, team_name: str, team_abbr: str):
    df = team_minutes_forecast(team_id, _mtime=mtime)
    st.markdown(f"#### {team_name}")
    if df.empty:
        st.caption("No recent player data found.")
        return

    # Build a display frame
    rows = []
    for _, r in df.iterrows():
        emoji = _status_emoji(r)
        starter_mark = "★" if r["is_starter_last"] else ""
        rows.append({
            "": emoji,
            "Player": f"{starter_mark} {r['player_name']}".strip(),
            "L5 MIN": _format_minutes(r["l5_min"]),
            "L5 +/−": _format_pm(r["l5_pm"]),
            "L5 GP": int(r["l5_gp"]) if pd.notna(r["l5_gp"]) else 0,
            "Last MIN": _format_minutes(r["last_min"]),
            "Status": r["injury_status"] or "",
        })
    display_df = pd.DataFrame(rows)

    # Color rows: red bg for OUT, orange for Doubtful, green for will_absorb
    def _row_style(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        idx_in_orig = row.name
        orig_row = df.iloc[idx_in_orig]
        if orig_row["is_out"]:
            return ["background-color: rgba(200,70,70,0.18); color: #E37070;"] * len(row)
        if orig_row["is_doubtful"]:
            return ["background-color: rgba(244,167,66,0.18); color: #F4A742;"] * len(row)
        if orig_row.get("will_absorb"):
            return ["background-color: rgba(62,168,102,0.15); color: #5FBE85;"] * len(row)
        return styles

    styler = display_df.style.apply(_row_style, axis=1)
    st.dataframe(
        styler,
        hide_index=True,
        width="stretch",
        column_config={
            "": st.column_config.TextColumn("", width=30),
            "Player": st.column_config.TextColumn("Player", width=180),
            "L5 MIN": st.column_config.TextColumn("L5 MIN"),
            "L5 +/−": st.column_config.TextColumn("L5 +/−"),
            "L5 GP": st.column_config.NumberColumn("GP", format="%d"),
            "Last MIN": st.column_config.TextColumn("Last MIN"),
            "Status": st.column_config.TextColumn("Status"),
        },
    )

    # Surface a quick text summary if there are missing minutes
    significant_missing = df[
        ((df["is_out"] | df["is_doubtful"])) & (df["l5_min"].fillna(0) > 15)
    ]
    if not significant_missing.empty:
        names = ", ".join(significant_missing["player_name"].tolist())
        missing_mins = significant_missing["l5_min"].sum()
        st.caption(
            f"⚠️ Missing **{missing_mins:.0f} L5 minutes** ({names}). "
            "Marked players (⬆️) are likely to absorb."
        )

scols = st.columns(2)
with scols[0]:
    _minutes_forecast_block(away_id, away["full_name"], away["abbreviation"])
with scols[1]:
    _minutes_forecast_block(home_id, home["full_name"], home["abbreviation"])

st.caption("★ = started in last game. Forecast uses L5 average — actual rotation tonight may differ.")

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
# ODDS — Goaloo-style compact view: open + latest, expandable for full phases
# =========================================================================
from lib.odds_data import odds_for_game, odds_compact_view

st.divider()
st.subheader("💰 Odds")

compact = odds_compact_view(g["game_id"], _mtime=mtime)

if not compact:
    st.info(
        "No odds data captured for this game yet. "
        "Odds are fetched 8× daily by the GitHub Actions workflow. "
        "Check back closer to tip-off."
    )
else:
    def _fmt_price(x):
        if x is None or pd.isna(x):
            return "—"
        return f"{x:.2f}"

    def _fmt_line(x, plus_sign=False):
        if x is None or pd.isna(x):
            return "—"
        if plus_sign:
            return f"{x:+g}"
        return f"{x:g}"

    def _fmt_time(iso_utc: str | None) -> str:
        if not iso_utc:
            return "—"
        # ISO 2026-05-03T14:30:00+00:00 → display "May 03 14:30 UTC"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
            return dt.strftime("%b %d %H:%M UTC")
        except Exception:
            return iso_utc[:16]

    def _movement_badge(open_val, latest_val, lower_is_better: bool = False) -> str:
        """Return colored arrow if line moved. Color reflects direction.
        For spreads (home perspective): negative spread = home favored more.
        For totals: higher = more points expected.
        """
        if open_val is None or latest_val is None or pd.isna(open_val) or pd.isna(latest_val):
            return ""
        diff = latest_val - open_val
        if abs(diff) < 0.01:
            return ""
        # Format: +0.5 or -1.0
        sign = "+" if diff > 0 else ""
        color = "#5FBE85" if diff > 0 else "#E37070"
        arrow = "▲" if diff > 0 else "▼"
        return (
            f'<span style="color:{color};font-weight:500;font-size:11px;">'
            f'{arrow} {sign}{diff:.1f}</span>'
        )

    def _market_row(market_key: str, label: str, has_line: bool):
        """Render one row per market: book name, open, latest, movement, expand."""
        info = compact.get(market_key)
        if info is None:
            st.markdown(
                f'<div style="background:#172033;border-radius:8px;padding:12px 16px;'
                f'margin-bottom:8px;color:#8B95A8;">'
                f'<strong>{label}</strong> — no data captured</div>',
                unsafe_allow_html=True,
            )
            return

        book = info["book"].upper()
        op = info["open"]
        lt = info["latest"]
        n_phases = info["n_phases"]
        moved = info["moved"]

        # Build the open + latest cells
        if has_line:
            # Spread or total — show line + price
            if market_key == "spreads":
                open_line_str = f"{home['abbreviation']} {_fmt_line(op['line'], plus_sign=True)}"
                latest_line_str = f"{home['abbreviation']} {_fmt_line(lt['line'], plus_sign=True)}"
                line_movement = _movement_badge(op["line"], lt["line"])
            else:  # totals
                open_line_str = _fmt_line(op["line"])
                latest_line_str = _fmt_line(lt["line"])
                line_movement = _movement_badge(op["line"], lt["line"])
            home_label = away["abbreviation"] if market_key == "spreads" else "O"
            away_label = home["abbreviation"] if market_key == "spreads" else "U"

            open_prices = (
                f'<span style="color:#8B95A8;font-size:11px;">'
                f'{home_label} {_fmt_price(op["away_price"])} · {away_label} {_fmt_price(op["home_price"])}</span>'
            )
            latest_prices = (
                f'<span style="color:#8B95A8;font-size:11px;">'
                f'{home_label} {_fmt_price(lt["away_price"])} · {away_label} {_fmt_price(lt["home_price"])}</span>'
            )
        else:
            # Moneyline: just home/away prices, no line
            open_line_str = ""
            latest_line_str = ""
            line_movement = ""
            open_prices = (
                f'<span>'
                f'{away["abbreviation"]} <strong style="color:#E5E9F0;">{_fmt_price(op["away_price"])}</strong> · '
                f'{home["abbreviation"]} <strong style="color:#E5E9F0;">{_fmt_price(op["home_price"])}</strong></span>'
            )
            latest_prices = (
                f'<span>'
                f'{away["abbreviation"]} <strong style="color:#E5E9F0;">{_fmt_price(lt["away_price"])}</strong> · '
                f'{home["abbreviation"]} <strong style="color:#E5E9F0;">{_fmt_price(lt["home_price"])}</strong></span>'
            )

        # Compose: [Market] [Book]   Open: line + prices · time   |  Latest: line + prices · time   movement
        moved_indicator = (
            ' <span style="color:#F4A742;font-size:10px;margin-left:4px;">●</span>'
            if moved else ""
        )

        if has_line:
            line_section = (
                f'<div style="display:flex;gap:18px;align-items:baseline;flex-wrap:wrap;">'
                f'<div><span style="color:#8B95A8;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;">Open</span> '
                f'<strong style="color:#E5E9F0;font-size:14px;">{open_line_str}</strong> '
                f'{open_prices} '
                f'<span style="color:#8B95A8;font-size:10px;margin-left:4px;">{_fmt_time(op["fetched_utc"])}</span></div>'
                f'<div><span style="color:#8B95A8;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;">Latest</span> '
                f'<strong style="color:#E5E9F0;font-size:14px;">{latest_line_str}</strong> '
                f'{line_movement} '
                f'{latest_prices} '
                f'<span style="color:#8B95A8;font-size:10px;margin-left:4px;">{_fmt_time(lt["fetched_utc"])}</span></div>'
                f'</div>'
            )
        else:
            line_section = (
                f'<div style="display:flex;gap:18px;align-items:baseline;flex-wrap:wrap;">'
                f'<div><span style="color:#8B95A8;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;">Open</span> '
                f'{open_prices} '
                f'<span style="color:#8B95A8;font-size:10px;margin-left:4px;">{_fmt_time(op["fetched_utc"])}</span></div>'
                f'<div><span style="color:#8B95A8;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;">Latest</span> '
                f'{latest_prices} '
                f'<span style="color:#8B95A8;font-size:10px;margin-left:4px;">{_fmt_time(lt["fetched_utc"])}</span></div>'
                f'</div>'
            )

        header_html = (
            f'<div style="background:#172033;border-radius:8px;padding:10px 14px;'
            f'margin-bottom:8px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:6px;">'
            f'<div><strong style="color:#E5E9F0;font-size:13px;">{label}</strong>'
            f' <span style="color:#8B95A8;font-size:11px;margin-left:6px;">{book}{moved_indicator}</span></div>'
            f'<span style="color:#8B95A8;font-size:10px;">{n_phases} snapshot{"s" if n_phases != 1 else ""}</span>'
            f'</div>'
            f'{line_section}'
            f'</div>'
        )
        st.markdown(header_html, unsafe_allow_html=True)

    # Render compact view
    _market_row("spreads", "Spread", has_line=True)
    _market_row("totals",  "Total",  has_line=True)
    _market_row("h2h",     "Moneyline", has_line=False)

    # Expander: show full timeline of all phases for all books
    with st.expander("▶ Show full snapshot history", expanded=False):
        odds_df = odds_for_game(g["game_id"], _mtime=mtime)
        if odds_df.empty:
            st.caption("No snapshots.")
        else:
            for market_key, label in [("spreads", "Spread"), ("totals", "Total"), ("h2h", "Moneyline")]:
                m_df = odds_df[odds_df["market"] == market_key].copy()
                if m_df.empty:
                    continue
                st.markdown(f"**{label}**")
                # Build a clean timeline table
                if market_key == "spreads":
                    m_df["line"] = m_df.apply(
                        lambda r: f"{home['abbreviation']} {r['spread_home']:+g}"
                        if pd.notna(r["spread_home"]) else "—", axis=1)
                    m_df["away_px"] = m_df["away_price"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    m_df["home_px"] = m_df["home_price"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    cols = ["fetched_utc", "snapshot_phase", "bookmaker", "line", "away_px", "home_px"]
                elif market_key == "totals":
                    m_df["line"] = m_df["total_line"].apply(lambda x: f"{x:g}" if pd.notna(x) else "—")
                    m_df["over_px"] = m_df["over_price"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    m_df["under_px"] = m_df["under_price"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    cols = ["fetched_utc", "snapshot_phase", "bookmaker", "line", "over_px", "under_px"]
                else:  # h2h
                    m_df["away_px"] = m_df["away_price"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    m_df["home_px"] = m_df["home_price"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    cols = ["fetched_utc", "snapshot_phase", "bookmaker", "away_px", "home_px"]
                m_df = m_df.sort_values("fetched_utc", ascending=False)[cols]
                m_df["fetched_utc"] = m_df["fetched_utc"].apply(_fmt_time)
                st.dataframe(m_df.rename(columns={
                    "fetched_utc": "When",
                    "snapshot_phase": "Phase",
                    "bookmaker": "Book",
                }), hide_index=True, width="stretch")
