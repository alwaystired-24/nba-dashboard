"""Apply custom CSS theme — fonts, hierarchy, layout polish.

Call inject_theme() once at the top of every page.
"""
from __future__ import annotations

import streamlit as st


_CSS = """
<style>
/* ============================================================
   FONT HIERARCHY — bumped one tier from defaults
============================================================ */

/* Body text */
.stApp, .stApp p, .stApp div, .stApp span, .stApp li {
  font-size: 15px;
  line-height: 1.55;
}

/* Subdued captions (st.caption) */
.stApp [data-testid="stCaptionContainer"],
.stApp .stCaption {
  font-size: 12px !important;
  color: #8B95A8 !important;
}

/* Page title (st.title) — bigger, more presence */
.stApp h1 {
  font-size: 36px !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em;
  margin-bottom: 0.5rem !important;
}

/* Section subheaders (st.subheader) */
.stApp h2 {
  font-size: 24px !important;
  font-weight: 500 !important;
  letter-spacing: -0.005em;
  margin-top: 1.25rem !important;
  margin-bottom: 0.75rem !important;
}

/* Smaller headers (st.markdown #### etc) */
.stApp h3 { font-size: 20px !important; font-weight: 500 !important; }
.stApp h4 { font-size: 17px !important; font-weight: 500 !important; }

/* ============================================================
   HORIZONTAL TOP NAV — replaces page sidebar nav
============================================================ */

/* Hide the default Streamlit page nav links in the sidebar */
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
  display: none !important;
}

/* Compact the sidebar — used only for filters now */
section[data-testid="stSidebar"] {
  width: auto !important;
}

/* ============================================================
   CARDS — slightly bigger numbers in metric cards (rendered HTML)
============================================================ */
.metric-card-value {
  font-size: 22px !important;
}

/* ============================================================
   DATAFRAMES — slightly more breathing room
============================================================ */
.stDataFrame {
  font-size: 13px;
}

/* Table header — uppercase tracked, like the other headers */
.stDataFrame thead th {
  font-size: 12px !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #8B95A8 !important;
  font-weight: 500 !important;
}

/* ============================================================
   PAGE PADDING — tighter so content gets more space
============================================================ */
.block-container {
  padding-top: 1.5rem !important;
  padding-bottom: 2rem !important;
  max-width: 1500px;
}
</style>
"""


_TOP_NAV_CSS_AND_HTML_TEMPLATE = """
<style>
.nba-topnav {{
  display: flex;
  gap: 4px;
  padding: 8px 0;
  margin-bottom: 12px;
  border-bottom: 1px solid #25304a;
  align-items: center;
}}
.nba-topnav a {{
  text-decoration: none;
  font-size: 14px;
  padding: 6px 14px;
  border-radius: 6px;
  color: #8B95A8;
  font-weight: 500;
  transition: background 120ms;
}}
.nba-topnav a:hover {{
  background: #172033;
  color: #E5E9F0;
}}
.nba-topnav a.active {{
  background: #F4A742;
  color: #0E1525;
}}
</style>
<div class="nba-topnav">
  <a href="/" target="_self" class="{home_active}">🏠 Home</a>
  <a href="/Today" target="_self" class="{today_active}">📅 Today</a>
  <a href="/Matchup" target="_self" class="{matchup_active}">🥊 Matchup</a>
  <a href="/Team_Stats" target="_self" class="{teamstats_active}">🏟️ Team Stats</a>
  <a href="/Player_Stats" target="_self" class="{playerstats_active}">🧍 Player Stats</a>
</div>
"""


def inject_theme(active_page: str = "home") -> None:
    """Inject the global CSS theme + horizontal top nav.

    Args:
        active_page: 'home' | 'today' | 'matchup' | 'teamstats' | 'playerstats'
    """
    st.markdown(_CSS, unsafe_allow_html=True)
    nav = _TOP_NAV_CSS_AND_HTML_TEMPLATE.format(
        home_active="active" if active_page == "home" else "",
        today_active="active" if active_page == "today" else "",
        matchup_active="active" if active_page == "matchup" else "",
        teamstats_active="active" if active_page == "teamstats" else "",
        playerstats_active="active" if active_page == "playerstats" else "",
    )
    st.markdown(nav, unsafe_allow_html=True)
