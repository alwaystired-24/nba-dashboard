"""Pull data from nba_api and write it into the SQLite store.

Phase 1 covers:
  - teams       (one-shot, static)
  - schedule    (games table; one row per game)
  - team box    (traditional + advanced)
  - player box  (traditional + advanced)
  - players     (derived from box score appearances)
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from typing import Any

from nba_api.stats.endpoints import (
    boxscoreadvancedv2,
    boxscoretraditionalv2,
    leaguegamefinder,
)
from nba_api.stats.static import teams as static_teams

from .db import connect, record_etl, upsert
from .nba import SEASON_TYPES, call_with_retry, current_season

logger = logging.getLogger(__name__)

# =========================================================================
# TEAMS — one-shot, runs at init
# =========================================================================

def seed_teams(conn: sqlite3.Connection) -> int:
    """Populate the 30 NBA teams from the static module (no network needed)."""
    rows = []
    for t in static_teams.get_teams():
        rows.append({
            "team_id": t["id"],
            "abbreviation": t["abbreviation"],
            "full_name": t["full_name"],
            "nickname": t["nickname"],
            "city": t["city"],
            # conference/division aren't in the static list — fill in later via roster endpoint if needed
            "conference": None,
            "division": None,
        })
    return upsert(conn, "teams", rows, pk=["team_id"])


# =========================================================================
# SCHEDULE — one row per game
# =========================================================================

def _parse_matchup(matchup: str) -> tuple[bool, str]:
    """LeagueGameFinder MATCHUP looks like 'LAL vs. BOS' (home) or 'LAL @ BOS' (away)."""
    is_home = " vs. " in matchup
    parts = matchup.split(" vs. ") if is_home else matchup.split(" @ ")
    opponent = parts[1].strip() if len(parts) == 2 else ""
    return is_home, opponent


def _abbr_to_team_id(conn: sqlite3.Connection, abbr: str) -> int | None:
    row = conn.execute("SELECT team_id FROM teams WHERE abbreviation = ?", (abbr,)).fetchone()
    return row["team_id"] if row else None


def _season_type_to_label(season_type_api: str) -> str:
    return {
        "Regular Season": "Regular",
        "Playoffs": "Playoffs",
        "PlayIn": "PlayIn",
        "Pre Season": "PreSeason",
    }.get(season_type_api, season_type_api)


def fetch_schedule_for_season(season: str, season_type: str) -> list[dict]:
    """Use LeagueGameFinder to grab all games for a season+type.

    Returns the raw `LeagueGameFinderResults` rows as dicts. Each completed
    game shows up as TWO rows (one per team), which we collapse into one
    `games` row downstream.
    """
    finder = call_with_retry(
        leaguegamefinder.LeagueGameFinder,
        season_nullable=season,
        season_type_nullable=season_type,
        league_id_nullable="00",  # NBA
    )
    df = finder.get_data_frames()[0]
    return df.to_dict("records")


def ingest_schedule(conn: sqlite3.Connection, season: str | None = None) -> int:
    """Pull current-season schedule across all season types and upsert games table."""
    season = season or current_season()
    by_game: dict[str, dict[str, Any]] = {}

    for st in SEASON_TYPES:
        try:
            raw = fetch_schedule_for_season(season, st)
        except Exception as exc:
            logger.warning("Schedule fetch failed for %s %s: %s", season, st, exc)
            continue
        for r in raw:
            gid = str(r["GAME_ID"])
            is_home, opp_abbr = _parse_matchup(r["MATCHUP"])
            team_id = int(r["TEAM_ID"])
            opp_id = _abbr_to_team_id(conn, opp_abbr)
            if opp_id is None:
                continue  # rare: G-League or All-Star noise

            entry = by_game.setdefault(gid, {
                "game_id": gid,
                "season": season,
                "season_type": _season_type_to_label(st),
                "game_date": r["GAME_DATE"],   # already YYYY-MM-DD
                "game_datetime_et": None,
                "home_team_id": None,
                "away_team_id": None,
                "home_score": None,
                "away_score": None,
                "status": "Final" if r.get("WL") in ("W", "L") else "Scheduled",
                "arena": None,
                "attendance": None,
            })
            pts = r.get("PTS")
            pts = int(pts) if pts is not None and not _is_nan(pts) else None
            if is_home:
                entry["home_team_id"] = team_id
                entry["home_score"] = pts
            else:
                entry["away_team_id"] = team_id
                entry["away_score"] = pts

    rows = [g for g in by_game.values()
            if g["home_team_id"] is not None and g["away_team_id"] is not None]
    return upsert(conn, "games", rows, pk=["game_id"])


def _is_nan(x: Any) -> bool:
    try:
        import math
        return isinstance(x, float) and math.isnan(x)
    except Exception:
        return False


# =========================================================================
# BOX SCORES — traditional + advanced, team + player
# =========================================================================

def _min_to_float(min_str: Any) -> float | None:
    """nba_api V2 returns minutes as 'MM:SS' string OR plain int OR None."""
    if min_str is None or min_str == "":
        return None
    if isinstance(min_str, (int, float)):
        return float(min_str)
    s = str(min_str)
    if ":" in s:
        try:
            m, sec = s.split(":")
            return int(m) + int(sec) / 60.0
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(x: Any) -> int | None:
    if x is None or _is_nan(x) or x == "":
        return None
    try:
        return int(x)
    except (ValueError, TypeError):
        return None


def _safe_float(x: Any) -> float | None:
    if x is None or _is_nan(x) or x == "":
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


# ---- Traditional box score ----------------------------------------------

def fetch_traditional_box(game_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (team_rows, player_rows, player_seen) tuples for the games's traditional box."""
    bs = call_with_retry(boxscoretraditionalv2.BoxScoreTraditionalV2, game_id=game_id)
    team_df, player_df = bs.team_stats.get_data_frame(), bs.player_stats.get_data_frame()

    # Determine home team for is_home flag — fall back to first row if needed
    # (the LineScore endpoint is more authoritative but we can fetch home_team_id from games table later)
    team_rows: list[dict] = []
    for _, r in team_df.iterrows():
        team_rows.append({
            "game_id": str(r["GAME_ID"]),
            "team_id": int(r["TEAM_ID"]),
            "is_home": 0,  # corrected by post-process below
            "minutes": _min_to_float(r.get("MIN")),
            "fgm": _safe_int(r.get("FGM")), "fga": _safe_int(r.get("FGA")),
            "fg_pct": _safe_float(r.get("FG_PCT")),
            "fg3m": _safe_int(r.get("FG3M")), "fg3a": _safe_int(r.get("FG3A")),
            "fg3_pct": _safe_float(r.get("FG3_PCT")),
            "ftm": _safe_int(r.get("FTM")), "fta": _safe_int(r.get("FTA")),
            "ft_pct": _safe_float(r.get("FT_PCT")),
            "oreb": _safe_int(r.get("OREB")), "dreb": _safe_int(r.get("DREB")),
            "reb": _safe_int(r.get("REB")),
            "ast": _safe_int(r.get("AST")), "stl": _safe_int(r.get("STL")),
            "blk": _safe_int(r.get("BLK")),
            "tov": _safe_int(r.get("TO")), "pf": _safe_int(r.get("PF")),
            "pts": _safe_int(r.get("PTS")),
            "plus_minus": _safe_int(r.get("PLUS_MINUS")),
        })

    player_rows: list[dict] = []
    seen_players: list[dict] = []
    today_iso = date.today().isoformat()
    for _, r in player_df.iterrows():
        pid = int(r["PLAYER_ID"])
        seen_players.append({
            "player_id": pid,
            "full_name": r.get("PLAYER_NAME"),
            "first_name": None,
            "last_name": None,
            "is_active": 1,
            "last_seen_date": today_iso,
        })
        start_pos = r.get("START_POSITION")
        is_starter = 1 if (start_pos is not None and str(start_pos).strip() != "") else 0
        player_rows.append({
            "game_id": str(r["GAME_ID"]),
            "player_id": pid,
            "team_id": int(r["TEAM_ID"]),
            "is_starter": is_starter,
            "minutes": _min_to_float(r.get("MIN")),
            "fgm": _safe_int(r.get("FGM")), "fga": _safe_int(r.get("FGA")),
            "fg_pct": _safe_float(r.get("FG_PCT")),
            "fg3m": _safe_int(r.get("FG3M")), "fg3a": _safe_int(r.get("FG3A")),
            "fg3_pct": _safe_float(r.get("FG3_PCT")),
            "ftm": _safe_int(r.get("FTM")), "fta": _safe_int(r.get("FTA")),
            "ft_pct": _safe_float(r.get("FT_PCT")),
            "oreb": _safe_int(r.get("OREB")), "dreb": _safe_int(r.get("DREB")),
            "reb": _safe_int(r.get("REB")),
            "ast": _safe_int(r.get("AST")), "stl": _safe_int(r.get("STL")),
            "blk": _safe_int(r.get("BLK")),
            "tov": _safe_int(r.get("TO")), "pf": _safe_int(r.get("PF")),
            "pts": _safe_int(r.get("PTS")),
            "plus_minus": _safe_int(r.get("PLUS_MINUS")),
        })

    return team_rows, player_rows, seen_players


def ingest_traditional_box(conn: sqlite3.Connection, game_id: str) -> bool:
    try:
        team_rows, player_rows, seen = fetch_traditional_box(game_id)
        # Look up home team from games and set is_home flag
        g = conn.execute("SELECT home_team_id FROM games WHERE game_id = ?", (game_id,)).fetchone()
        if g and g["home_team_id"]:
            for tr in team_rows:
                tr["is_home"] = 1 if tr["team_id"] == g["home_team_id"] else 0
        upsert(conn, "players", seen, pk=["player_id"])
        upsert(conn, "team_box_traditional", team_rows, pk=["game_id", "team_id"])
        upsert(conn, "player_box_traditional", player_rows, pk=["game_id", "player_id"])
        record_etl(conn, game_id, "team_box_traditional", "success")
        record_etl(conn, game_id, "player_box_traditional", "success")
        return True
    except Exception as exc:
        logger.exception("traditional box failed for %s", game_id)
        record_etl(conn, game_id, "team_box_traditional", "failed", str(exc))
        record_etl(conn, game_id, "player_box_traditional", "failed", str(exc))
        return False


# ---- Advanced box score -------------------------------------------------

def fetch_advanced_box(game_id: str) -> tuple[list[dict], list[dict]]:
    bs = call_with_retry(boxscoreadvancedv2.BoxScoreAdvancedV2, game_id=game_id)
    team_df = bs.team_stats.get_data_frame()
    player_df = bs.player_stats.get_data_frame()

    def _team_row(r: dict) -> dict:
        return {
            "game_id": str(r["GAME_ID"]),
            "team_id": int(r["TEAM_ID"]),
            "minutes": _min_to_float(r.get("MIN")),
            "off_rating": _safe_float(r.get("OFF_RATING")),
            "def_rating": _safe_float(r.get("DEF_RATING")),
            "net_rating": _safe_float(r.get("NET_RATING")),
            "pace": _safe_float(r.get("PACE")),
            "pie": _safe_float(r.get("PIE")),
            "ast_pct": _safe_float(r.get("AST_PCT")),
            "ast_to_tov": _safe_float(r.get("AST_TOV")),
            "ast_ratio": _safe_float(r.get("AST_RATIO")),
            "oreb_pct": _safe_float(r.get("OREB_PCT")),
            "dreb_pct": _safe_float(r.get("DREB_PCT")),
            "reb_pct": _safe_float(r.get("REB_PCT")),
            "tov_pct": _safe_float(r.get("TM_TOV_PCT") or r.get("TOV_PCT")),
            "efg_pct": _safe_float(r.get("EFG_PCT")),
            "ts_pct": _safe_float(r.get("TS_PCT")),
            "poss": _safe_float(r.get("POSS")),
        }

    def _player_row(r: dict) -> dict:
        return {
            "game_id": str(r["GAME_ID"]),
            "player_id": int(r["PLAYER_ID"]),
            "team_id": int(r["TEAM_ID"]),
            "minutes": _min_to_float(r.get("MIN")),
            "off_rating": _safe_float(r.get("OFF_RATING")),
            "def_rating": _safe_float(r.get("DEF_RATING")),
            "net_rating": _safe_float(r.get("NET_RATING")),
            "usg_pct": _safe_float(r.get("USG_PCT")),
            "pie": _safe_float(r.get("PIE")),
            "ast_pct": _safe_float(r.get("AST_PCT")),
            "ast_to_tov": _safe_float(r.get("AST_TOV")),
            "ast_ratio": _safe_float(r.get("AST_RATIO")),
            "oreb_pct": _safe_float(r.get("OREB_PCT")),
            "dreb_pct": _safe_float(r.get("DREB_PCT")),
            "reb_pct": _safe_float(r.get("REB_PCT")),
            "tov_pct": _safe_float(r.get("TO_PCT") or r.get("TOV_PCT")),
            "efg_pct": _safe_float(r.get("EFG_PCT")),
            "ts_pct": _safe_float(r.get("TS_PCT")),
            "pace": _safe_float(r.get("PACE")),
            "poss": _safe_float(r.get("POSS")),
        }

    return [_team_row(r) for _, r in team_df.iterrows()], \
           [_player_row(r) for _, r in player_df.iterrows()]


def ingest_advanced_box(conn: sqlite3.Connection, game_id: str) -> bool:
    try:
        team_rows, player_rows = fetch_advanced_box(game_id)
        upsert(conn, "team_box_advanced", team_rows, pk=["game_id", "team_id"])
        upsert(conn, "player_box_advanced", player_rows, pk=["game_id", "player_id"])
        record_etl(conn, game_id, "team_box_advanced", "success")
        record_etl(conn, game_id, "player_box_advanced", "success")
        return True
    except Exception as exc:
        logger.exception("advanced box failed for %s", game_id)
        record_etl(conn, game_id, "team_box_advanced", "failed", str(exc))
        record_etl(conn, game_id, "player_box_advanced", "failed", str(exc))
        return False


# =========================================================================
# DRIVERS
# =========================================================================

def list_unprocessed_games(conn: sqlite3.Connection) -> list[str]:
    """Game IDs that don't have a successful traditional box yet (only Final games)."""
    rows = conn.execute(
        """
        SELECT g.game_id FROM games g
        LEFT JOIN etl_runs e
          ON e.game_id = g.game_id
         AND e.endpoint = 'team_box_traditional'
         AND e.status = 'success'
        WHERE g.status = 'Final' AND e.game_id IS NULL
        ORDER BY g.game_date
        """
    ).fetchall()
    return [r["game_id"] for r in rows]
