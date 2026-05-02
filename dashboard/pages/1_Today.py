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
st.title("📅 Today & Upcoming")

mtime = db_mtime()
show_freshness_banner(mtime)

season_filter = season_filter_picker()
st.caption(f"Showing **{SEASON_FILTER_LABELS[season_filter]}** form previews. "
            "Change at top of any page.")

injury_counts = all_team_injury_counts(_mtime=mtime)
tlookup = team_lookup(_mtime=mtime)

# --- Range we want: yesterday, today, tomorrow, +5 more ----------------
today = date.fromisoformat(hkt_today())
hkt_window_start = today - timedelta(days=1)
hkt_window_end = today + timedelta(days=7)
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
    if 2 <= delta <= 7:
        return hkt.strftime("%a %d %b")
    return hkt.isoformat()

games = games.assign(hkt_label=games["game_date"].apply(_hkt_label))

# --- Section per HKT bucket --------------------------------------------
ordering = ["Yesterday", "Today", "Tomorrow"]
seen_labels: list[str] = []
for lbl in ordering:
    sub = games[games["hkt_label"] == lbl]
    if not sub.empty:
        seen_labels.append(lbl)
# Then add the rest in date order
other = sorted(
    {l for l in games["hkt_label"].unique() if l not in ordering},
    key=lambda l: games[games["hkt_label"] == l]["game_date"].min(),
)
seen_labels.extend(other)

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

    def _injury_pill(team_abbr: str, count: int) -> str:
        if count == 0:
            bg, color, icon = "rgba(62,168,102,0.18)", "#5FBE85", "✓"
        elif count >= 3:
            bg, color, icon = "rgba(200,70,70,0.22)", "#E37070", "⚠"
        else:
            bg, color, icon = "rgba(244,167,66,0.20)", "#F4A742", "⚠"
        return (
            f'<span style="padding:2px 7px;border-radius:4px;background:{bg};'
            f'color:{color};font-size:11px;">{icon} {team_abbr}: {count}</span>'
        )

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

        # Right-side info: score for Final, dash for upcoming
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

    # Two-column grid via HTML
    rendered_rows = []
    for _, g in bucket.iterrows():
        away_inj = injury_counts.get(int(g["away_team_id"]), 0)
        home_inj = injury_counts.get(int(g["home_team_id"]), 0)
        meta_parts = []
        if g["season_type"] != "Regular":
            meta_parts.append(g["season_type"])
        meta_parts.append(f"ET {g['game_date']}")
        meta_text = " · ".join(meta_parts)

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
            f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid #25304a;'
            f'display:flex;gap:6px;align-items:center;">'
            f'{_injury_pill(g["away_abbr"], away_inj)}'
            f'{_injury_pill(g["home_abbr"], home_inj)}'
            f'</div>'
            f'</div>'
        )
        rendered_rows.append(card)

    # Render in 2-column grid using Streamlit columns (so each card stays within its column)
    cols = st.columns(2)
    for i, html in enumerate(rendered_rows):
        with cols[i % 2]:
            st.markdown(html, unsafe_allow_html=True)
