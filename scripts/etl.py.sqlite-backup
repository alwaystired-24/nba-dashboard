"""Pull data from nba_api and write it into the SQLite store.

Phase 1 covers:
  - teams       (one-shot, static)
  - schedule    (games table; one row per game)
  - team box    (traditional + advanced)
  - player box  (traditional + advanced)
  - players     (derived from box score appearances)

NOTE: Uses V3 endpoints because NBA deprecated V2 in 2024.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from typing import Any

from nba_api.stats.endpoints import (
    boxscoreadvancedv3,
    boxscoretraditionalv3,
    commonplayerinfo,
    leaguegamefinder,
)
from nba_api.stats.static import teams as static_teams

from .db import record_etl, upsert
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
    finder = call_with_retry(
        leaguegamefinder.LeagueGameFinder,
        season_nullable=season,
        season_type_nullable=season_type,
        league_id_nullable="00",
    )
    df = finder.get_data_frames()[0]
    return df.to_dict("records")


def fetch_full_schedule(season: str) -> list[dict]:
    """Use ScheduleLeagueV2 to get the full season schedule INCLUDING future games.

    LeagueGameFinder only returns played games — this is the complement.
    """
    from nba_api.stats.endpoints import scheduleleaguev2
    sched = call_with_retry(scheduleleaguev2.ScheduleLeagueV2, season=season)
    df = sched.season_games.get_data_frame()
    return df.to_dict("records")


def _gamestatus_to_label(status: int) -> str:
    """ScheduleLeagueV2 gameStatus: 1=Scheduled, 2=Live, 3=Final."""
    return {1: "Scheduled", 2: "Live", 3: "Final"}.get(int(status), "Scheduled")


def ingest_schedule(conn: sqlite3.Connection, season: str | None = None) -> int:
    """Ingest both played AND future games. Combines two endpoints:

    1. ScheduleLeagueV2 — full season including future games + game times
    2. LeagueGameFinder — final scores for completed games (more reliable for scores)
    """
    season = season or current_season()
    by_game: dict[str, dict[str, Any]] = {}

    # ---- Step 1: Pull the full season schedule from ScheduleLeagueV2 ----
    try:
        full = fetch_full_schedule(season)
        for r in full:
            gid = str(r.get("gameId") or "").strip()
            if not gid:
                continue
            home_id = _safe_int(r.get("homeTeam_teamId"))
            away_id = _safe_int(r.get("awayTeam_teamId"))
            if not home_id or not away_id:
                continue

            game_dt_et = r.get("gameDateTimeEst")  # ISO datetime in ET
            game_date = (str(r.get("gameDateEst") or "")[:10]) or None
            if not game_date and game_dt_et:
                game_date = str(game_dt_et)[:10]

            # Determine season_type from game_id prefix (most reliable)
            # NBA game_id format: 002SSXXXXX (preseason), 0022SSXXXXX (regular),
            #   0042SSXXXXX (playoffs), 0052SSXXXXX (play-in), 0012SSXXXXX (preseason)
            # Where SS = season year, XXXXX = sequential
            season_type = None
            if gid and len(gid) >= 4:
                prefix = gid[:4]
                if prefix == "0042":
                    season_type = "Playoffs"
                elif prefix == "0052":
                    season_type = "PlayIn"
                elif prefix == "0012":
                    season_type = "PreSeason"
                elif prefix == "0022":
                    season_type = "Regular"
                # Older preseason formats
                elif gid.startswith("001"):
                    season_type = "PreSeason"

            # Fallback to gameLabel if game_id prefix didn't tell us
            if not season_type:
                label = (r.get("gameLabel") or "").strip().lower()
                if "play-in" in label or "playin" in label:
                    season_type = "PlayIn"
                elif "playoff" in label or label.startswith("round") or "finals" in label:
                    season_type = "Playoffs"
                elif "preseason" in label or "pre season" in label:
                    season_type = "PreSeason"
                else:
                    season_type = "Regular"

            home_score = _safe_int(r.get("homeTeam_score"))
            away_score = _safe_int(r.get("awayTeam_score"))
            status = _gamestatus_to_label(r.get("gameStatus") or 1)
            # ScheduleLeagueV2 sometimes shows 0-0 for unplayed games
            if status != "Final" and home_score == 0 and away_score == 0:
                home_score = None
                away_score = None

            by_game[gid] = {
                "game_id": gid,
                "season": season,
                "season_type": season_type,
                "game_date": game_date,
                "game_datetime_et": game_dt_et,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "home_score": home_score,
                "away_score": away_score,
                "status": status,
                "arena": r.get("arenaName"),
                "attendance": None,
            }
    except Exception as exc:
        logger.warning("Full schedule fetch failed: %s", exc)

    # ---- Step 2: Overlay LeagueGameFinder results for played games ----
    # LeagueGameFinder is more authoritative for final scores
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
                continue

            # Determine season_type from game_id prefix (most reliable)
            # 0022=Regular, 0042=Playoffs, 0052=PlayIn, 0012/001=PreSeason
            entry_season_type = _season_type_to_label(st)  # fallback from loop var
            if gid and len(gid) >= 4:
                pfx = gid[:4]
                if pfx == "0042":
                    entry_season_type = "Playoffs"
                elif pfx == "0052":
                    entry_season_type = "PlayIn"
                elif pfx == "0022":
                    entry_season_type = "Regular"
                elif pfx == "0012" or gid.startswith("001"):
                    entry_season_type = "PreSeason"

            entry = by_game.setdefault(gid, {
                "game_id": gid,
                "season": season,
                "season_type": entry_season_type,
                "game_date": r["GAME_DATE"],
                "game_datetime_et": None,
                "home_team_id": None,
                "away_team_id": None,
                "home_score": None,
                "away_score": None,
                "status": "Final" if r.get("WL") in ("W", "L") else "Scheduled",
                "arena": None,
                "attendance": None,
            })
            # ALWAYS overwrite season_type if game_id prefix gives us better info
            # (handles case where Step 1 set it wrong, or Step 2 found it under wrong loop iteration)
            if gid and len(gid) >= 4 and gid[:4] in ("0042", "0052", "0022", "0012"):
                entry["season_type"] = entry_season_type
            # Don't overwrite with worse data — only fill in if missing
            if entry.get("home_team_id") is None:
                if is_home:
                    entry["home_team_id"] = team_id
                else:
                    entry["away_team_id"] = team_id
            # But always update score for played games (more reliable here)
            pts = r.get("PTS")
            pts = int(pts) if pts is not None and not _is_nan(pts) else None
            if pts is not None:
                if is_home:
                    entry["home_score"] = pts
                else:
                    entry["away_score"] = pts
                # If we have scores from LeagueGameFinder, this game is Final
                if r.get("WL") in ("W", "L"):
                    entry["status"] = "Final"

    # Only keep games where both teams exist in our teams table
    # (skips G League, international, all-star, or other non-NBA games)
    valid_team_ids = {row[0] for row in conn.execute("SELECT team_id FROM teams")}

    rows = [g for g in by_game.values()
            if g["home_team_id"] is not None and g["away_team_id"] is not None
            and g["home_team_id"] in valid_team_ids
            and g["away_team_id"] in valid_team_ids]

    skipped = len(by_game) - len(rows)
    if skipped > 0:
        logger.info("Skipped %d games with non-NBA team IDs", skipped)

    return upsert(conn, "games", rows, pk=["game_id"])


def _is_nan(x: Any) -> bool:
    try:
        import math
        return isinstance(x, float) and math.isnan(x)
    except Exception:
        return False


# =========================================================================
# BOX SCORES — V3 endpoints (V2 was deprecated by NBA in 2024)
# =========================================================================

def _min_to_float(min_str: Any) -> float | None:
    """V3 minutes format is 'PT34M12.34S' (ISO-8601 duration) OR 'MM:SS' OR int."""
    if min_str is None or min_str == "":
        return None
    if isinstance(min_str, (int, float)):
        return float(min_str)
    s = str(min_str).strip()

    # ISO-8601 duration: 'PT34M12.34S' or 'PT34M' or 'PT0S'
    if s.startswith("PT"):
        body = s[2:]
        minutes = 0.0
        seconds = 0.0
        if "M" in body:
            m_part, _, rest = body.partition("M")
            try:
                minutes = float(m_part)
            except ValueError:
                return None
            body = rest
        if body.endswith("S"):
            try:
                seconds = float(body[:-1])
            except ValueError:
                return None
        return minutes + seconds / 60.0

    # Old MM:SS format
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


# ---- Traditional box score (V3) ----------------------------------------

def fetch_traditional_box(game_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (team_rows, player_rows, player_seen) for the game's traditional box.

    V3 field names use camelCase (fieldGoalsMade, etc.) instead of V2's UPPER_CASE.
    """
    bs = call_with_retry(boxscoretraditionalv3.BoxScoreTraditionalV3, game_id=game_id)
    team_df = bs.team_stats.get_data_frame()
    player_df = bs.player_stats.get_data_frame()

    team_rows: list[dict] = []
    for _, r in team_df.iterrows():
        team_rows.append({
            "game_id": str(r["gameId"]).zfill(10),
            "team_id": int(r["teamId"]),
            "is_home": 0,  # corrected post-fetch using games.home_team_id
            "minutes": _min_to_float(r.get("minutes")),
            "fgm": _safe_int(r.get("fieldGoalsMade")),
            "fga": _safe_int(r.get("fieldGoalsAttempted")),
            "fg_pct": _safe_float(r.get("fieldGoalsPercentage")),
            "fg3m": _safe_int(r.get("threePointersMade")),
            "fg3a": _safe_int(r.get("threePointersAttempted")),
            "fg3_pct": _safe_float(r.get("threePointersPercentage")),
            "ftm": _safe_int(r.get("freeThrowsMade")),
            "fta": _safe_int(r.get("freeThrowsAttempted")),
            "ft_pct": _safe_float(r.get("freeThrowsPercentage")),
            "oreb": _safe_int(r.get("reboundsOffensive")),
            "dreb": _safe_int(r.get("reboundsDefensive")),
            "reb": _safe_int(r.get("reboundsTotal")),
            "ast": _safe_int(r.get("assists")),
            "stl": _safe_int(r.get("steals")),
            "blk": _safe_int(r.get("blocks")),
            "tov": _safe_int(r.get("turnovers")),
            "pf": _safe_int(r.get("foulsPersonal")),
            "pts": _safe_int(r.get("points")),
            "plus_minus": _safe_int(r.get("plusMinusPoints")),
        })

    player_rows: list[dict] = []
    seen_players: list[dict] = []
    today_iso = date.today().isoformat()
    for _, r in player_df.iterrows():
        pid = int(r["personId"])
        full_name = " ".join(part for part in [r.get("firstName"), r.get("familyName")] if part)
        seen_players.append({
            "player_id": pid,
            "full_name": full_name or r.get("nameI"),
            "first_name": r.get("firstName"),
            "last_name": r.get("familyName"),
            "is_active": 1,
            "last_seen_date": today_iso,
        })
        # In V3, starters have a position field set ("F", "G", "C"); bench players have "" or NaN
        position = r.get("position")
        is_starter = 1 if (position is not None and str(position).strip() not in ("", "nan", "None")) else 0
        player_rows.append({
            "game_id": str(r["gameId"]).zfill(10),
            "player_id": pid,
            "team_id": int(r["teamId"]),
            "is_starter": is_starter,
            "minutes": _min_to_float(r.get("minutes")),
            "fgm": _safe_int(r.get("fieldGoalsMade")),
            "fga": _safe_int(r.get("fieldGoalsAttempted")),
            "fg_pct": _safe_float(r.get("fieldGoalsPercentage")),
            "fg3m": _safe_int(r.get("threePointersMade")),
            "fg3a": _safe_int(r.get("threePointersAttempted")),
            "fg3_pct": _safe_float(r.get("threePointersPercentage")),
            "ftm": _safe_int(r.get("freeThrowsMade")),
            "fta": _safe_int(r.get("freeThrowsAttempted")),
            "ft_pct": _safe_float(r.get("freeThrowsPercentage")),
            "oreb": _safe_int(r.get("reboundsOffensive")),
            "dreb": _safe_int(r.get("reboundsDefensive")),
            "reb": _safe_int(r.get("reboundsTotal")),
            "ast": _safe_int(r.get("assists")),
            "stl": _safe_int(r.get("steals")),
            "blk": _safe_int(r.get("blocks")),
            "tov": _safe_int(r.get("turnovers")),
            "pf": _safe_int(r.get("foulsPersonal")),
            "pts": _safe_int(r.get("points")),
            "plus_minus": _safe_int(r.get("plusMinusPoints")),
        })

    return team_rows, player_rows, seen_players


def ingest_traditional_box(conn: sqlite3.Connection, game_id: str) -> bool:
    try:
        team_rows, player_rows, seen = fetch_traditional_box(game_id)
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


# ---- Advanced box score (V3) -------------------------------------------

def fetch_advanced_box(game_id: str) -> tuple[list[dict], list[dict]]:
    bs = call_with_retry(boxscoreadvancedv3.BoxScoreAdvancedV3, game_id=game_id)
    team_df = bs.team_stats.get_data_frame()
    player_df = bs.player_stats.get_data_frame()

    def _team_row(r: dict) -> dict:
        return {
            "game_id": str(r["gameId"]).zfill(10),
            "team_id": int(r["teamId"]),
            "minutes": _min_to_float(r.get("minutes")),
            "off_rating": _safe_float(r.get("offensiveRating")),
            "def_rating": _safe_float(r.get("defensiveRating")),
            "net_rating": _safe_float(r.get("netRating")),
            "pace": _safe_float(r.get("pace")),
            "pie": _safe_float(r.get("PIE")),
            "ast_pct": _safe_float(r.get("assistPercentage")),
            "ast_to_tov": _safe_float(r.get("assistToTurnover")),
            "ast_ratio": _safe_float(r.get("assistRatio")),
            "oreb_pct": _safe_float(r.get("offensiveReboundPercentage")),
            "dreb_pct": _safe_float(r.get("defensiveReboundPercentage")),
            "reb_pct": _safe_float(r.get("reboundPercentage")),
            "tov_pct": _safe_float(r.get("turnoverRatio")),
            "efg_pct": _safe_float(r.get("effectiveFieldGoalPercentage")),
            "ts_pct": _safe_float(r.get("trueShootingPercentage")),
            "poss": _safe_float(r.get("possessions")),
        }

    def _player_row(r: dict) -> dict:
        return {
            "game_id": str(r["gameId"]).zfill(10),
            "player_id": int(r["personId"]),
            "team_id": int(r["teamId"]),
            "minutes": _min_to_float(r.get("minutes")),
            "off_rating": _safe_float(r.get("offensiveRating")),
            "def_rating": _safe_float(r.get("defensiveRating")),
            "net_rating": _safe_float(r.get("netRating")),
            "usg_pct": _safe_float(r.get("usagePercentage")),
            "pie": _safe_float(r.get("PIE")),
            "ast_pct": _safe_float(r.get("assistPercentage")),
            "ast_to_tov": _safe_float(r.get("assistToTurnover")),
            "ast_ratio": _safe_float(r.get("assistRatio")),
            "oreb_pct": _safe_float(r.get("offensiveReboundPercentage")),
            "dreb_pct": _safe_float(r.get("defensiveReboundPercentage")),
            "reb_pct": _safe_float(r.get("reboundPercentage")),
            "tov_pct": _safe_float(r.get("turnoverRatio")),
            "efg_pct": _safe_float(r.get("effectiveFieldGoalPercentage")),
            "ts_pct": _safe_float(r.get("trueShootingPercentage")),
            "pace": _safe_float(r.get("pace")),
            "poss": _safe_float(r.get("possessions")),
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


# =========================================================================
# PLAYER DEMOGRAPHICS — commonplayerinfo (one-time, then occasional refresh)
# =========================================================================

def list_players_needing_info(conn: sqlite3.Connection) -> list[int]:
    """Player IDs that have appeared in a box score but lack demographics."""
    rows = conn.execute(
        """
        SELECT player_id FROM players
        WHERE info_fetched IS NULL
          AND player_id IN (SELECT DISTINCT player_id FROM player_box_traditional)
        ORDER BY player_id
        """
    ).fetchall()
    return [r["player_id"] for r in rows]


def fetch_player_info(player_id: int) -> dict | None:
    """Pull demographics for one player. Returns None on failure."""
    try:
        ep = call_with_retry(commonplayerinfo.CommonPlayerInfo, player_id=player_id)
        df = ep.common_player_info.get_data_frame()
        if df.empty:
            return None
        r = df.iloc[0].to_dict()
        from datetime import datetime, timezone
        return {
            "player_id": int(r["PERSON_ID"]),
            "full_name": r.get("DISPLAY_FIRST_LAST"),
            "first_name": r.get("FIRST_NAME"),
            "last_name": r.get("LAST_NAME"),
            "is_active": 1 if r.get("ROSTERSTATUS") == "Active" else 0,
            "birthdate": (r["BIRTHDATE"][:10] if r.get("BIRTHDATE") else None),
            "position": r.get("POSITION") or None,
            "height": r.get("HEIGHT") or None,
            "weight": _safe_int(r.get("WEIGHT")),
            "jersey": r.get("JERSEY") or None,
            "team_id": _safe_int(r.get("TEAM_ID")) or None,
            "draft_year": _safe_int(r.get("DRAFT_YEAR")),
            "country": r.get("COUNTRY") or None,
            "season_exp": _safe_int(r.get("SEASON_EXP")),
            "info_fetched": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        logger.exception("commonplayerinfo failed for player_id=%s", player_id)
        return None


def ingest_player_info(conn: sqlite3.Connection, player_id: int) -> bool:
    info = fetch_player_info(player_id)
    if info is None:
        return False
    # Use a partial update — we don't want to wipe last_seen_date which lives in the
    # same row but is set by the box-score ingest path.
    sets = ", ".join(f"{k} = :{k}" for k in info if k != "player_id")
    conn.execute(
        f"UPDATE players SET {sets} WHERE player_id = :player_id",
        info,
    )
    return True

