"""Today's Games + upcoming schedule, grouped by HKT date."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st


from lib.data import (
    db_mtime,
    games_in_window,
    latest_loaded_date,
    team_aggregate,
    team_record,
    team_lookup,
    all_team_injury_counts,
    team_injuries,
    conference_standings,
    stat_leaders,
    league_injuries_top,
    closing_line_for_game,
)
from lib.freshness import show_freshness_banner
from lib.filters import season_filter_picker, SEASON_FILTER_LABELS
from lib.format import (
    fmt_num,
    hkt_to_et_date,
    hkt_today,
    matchup_label,
    status_badge,
)

st.set_page_config(page_title="Today's Games", page_icon="📅", layout="wide")

from lib.theme import inject_theme
inject_theme(active_page="today")
st.title("📅 Today & Upcoming")

mtime = db_mtime()
show_freshness_banner(mtime)

season_filter = season_filter_picker()
st.caption(f"Showing **{SEASON_FILTER_LABELS[season_filter]}** form previews. "
            "Change at top of any page.")

injury_counts = all_team_injury_counts(_mtime=mtime)
tlookup = team_lookup(_mtime=mtime)

# --- Range: yesterday, today, tomorrow only ---------------------------
today = date.fromisoformat(hkt_today())
hkt_window_start = today - timedelta(days=1)
hkt_window_end = today + timedelta(days=1)
et_window_start = hkt_to_et_date(hkt_window_start.isoformat())
et_window_end = hkt_to_et_date(hkt_window_end.isoformat())

games = games_in_window(et_window_start, et_window_end, _mtime=mtime)
if games.empty:
    last = latest_loaded_date(_mtime=mtime)
    st.info(
        f"No games found in this date range. "
        f"Latest game date in your database: **{last or '—'}**. "
        "Run `python -m scripts.run daily` to refresh."
    )
    st.stop()

# --- Bucket games by HKT date label ------------------------------------
# game_date is ET; HKT date = ET date + 1 (NBA games are evening ET = morning HKT next day)
def _hkt_label(et_date_str: str) -> str:
    et = date.fromisoformat(et_date_str)
    hkt = et + timedelta(days=1)
    delta = (hkt - today).days
    if delta == -1: return "Yesterday"
    if delta == 0:  return "Today"
    if delta == 1:  return "Tomorrow"
    return None  # filter out anything else

games = games.assign(hkt_label=games["game_date"].apply(_hkt_label))
games = games[games["hkt_label"].notna()]  # drop dates outside window

if games.empty:
    st.info("No games in yesterday/today/tomorrow window.")
    st.stop()

# Show in fixed order
seen_labels = [lbl for lbl in ["Yesterday", "Today", "Tomorrow"]
                if not games[games["hkt_label"] == lbl].empty]

for label in seen_labels:
    bucket = games[games["hkt_label"] == label].sort_values("game_id")
    finished = (bucket["status"] == "Final").sum()
    total = len(bucket)
    st.markdown(
        f'<p style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;'
        f'color:#8B95A8;margin:1.25rem 0 10px;">{label} · {total} game{"s" if total != 1 else ""}'
        f'{f" · {finished} final" if finished else ""}</p>',
        unsafe_allow_html=True,
    )

    from lib.branding import team_logo_url

    def _named_injuries_html(team_id: int, team_abbr: str) -> str:
        """Return HTML chips for Out/Doubtful/Suspended players. Empty string if none."""
        inj = team_injuries(team_id, _mtime=mtime)
        if inj.empty:
            return (
                f'<span style="padding:2px 7px;border-radius:4px;'
                f'background:rgba(62,168,102,0.18);color:#5FBE85;font-size:11px;'
                f'white-space:nowrap;">✓ {team_abbr} all clear</span>'
            )
        # Filter to actionable statuses only
        actionable = inj[inj["status"].str.lower().isin(
            ["out", "out for season", "doubtful", "suspended", "questionable"]
        )]
        if actionable.empty:
            return (
                f'<span style="padding:2px 7px;border-radius:4px;'
                f'background:rgba(62,168,102,0.18);color:#5FBE85;font-size:11px;'
                f'white-space:nowrap;">✓ {team_abbr} all clear</span>'
            )

        chips = []
        for _, row in actionable.iterrows():
            status = row["status"]
            s_lower = status.lower()
            if "out" in s_lower or "suspended" in s_lower:
                bg, color = "rgba(200,70,70,0.18)", "#E37070"
                short_status = "OUT"
            elif "doubtful" in s_lower:
                bg, color = "rgba(244,167,66,0.20)", "#F4A742"
                short_status = "DTD"
            else:
                bg, color = "rgba(244,167,66,0.15)", "#F4A742"
                short_status = "Q"
            # Last name only to save space
            last_name = row["player_name"].split(" ", 1)[-1] if " " in row["player_name"] else row["player_name"]
            chips.append(
                f'<span style="padding:1px 6px;border-radius:4px;'
                f'background:{bg};color:{color};font-size:11px;white-space:nowrap;">'
                f'{last_name} ({short_status})</span>'
            )

        team_pill = (
            f'<span style="font-size:11px;color:#8B95A8;margin-right:4px;'
            f'white-space:nowrap;">{team_abbr}:</span>'
        )
        return team_pill + " ".join(chips)

    def _status_pill(status: str) -> str:
        if status == "Final":
            return ('<span style="font-size:11px;padding:2px 8px;border-radius:4px;'
                     'background:#25304a;color:#8B95A8;font-weight:500;">Final</span>')
        if status == "Live":
            return ('<span style="font-size:11px;padding:2px 8px;border-radius:4px;'
                     'background:#F4A742;color:#0E1525;font-weight:500;">Live</span>')
        return ('<span style="font-size:11px;padding:2px 8px;border-radius:4px;'
                 'background:rgba(244,167,66,0.15);color:#F4A742;font-weight:500;">Upcoming</span>')

    def _team_row(g, side: str) -> str:
        team_id = int(g[f"{side}_team_id"])
        abbr = g[f"{side}_abbr"]
        full_name = tlookup.get(team_id, {}).get("full_name", abbr)
        logo = team_logo_url(team_id, size=500)
        w, l = team_record(team_id, "L10", season_filter, _mtime=mtime)

        # Right-side info: score for Final, blank for upcoming (closing line shown below)
        score = ""
        if g["status"] == "Final" and pd.notna(g[f"{side}_score"]):
            score = f'<div style="font-size:22px;color:#E5E9F0;font-weight:500;">{int(g[f"{side}_score"])}</div>'

        return (
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'margin-bottom:6px;">'
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<img src="{logo}" style="width:32px;height:32px;" alt="{abbr}">'
            f'<div>'
            f'<div style="font-size:14px;color:#E5E9F0;font-weight:500;">{full_name}</div>'
            f'<div style="font-size:11px;color:#8B95A8;">L10 {w}-{l}</div>'
            f'</div>'
            f'</div>'
            f'{score}'
            f'</div>'
        )

    def _closing_line_html(game_id: str, home_abbr: str, away_abbr: str) -> str:
        """Return closing line spread + total as a strip, or empty string if no odds."""
        cl = closing_line_for_game(game_id, _mtime=mtime)
        if not cl:
            return ""
        parts = []
        if "spread" in cl:
            # cl["spread"] is for HOME team — convention
            parts.append(f'<span style="color:#8B95A8;">Closing</span> '
                          f'<span style="color:#E5E9F0;">{home_abbr} {cl["spread"]}</span>')
        if "total" in cl:
            parts.append(f'<span style="color:#8B95A8;">O/U</span> '
                          f'<span style="color:#E5E9F0;">{cl["total"]}</span>')
        if not parts:
            return ""
        return (
            f'<div style="margin-top:8px;padding:6px 10px;background:#0E1525;'
            f'border-radius:6px;font-size:11px;display:flex;gap:14px;">'
            + "  ·  ".join(parts) +
            f'</div>'
        )

    # Two-column grid via HTML
    rendered_rows = []
    for _, g in bucket.iterrows():
        meta_parts = [f"ET {g['game_date']}"]
        if g["season_type"] != "Regular":
            meta_parts.append(g["season_type"])
        meta_text = " · ".join(meta_parts)

        # Closing line shown only for upcoming games (not Final)
        closing_html = ""
        if g["status"] != "Final":
            closing_html = _closing_line_html(g["game_id"], g["home_abbr"], g["away_abbr"])

        # Named injury chips, one row per team
        away_inj_html = _named_injuries_html(int(g["away_team_id"]), g["away_abbr"])
        home_inj_html = _named_injuries_html(int(g["home_team_id"]), g["home_abbr"])

        card = (
            f'<div style="background:#172033;border-radius:12px;padding:14px 16px;'
            f'margin-bottom:12px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:12px;">'
            f'<span style="font-size:11px;color:#8B95A8;">{meta_text}</span>'
            f'{_status_pill(g["status"])}'
            f'</div>'
            f'{_team_row(g, "away")}'
            f'{_team_row(g, "home")}'
            f'{closing_html}'
            f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid #25304a;'
            f'display:flex;flex-direction:column;gap:6px;">'
            f'<div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">{away_inj_html}</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">{home_inj_html}</div>'
            f'</div>'
            f'</div>'
        )
        rendered_rows.append(card)

    # Render in 2-column grid using Streamlit columns (so each card stays within its column)
    cols = st.columns(2)
    for i, html in enumerate(rendered_rows):
        with cols[i % 2]:
            st.markdown(html, unsafe_allow_html=True)


# =========================================================================
# Landing widgets — Standings, Stat Leaders, Injury Watch, Latest News
# =========================================================================
from lib.branding import team_logo_url

st.markdown(
    '<p style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;'
    'color:#8B95A8;margin:1.75rem 0 10px;">League pulse</p>',
    unsafe_allow_html=True,
)

pulse_cols = st.columns(2)

# ---- East standings ----
def _standings_html(conf: str) -> str:
    df = conference_standings(conf, season_filter=season_filter, _mtime=mtime)
    if df.empty:
        return f'<div style="color:#8B95A8;">No data for {conf}.</div>'
    rows = []
    for _, r in df.head(15).iterrows():
        rank_color = "#F4A742" if r["rank"] <= 6 else ("#5FBE85" if r["rank"] <= 8 else "#8B95A8")
        rows.append(
            f'<div style="display:grid;grid-template-columns:24px 28px 1fr 60px 50px;'
            f'align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid #25304a;">'
            f'<span style="color:{rank_color};font-size:12px;font-weight:500;">{r["rank"]}</span>'
            f'<img src="{team_logo_url(int(r["team_id"]), 500)}" style="width:22px;height:22px;" alt="">'
            f'<span style="font-size:13px;color:#E5E9F0;">{r["abbreviation"]}</span>'
            f'<span style="font-size:12px;color:#E5E9F0;text-align:right;">{r["w"]}-{r["l"]}</span>'
            f'<span style="font-size:11px;color:#8B95A8;text-align:right;">{r["win_pct"]*100:.1f}%</span>'
            f'</div>'
        )
    return (
        f'<div style="background:#172033;border-radius:12px;padding:14px 16px;">'
        f'<div style="font-size:13px;color:#E5E9F0;font-weight:500;margin-bottom:8px;">{conf}ern Conference</div>'
        + "".join(rows) +
        f'</div>'
    )

with pulse_cols[0]:
    st.markdown(_standings_html("East"), unsafe_allow_html=True)
with pulse_cols[1]:
    st.markdown(_standings_html("West"), unsafe_allow_html=True)


# ---- Stat Leaders ----
st.markdown(
    '<p style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;'
    'color:#8B95A8;margin:1.5rem 0 10px;">Stat leaders · top 5 per category</p>',
    unsafe_allow_html=True,
)

def _leaders_html(stat: str, label: str, fmt: str = "num") -> str:
    df = stat_leaders(stat, season_filter=season_filter, min_games=5,
                       top_n=5, _mtime=mtime)
    if df.empty:
        return ''
    rows = []
    for i, r in df.iterrows():
        if fmt == "pct":
            v = f'{r["value"]*100:.1f}%'
        else:
            v = f'{r["value"]:.1f}'
        rows.append(
            f'<div style="display:grid;grid-template-columns:18px 22px 1fr 50px;'
            f'align-items:center;gap:6px;padding:3px 0;font-size:11px;">'
            f'<span style="color:#8B95A8;">{i+1}</span>'
            f'<img src="{team_logo_url(int(r["team_id"]), 500)}" style="width:18px;height:18px;" alt="">'
            f'<span style="color:#E5E9F0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{r["player_name"]}</span>'
            f'<span style="color:#F4A742;text-align:right;font-weight:500;">{v}</span>'
            f'</div>'
        )
    return (
        f'<div style="background:#172033;border-radius:12px;padding:12px 14px;'
        f'margin-bottom:12px;">'
        f'<div style="font-size:12px;color:#8B95A8;letter-spacing:0.05em;'
        f'text-transform:uppercase;margin-bottom:6px;">{label}</div>'
        + "".join(rows) +
        f'</div>'
    )

leaders_cols = st.columns(4)
LEADER_SPECS = [
    ("pts", "Points", "num"),
    ("ast", "Assists", "num"),
    ("reb", "Rebounds", "num"),
    ("stl", "Steals", "num"),
    ("blk", "Blocks", "num"),
    ("fg_pct", "FG%", "pct"),
    ("fg3_pct", "3PT%", "pct"),
    ("ft_pct", "FT%", "pct"),
]
for idx, (stat, label, fmt) in enumerate(LEADER_SPECS):
    with leaders_cols[idx % 4]:
        st.markdown(_leaders_html(stat, label, fmt), unsafe_allow_html=True)


# ---- League Injury Watch ----
st.markdown(
    '<p style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;'
    'color:#8B95A8;margin:1.5rem 0 10px;">League injury watch · highest-impact</p>',
    unsafe_allow_html=True,
)

inj_df = league_injuries_top(limit=12, _mtime=mtime)
if not inj_df.empty:
    chips = []
    for _, r in inj_df.iterrows():
        s_lower = (r["status"] or "").lower()
        if "out" in s_lower or "suspended" in s_lower:
            bg, color = "rgba(200,70,70,0.18)", "#E37070"
        elif "doubtful" in s_lower:
            bg, color = "rgba(244,167,66,0.20)", "#F4A742"
        else:
            bg, color = "rgba(244,167,66,0.15)", "#F4A742"
        chips.append(
            f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;">'
            f'<img src="{team_logo_url(int(r["team_id"]), 500)}" style="width:18px;height:18px;" alt="">'
            f'<span style="font-size:12px;color:#E5E9F0;flex:1;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;">{r["player_name"]}</span>'
            f'<span style="font-size:10px;padding:1px 6px;border-radius:4px;'
            f'background:{bg};color:{color};white-space:nowrap;">{r["status"]}</span>'
            f'</div>'
        )

    cards_per_col = (len(chips) + 1) // 2  # split into 2 columns
    left_html = "".join(chips[:cards_per_col])
    right_html = "".join(chips[cards_per_col:])

    inj_panel_html = (
        f'<div style="background:#172033;border-radius:12px;padding:12px 16px;">'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;">'
        f'<div>{left_html}</div>'
        f'<div>{right_html}</div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(inj_panel_html, unsafe_allow_html=True)
