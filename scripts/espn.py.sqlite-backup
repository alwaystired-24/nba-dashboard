"""ESPN API integration — injuries + team news.

ESPN exposes an unofficial JSON API at site.api.espn.com.
Endpoints used:
  - /apis/site/v2/sports/basketball/nba/teams/{abbr}/injuries
  - /apis/site/v2/sports/basketball/nba/news?team={espn_team_id}

Note: ESPN's NBA team IDs differ from NBA's stats.nba.com IDs. We maintain
a static mapping below (only changes when an NBA team relocates / rebrands).
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"

# Map: nba_api team_id -> (lowercase abbr ESPN uses, ESPN numeric team id)
# ESPN abbr is sometimes different from nba_api (e.g., NJN/BKN historical).
# Verified May 2026.
NBA_TEAM_TO_ESPN = {
    1610612737: ("atl", 1),    # Atlanta Hawks
    1610612738: ("bos", 2),    # Boston Celtics
    1610612739: ("cle", 5),    # Cleveland Cavaliers
    1610612740: ("no",  3),    # New Orleans Pelicans
    1610612741: ("chi", 4),    # Chicago Bulls
    1610612742: ("dal", 6),    # Dallas Mavericks
    1610612743: ("den", 7),    # Denver Nuggets
    1610612744: ("gs",  9),    # Golden State Warriors
    1610612745: ("hou", 10),   # Houston Rockets
    1610612746: ("lac", 12),   # Los Angeles Clippers
    1610612747: ("lal", 13),   # Los Angeles Lakers
    1610612748: ("mia", 14),   # Miami Heat
    1610612749: ("mil", 15),   # Milwaukee Bucks
    1610612750: ("min", 16),   # Minnesota Timberwolves
    1610612751: ("bkn", 17),   # Brooklyn Nets
    1610612752: ("ny",  18),   # New York Knicks
    1610612753: ("orl", 19),   # Orlando Magic
    1610612754: ("ind", 11),   # Indiana Pacers
    1610612755: ("phi", 20),   # Philadelphia 76ers
    1610612756: ("phx", 21),   # Phoenix Suns
    1610612757: ("por", 22),   # Portland Trail Blazers
    1610612758: ("sac", 23),   # Sacramento Kings
    1610612759: ("sa",  24),   # San Antonio Spurs
    1610612760: ("okc", 25),   # Oklahoma City Thunder
    1610612761: ("tor", 28),   # Toronto Raptors
    1610612762: ("utah", 26),  # Utah Jazz
    1610612763: ("mem", 29),   # Memphis Grizzlies
    1610612764: ("wsh", 27),   # Washington Wizards
    1610612765: ("det", 8),    # Detroit Pistons
    1610612766: ("cha", 30),   # Charlotte Hornets
}

REQUEST_TIMEOUT = 15
RETRY_DELAYS = [1, 3, 8]  # exponential backoff


def _http_get_json(url: str, params: dict | None = None) -> dict | None:
    """GET with retry. Returns None on definitive failure (caller handles)."""
    last_err = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS, 1):
        if delay:
            time.sleep(delay)
        try:
            r = requests.get(url, params=params or {}, timeout=REQUEST_TIMEOUT,
                             headers={"User-Agent": "nba-dashboard/1.0"})
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 403):
                logger.warning("ESPN %d for %s — skipping", r.status_code, url)
                return None
            logger.warning("ESPN HTTP %d (attempt %d/%d): %s",
                            r.status_code, attempt, len(RETRY_DELAYS) + 1, url)
            last_err = f"HTTP {r.status_code}"
        except Exception as exc:
            logger.warning("ESPN error (attempt %d/%d): %s", attempt, len(RETRY_DELAYS) + 1, exc)
            last_err = str(exc)
    logger.error("ESPN gave up on %s after retries: %s", url, last_err)
    return None


# =========================================================================
# INJURIES — uses LEAGUE-WIDE endpoint (one call returns all teams)
# =========================================================================

# ESPN team_id -> nba_api team_id (reverse map for quick lookup)
ESPN_TO_NBA = {espn_id: nba_id for nba_id, (_, espn_id) in NBA_TEAM_TO_ESPN.items()}


def fetch_all_injuries(conn: sqlite3.Connection) -> dict:
    """Fetch league-wide injuries with ONE API call. Replace contents of injuries table.

    Endpoint: /apis/site/v2/sports/basketball/nba/injuries
    Returns nested: { injuries: [ { id (espn_team_id), displayName, injuries: [...] } ] }
    """
    fetched_utc = datetime.now(timezone.utc).isoformat()
    url = f"{ESPN_BASE}/injuries"
    data = _http_get_json(url)

    if not data or "injuries" not in data:
        logger.warning("League injuries endpoint returned no data")
        return {
            "teams_fetched": 0,
            "teams_failed": 30,
            "total_injuries": 0,
            "fetched_utc": fetched_utc,
        }

    all_rows = []
    teams_fetched = 0
    teams_failed = 0

    for team_block in data.get("injuries", []):
        # Top-level entry per team. id is the ESPN team_id (string).
        try:
            espn_team_id = int(team_block.get("id", 0))
        except (ValueError, TypeError):
            continue

        nba_team_id = ESPN_TO_NBA.get(espn_team_id)
        if nba_team_id is None:
            # Probably a non-NBA entity (rare)
            continue

        teams_fetched += 1

        for inj in team_block.get("injuries", []):
            athlete = inj.get("athlete") or {}

            # Status normalization — ESPN uses 'Out', 'Day-To-Day', 'Doubtful', etc.
            status = inj.get("status") or "Unknown"

            # Detail: prefer shortComment over longComment for compact display
            detail = (inj.get("shortComment") or
                       inj.get("longComment") or
                       (inj.get("details") or {}).get("type"))
            # Trim very long details to keep table compact
            if detail and len(detail) > 250:
                detail = detail[:247] + "..."

            return_date = (
                (inj.get("details") or {}).get("returnDate") or
                inj.get("date")
            )
            # Strip time portion if present
            if return_date:
                return_date = return_date[:10]

            all_rows.append({
                "team_id": nba_team_id,
                "player_id": _safe_int(athlete.get("id")),
                "player_name": athlete.get("displayName") or "Unknown",
                "status": status,
                "detail": detail,
                "return_date": return_date,
                "fetched_utc": fetched_utc,
            })

    # Replace contents
    conn.execute("DELETE FROM injuries")
    if all_rows:
        conn.executemany(
            """
            INSERT INTO injuries
            (team_id, player_id, player_name, status, detail, return_date, fetched_utc)
            VALUES (:team_id, :player_id, :player_name, :status, :detail,
                    :return_date, :fetched_utc)
            ON CONFLICT(team_id, player_name) DO UPDATE SET
                player_id = excluded.player_id,
                status = excluded.status,
                detail = excluded.detail,
                return_date = excluded.return_date,
                fetched_utc = excluded.fetched_utc
            """,
            all_rows,
        )
    conn.commit()

    return {
        "teams_fetched": teams_fetched,
        "teams_failed": 30 - teams_fetched,
        "total_injuries": len(all_rows),
        "fetched_utc": fetched_utc,
    }


# =========================================================================
# TEAM NEWS
# =========================================================================

def fetch_news_for_team(espn_team_id: int, limit: int = 10) -> list[dict]:
    """Return a list of news article dicts for one team from ESPN.

    Each dict has: article_id, headline, summary, category, published_utc, url.
    """
    url = f"{ESPN_BASE}/news"
    data = _http_get_json(url, params={"team": espn_team_id, "limit": limit})
    if not data:
        return []

    out = []
    for art in data.get("articles", []):
        # Find the canonical URL — ESPN nests it under links.web.href
        links = art.get("links") or {}
        web_link = (links.get("web") or {}).get("href")

        out.append({
            "article_id": str(art.get("id") or art.get("dataSourceIdentifier") or ""),
            "headline": art.get("headline") or "",
            "summary": art.get("description") or art.get("subhead"),
            "category": _classify_category(art),
            "published_utc": art.get("published") or art.get("lastModified"),
            "url": web_link,
        })
    return out


def _classify_category(article: dict) -> str | None:
    """Best-effort categorization based on headline/keywords."""
    text = ((article.get("headline") or "") + " " +
             (article.get("description") or "")).lower()
    if "trade" in text or "traded" in text or "deal" in text:
        return "Trade"
    if "injur" in text or "out" in text or "doubtful" in text or "questionable" in text:
        return "Injury"
    if "fire" in text or "hire" in text or "coach" in text:
        return "Coaching"
    if "suspen" in text:
        return "Suspension"
    if "sign" in text or "agree" in text or "extension" in text:
        return "Contract"
    return None


def fetch_all_news(conn: sqlite3.Connection, limit_per_team: int = 10) -> dict:
    """Fetch news for all 30 NBA teams. Upsert into team_news table.

    Returns {teams_fetched, total_articles}.
    """
    fetched_utc = datetime.now(timezone.utc).isoformat()
    all_rows = []
    teams_fetched = 0
    teams_failed = 0

    for team_id, (_abbr, espn_id) in NBA_TEAM_TO_ESPN.items():
        try:
            articles = fetch_news_for_team(espn_id, limit=limit_per_team)
            for art in articles:
                if not art["article_id"]:
                    continue  # skip articles without ID — can't dedup
                all_rows.append({
                    "article_id": art["article_id"],
                    "team_id": team_id,
                    "headline": art["headline"],
                    "summary": art["summary"],
                    "category": art["category"],
                    "published_utc": art["published_utc"],
                    "url": art["url"],
                    "fetched_utc": fetched_utc,
                })
            teams_fetched += 1
        except Exception as exc:
            logger.warning("News fetch failed for team %d: %s", team_id, exc)
            teams_failed += 1

    # Upsert (don't delete — we want to accumulate news history if articles change)
    if all_rows:
        conn.executemany(
            """
            INSERT INTO team_news
            (article_id, team_id, headline, summary, category, published_utc, url, fetched_utc)
            VALUES (:article_id, :team_id, :headline, :summary, :category,
                    :published_utc, :url, :fetched_utc)
            ON CONFLICT(article_id, team_id) DO UPDATE SET
                headline = excluded.headline,
                summary = excluded.summary,
                category = excluded.category,
                published_utc = excluded.published_utc,
                url = excluded.url,
                fetched_utc = excluded.fetched_utc
            """,
            all_rows,
        )

    # Prune articles older than 30 days to keep table small
    conn.execute(
        "DELETE FROM team_news WHERE date(published_utc) < date('now', '-30 days')"
    )
    conn.commit()

    return {
        "teams_fetched": teams_fetched,
        "teams_failed": teams_failed,
        "total_articles": len(all_rows),
        "fetched_utc": fetched_utc,
    }


# =========================================================================
# COMBINED FETCH (called from scripts.run)
# =========================================================================

def ensure_espn_schema(conn: sqlite3.Connection) -> None:
    """Apply migration 003 if not already applied."""
    has_injuries = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='injuries'"
    ).fetchone()
    has_news = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='team_news'"
    ).fetchone()
    if has_injuries and has_news:
        return

    from pathlib import Path
    sql_path = Path(__file__).resolve().parent.parent / "sql" / "migrations" / "003_injuries_and_news.sql"
    if sql_path.exists():
        conn.executescript(sql_path.read_text())
        conn.commit()


def run_espn_fetch(conn: sqlite3.Connection) -> dict:
    """Fetch injuries + news for all 30 teams. Called from `daily` and the
    odds workflow's espn step."""
    ensure_espn_schema(conn)
    inj = fetch_all_injuries(conn)
    news = fetch_all_news(conn)
    return {"injuries": inj, "news": news}


# Helper
def _safe_int(x: Any) -> int | None:
    try:
        return int(x) if x is not None else None
    except (ValueError, TypeError):
        return None
