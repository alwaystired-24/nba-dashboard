"""Data access layer for the dashboard.

All SQL lives here. Pages call these functions and never write SQL directly.
Streamlit's @st.cache_data is used aggressively because the DB only changes
once per day after the daily ETL run.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# Database location — same path the scripts use
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nba.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def db_mtime() -> float:
    """Used as a cache key — when the DB file changes, all caches invalidate."""
    return DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0


# =========================================================================
# REFERENCE DATA
# =========================================================================

@st.cache_data(show_spinner=False)
def teams(_mtime: float = 0.0) -> pd.DataFrame:
    """All 30 teams. _mtime forces cache invalidation when DB changes."""
    with _connect() as conn:
        return pd.read_sql_query(
            "SELECT team_id, abbreviation, full_name, nickname, city, conference, division "
            "FROM teams ORDER BY abbreviation",
            conn,
        )


@st.cache_data(show_spinner=False)
def team_lookup(_mtime: float = 0.0) -> dict[int, dict]:
    """team_id -> dict for fast lookups."""
    df = teams(_mtime)
    return {int(r["team_id"]): dict(r) for _, r in df.iterrows()}


# =========================================================================
# SCHEDULE
# =========================================================================

@st.cache_data(show_spinner=False)
def games_on_date(target_date: str, _mtime: float = 0.0) -> pd.DataFrame:
    """All games on a specific date (YYYY-MM-DD, ET)."""
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT g.game_id, g.season_type, g.game_date, g.status,
                   g.home_team_id, ht.abbreviation AS home_abbr, ht.full_name AS home_name,
                   g.away_team_id, at.abbreviation AS away_abbr, at.full_name AS away_name,
                   g.home_score, g.away_score
            FROM games g
            JOIN teams ht ON ht.team_id = g.home_team_id
            JOIN teams at ON at.team_id = g.away_team_id
            WHERE g.game_date = ?
            ORDER BY g.game_id
            """,
            conn, params=(target_date,),
        )


@st.cache_data(show_spinner=False)
def games_in_window(start_date: str, end_date: str, _mtime: float = 0.0) -> pd.DataFrame:
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT g.game_id, g.season_type, g.game_date, g.status,
                   g.home_team_id, ht.abbreviation AS home_abbr, ht.full_name AS home_name,
                   g.away_team_id, at.abbreviation AS away_abbr, at.full_name AS away_name,
                   g.home_score, g.away_score
            FROM games g
            JOIN teams ht ON ht.team_id = g.home_team_id
            JOIN teams at ON at.team_id = g.away_team_id
            WHERE g.game_date BETWEEN ? AND ?
            ORDER BY g.game_date, g.game_id
            """,
            conn, params=(start_date, end_date),
        )


@st.cache_data(show_spinner=False)
def latest_game_date(_mtime: float = 0.0) -> str | None:
    """Latest date with at least one Final game — useful when 'today' has no games yet."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(game_date) AS d FROM games WHERE status = 'Final'"
        ).fetchone()
    return row["d"] if row and row["d"] else None


@st.cache_data(show_spinner=False)
def latest_loaded_date(_mtime: float = 0.0) -> str | None:
    """Latest date in the games table regardless of status."""
    with _connect() as conn:
        row = conn.execute("SELECT MAX(game_date) AS d FROM games").fetchone()
    return row["d"] if row and row["d"] else None


# =========================================================================
# TEAM BOX SCORES — single game
# =========================================================================

@st.cache_data(show_spinner=False)
def game_team_box(game_id: str, _mtime: float = 0.0) -> pd.DataFrame:
    """Both teams' traditional + advanced merged for a single game."""
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT t.abbreviation, t.full_name, tbt.*,
                   tba.off_rating, tba.def_rating, tba.net_rating,
                   tba.pace, tba.efg_pct, tba.ts_pct, tba.tov_pct,
                   tba.oreb_pct, tba.dreb_pct, tba.ast_pct, tba.poss
            FROM team_box_traditional tbt
            JOIN teams t ON t.team_id = tbt.team_id
            LEFT JOIN team_box_advanced tba
              ON tba.game_id = tbt.game_id AND tba.team_id = tbt.team_id
            WHERE tbt.game_id = ?
            ORDER BY tbt.is_home DESC
            """,
            conn, params=(game_id,),
        )


@st.cache_data(show_spinner=False)
def game_player_box(game_id: str, _mtime: float = 0.0) -> pd.DataFrame:
    """Both teams' player box scores for a single game."""
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT t.abbreviation, p.full_name AS player_name, pbt.*,
                   pba.off_rating, pba.def_rating, pba.net_rating,
                   pba.usg_pct, pba.efg_pct, pba.ts_pct, pba.pie
            FROM player_box_traditional pbt
            JOIN teams t ON t.team_id = pbt.team_id
            JOIN players p ON p.player_id = pbt.player_id
            LEFT JOIN player_box_advanced pba
              ON pba.game_id = pbt.game_id AND pba.player_id = pbt.player_id
            WHERE pbt.game_id = ?
            ORDER BY t.abbreviation, pbt.is_starter DESC, pbt.minutes DESC
            """,
            conn, params=(game_id,),
        )


# =========================================================================
# TEAM AGGREGATES — averages over a form window
# =========================================================================

WINDOW_TO_LAST_N: dict[str, int | None] = {
    "L5": 5, "L10": 10, "L20": 20, "Season": None,
}


def _season_filter_clause(season_filter: str = "both") -> str:
    """Return a SQL fragment to filter games by season type.

    Args:
        season_filter: 'reg' | 'playoffs' | 'both'.

    Note: NBA's schedule API uses these season_type values:
      - 'Regular' (regular season)
      - 'Playoffs'
      - 'PlayIn' (play-in tournament — counted as playoffs for analysis)
      - 'PreSeason' (always excluded)
    """
    if season_filter == "reg":
        return "AND g.season_type = 'Regular'"
    if season_filter == "playoffs":
        return "AND g.season_type IN ('Playoffs', 'PlayIn')"
    # 'both' — include reg + playoffs + play-in, exclude preseason
    return "AND g.season_type IN ('Regular', 'Playoffs', 'PlayIn')"


def _team_recent_games_cte(team_id: int, last_n: int | None,
                            season_filter: str = "both") -> str:
    """Subquery: latest N completed games for a team, regardless of home/away.

    season_filter: 'reg' | 'playoffs' | 'both' — filters games by season type.
    """
    limit_clause = f"LIMIT {last_n}" if last_n else ""
    season_clause = _season_filter_clause(season_filter)
    return f"""
    WITH recent AS (
        SELECT g.game_id, g.game_date,
               CASE WHEN g.home_team_id = {team_id} THEN g.away_team_id ELSE g.home_team_id END AS opp_id
        FROM games g
        WHERE g.status = 'Final'
          AND (g.home_team_id = {team_id} OR g.away_team_id = {team_id})
          {season_clause}
        ORDER BY g.game_date DESC
        {limit_clause}
    )
    """


@st.cache_data(show_spinner=False)
def team_aggregate(team_id: int, window: str, season_filter: str = "both",
                    _mtime: float = 0.0) -> dict:
    """Return averages across the window for one team. Combines traditional + advanced."""
    last_n = WINDOW_TO_LAST_N[window]
    with _connect() as conn:
        cte = _team_recent_games_cte(team_id, last_n, season_filter)
        row = conn.execute(
            cte + f"""
            SELECT
                COUNT(*) AS gp,
                AVG(tbt.pts)    AS pts,
                AVG(tbt.fg_pct) AS fg_pct,
                AVG(tbt.fg3_pct) AS fg3_pct,
                AVG(tbt.ft_pct) AS ft_pct,
                AVG(tbt.fg3a)   AS fg3a,
                AVG(tbt.fga)    AS fga,
                AVG(tbt.reb)    AS reb,
                AVG(tbt.oreb)   AS oreb,
                AVG(tbt.dreb)   AS dreb,
                AVG(tbt.ast)    AS ast,
                AVG(tbt.stl)    AS stl,
                AVG(tbt.blk)    AS blk,
                AVG(tbt.tov)    AS tov,
                AVG(tbt.pf)     AS pf,
                AVG(tba.off_rating) AS off_rating,
                AVG(tba.def_rating) AS def_rating,
                AVG(tba.net_rating) AS net_rating,
                AVG(tba.pace)    AS pace,
                AVG(tba.efg_pct) AS efg_pct,
                AVG(tba.ts_pct)  AS ts_pct,
                AVG(tba.tov_pct) AS tov_pct,
                AVG(tba.oreb_pct) AS oreb_pct,
                AVG(tba.dreb_pct) AS dreb_pct,
                AVG(tba.ast_pct) AS ast_pct,
                AVG(tba.poss)    AS poss
            FROM recent r
            JOIN team_box_traditional tbt ON tbt.game_id = r.game_id AND tbt.team_id = {team_id}
            LEFT JOIN team_box_advanced tba ON tba.game_id = r.game_id AND tba.team_id = {team_id}
            """
        ).fetchone()
    return dict(row) if row else {}


@st.cache_data(show_spinner=False)
def team_record(team_id: int, window: str, season_filter: str = "both",
                 _mtime: float = 0.0) -> tuple[int, int]:
    """W-L record across the window."""
    last_n = WINDOW_TO_LAST_N[window]
    with _connect() as conn:
        cte = _team_recent_games_cte(team_id, last_n, season_filter)
        rows = conn.execute(
            cte + f"""
            SELECT g.home_team_id, g.away_team_id, g.home_score, g.away_score
            FROM recent r JOIN games g ON g.game_id = r.game_id
            """
        ).fetchall()
    w = l = 0
    for r in rows:
        team_pts = r["home_score"] if r["home_team_id"] == team_id else r["away_score"]
        opp_pts  = r["away_score"] if r["home_team_id"] == team_id else r["home_score"]
        if team_pts is None or opp_pts is None:
            continue
        if team_pts > opp_pts: w += 1
        else: l += 1
    return w, l


@st.cache_data(show_spinner=False)
def team_opponent_aggregate(team_id: int, window: str, season_filter: str = "both",
                              _mtime: float = 0.0) -> dict:
    """Stats of the OPPONENTS faced — what this team allowed across the window.

    This drives the Defence layer: opp_pts allowed, opp eFG% allowed, etc.
    """
    last_n = WINDOW_TO_LAST_N[window]
    with _connect() as conn:
        cte = _team_recent_games_cte(team_id, last_n, season_filter)
        row = conn.execute(
            cte + f"""
            SELECT
                AVG(tbt.pts)    AS opp_pts,
                AVG(tbt.fg_pct) AS opp_fg_pct,
                AVG(tbt.fg3_pct) AS opp_fg3_pct,
                AVG(tbt.fg3a)   AS opp_fg3a,
                AVG(tbt.fga)    AS opp_fga,
                AVG(tbt.reb)    AS opp_reb,
                AVG(tbt.oreb)   AS opp_oreb,
                AVG(tbt.ast)    AS opp_ast,
                AVG(tbt.tov)    AS opp_tov,
                AVG(tba.efg_pct) AS opp_efg_pct,
                AVG(tba.ts_pct)  AS opp_ts_pct,
                AVG(tba.tov_pct) AS opp_tov_pct
            FROM recent r
            JOIN team_box_traditional tbt ON tbt.game_id = r.game_id AND tbt.team_id = r.opp_id
            LEFT JOIN team_box_advanced tba ON tba.game_id = r.game_id AND tba.team_id = r.opp_id
            """
        ).fetchone()
    return dict(row) if row else {}


@st.cache_data(show_spinner=False)
def team_recent_games(team_id: int, last_n: int = 20, season_filter: str = "both",
                       _mtime: float = 0.0) -> pd.DataFrame:
    """One row per game with both teams' summary — for trend charts."""
    season_clause = _season_filter_clause(season_filter)
    with _connect() as conn:
        return pd.read_sql_query(
            f"""
            SELECT g.game_id, g.game_date, g.season_type,
                   CASE WHEN g.home_team_id = ? THEN 'H' ELSE 'A' END AS site,
                   CASE WHEN g.home_team_id = ? THEN g.away_team_id ELSE g.home_team_id END AS opp_id,
                   tbt.pts, tbt.fg_pct, tbt.fg3_pct,
                   tba.off_rating, tba.def_rating, tba.net_rating, tba.pace,
                   tba.efg_pct, tba.ts_pct,
                   opp_tbt.pts AS opp_pts
            FROM games g
            JOIN team_box_traditional tbt
              ON tbt.game_id = g.game_id AND tbt.team_id = ?
            LEFT JOIN team_box_advanced tba
              ON tba.game_id = g.game_id AND tba.team_id = ?
            JOIN team_box_traditional opp_tbt
              ON opp_tbt.game_id = g.game_id AND opp_tbt.team_id != ?
            WHERE g.status = 'Final'
              AND (g.home_team_id = ? OR g.away_team_id = ?)
              {season_clause}
            ORDER BY g.game_date DESC
            LIMIT ?
            """,
            conn, params=(team_id, team_id, team_id, team_id, team_id, team_id, team_id, last_n),
        )


# =========================================================================
# LEAGUE-WIDE — for ranking each team
# =========================================================================

@st.cache_data(show_spinner=False)
def league_team_table(window: str, season_filter: str = "both",
                       _mtime: float = 0.0) -> pd.DataFrame:
    """One row per team, averaged over the window. Used by the Team Stats page."""
    last_n = WINDOW_TO_LAST_N[window]
    rows = []
    for tm in teams(_mtime).itertuples(index=False):
        agg = team_aggregate(int(tm.team_id), window, season_filter, _mtime=_mtime)
        opp = team_opponent_aggregate(int(tm.team_id), window, season_filter, _mtime=_mtime)
        w, l = team_record(int(tm.team_id), window, season_filter, _mtime=_mtime)
        rows.append({
            "team_id": int(tm.team_id), "abbr": tm.abbreviation, "team": tm.full_name,
            "gp": agg.get("gp", 0), "w": w, "l": l,
            **{k: v for k, v in agg.items() if k != "gp"},
            **opp,
        })
    return pd.DataFrame(rows)


# Stats where LOWER is better — used for rank direction
LOWER_IS_BETTER = {
    "def_rating", "tov", "tov_pct", "pf",
    "opp_pts", "opp_fg_pct", "opp_fg3_pct", "opp_fg3a", "opp_fga",
    "opp_efg_pct", "opp_ts_pct", "opp_tov_pct", "opp_reb", "opp_oreb", "opp_ast", "opp_tov",
    "l",  # losses
}


def compute_team_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """Add rank columns per numeric stat. Higher = better unless in LOWER_IS_BETTER.
    Returns a NEW dataframe with `_rank` columns appended for each numeric col."""
    out = df.copy()
    skip = {"team_id", "abbr", "team", "gp"}
    for c in df.columns:
        if c in skip or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        ascending = c in LOWER_IS_BETTER
        out[f"{c}_rank"] = df[c].rank(method="min", ascending=ascending,
                                        na_option="bottom").astype("Int64")
    return out


def compute_league_averages(df: pd.DataFrame) -> dict:
    """Mean of every numeric column across the team table — for the bottom row."""
    out = {}
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            out[c] = df[c].mean()
    return out


@st.cache_data(show_spinner=False)
def upcoming_games(start_date: str, days: int = 7, _mtime: float = 0.0) -> pd.DataFrame:
    """All scheduled games from start_date forward, regardless of status.

    The Phase 1 ETL only INSERTed games once a team finished one — this helper
    relies on the daily ETL keeping the schedule sweep fresh. Future games show
    up with status='Scheduled' from LeagueGameFinder once the NBA publishes them.
    """
    from datetime import date, timedelta
    end_date = (date.fromisoformat(start_date) + timedelta(days=days)).isoformat()
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT g.game_id, g.season_type, g.game_date, g.status,
                   g.home_team_id, ht.abbreviation AS home_abbr, ht.full_name AS home_name,
                   g.away_team_id, at.abbreviation AS away_abbr, at.full_name AS away_name,
                   g.home_score, g.away_score
            FROM games g
            JOIN teams ht ON ht.team_id = g.home_team_id
            JOIN teams at ON at.team_id = g.away_team_id
            WHERE g.game_date BETWEEN ? AND ?
            ORDER BY g.game_date, g.game_id
            """,
            conn, params=(start_date, end_date),
        )


# =========================================================================
# PLAYER AGGREGATES
# =========================================================================

@st.cache_data(show_spinner=False)
def player_aggregate(player_id: int, window: str, season_filter: str = "both",
                      _mtime: float = 0.0) -> dict:
    """Player averages across the window."""
    last_n = WINDOW_TO_LAST_N[window]
    limit_clause = f"LIMIT {last_n}" if last_n else ""
    season_clause = _season_filter_clause(season_filter)
    with _connect() as conn:
        row = conn.execute(
            f"""
            WITH recent AS (
                SELECT pbt.game_id, g.game_date
                FROM player_box_traditional pbt
                JOIN games g ON g.game_id = pbt.game_id
                WHERE pbt.player_id = ? AND g.status = 'Final' AND pbt.minutes > 0
                  {season_clause}
                ORDER BY g.game_date DESC
                {limit_clause}
            )
            SELECT
                COUNT(*) AS gp,
                AVG(pbt.minutes) AS minutes,
                AVG(pbt.pts)     AS pts,
                AVG(pbt.reb)     AS reb,
                AVG(pbt.ast)     AS ast,
                AVG(pbt.stl)     AS stl,
                AVG(pbt.blk)     AS blk,
                AVG(pbt.tov)     AS tov,
                AVG(pbt.fg_pct)  AS fg_pct,
                AVG(pbt.fg3_pct) AS fg3_pct,
                AVG(pbt.ft_pct)  AS ft_pct,
                AVG(pbt.fg3a)    AS fg3a,
                AVG(pbt.fga)     AS fga,
                AVG(pba.off_rating) AS off_rating,
                AVG(pba.def_rating) AS def_rating,
                AVG(pba.net_rating) AS net_rating,
                AVG(pba.usg_pct) AS usg_pct,
                AVG(pba.efg_pct) AS efg_pct,
                AVG(pba.ts_pct)  AS ts_pct,
                AVG(pba.pie)     AS pie,
                SUM(pbt.is_starter) AS starts
            FROM recent r
            JOIN player_box_traditional pbt
              ON pbt.game_id = r.game_id AND pbt.player_id = ?
            LEFT JOIN player_box_advanced pba
              ON pba.game_id = r.game_id AND pba.player_id = ?
            """,
            (player_id, player_id, player_id),
        ).fetchone()
    return dict(row) if row else {}


@st.cache_data(show_spinner=False)
def league_player_table(window: str, min_games: int = 5, min_minutes: float = 12.0,
                        season_filter: str = "both",
                        _mtime: float = 0.0) -> pd.DataFrame:
    """Aggregate every active player across the window, filter by GP / MPG threshold."""
    last_n = WINDOW_TO_LAST_N[window]
    limit_clause = f"LIMIT {last_n}" if last_n else ""
    season_clause = _season_filter_clause(season_filter)
    with _connect() as conn:
        df = pd.read_sql_query(
            f"""
            WITH game_filter AS (
                SELECT DISTINCT g.game_id
                FROM games g
                WHERE g.status = 'Final'
                  {season_clause}
            ),
            ranked AS (
                SELECT pbt.player_id, pbt.team_id, pbt.game_id, g.game_date,
                       pbt.minutes, pbt.pts, pbt.reb, pbt.ast, pbt.stl, pbt.blk, pbt.tov,
                       pbt.fg_pct, pbt.fg3_pct, pbt.ft_pct, pbt.fg3a, pbt.fga, pbt.is_starter,
                       pba.off_rating, pba.def_rating, pba.net_rating,
                       pba.usg_pct, pba.efg_pct, pba.ts_pct, pba.pie,
                       ROW_NUMBER() OVER (PARTITION BY pbt.player_id ORDER BY g.game_date DESC) AS rn
                FROM player_box_traditional pbt
                JOIN games g ON g.game_id = pbt.game_id AND g.status = 'Final'
                LEFT JOIN player_box_advanced pba
                  ON pba.game_id = pbt.game_id AND pba.player_id = pbt.player_id
                WHERE pbt.minutes > 0
                  AND pbt.game_id IN (SELECT game_id FROM game_filter)
            )
            SELECT player_id, team_id,
                   COUNT(*) AS gp,
                   SUM(is_starter) AS starts,
                   AVG(minutes) AS minutes,
                   AVG(pts) AS pts, AVG(reb) AS reb, AVG(ast) AS ast,
                   AVG(stl) AS stl, AVG(blk) AS blk, AVG(tov) AS tov,
                   AVG(fg_pct) AS fg_pct, AVG(fg3_pct) AS fg3_pct, AVG(ft_pct) AS ft_pct,
                   AVG(fg3a) AS fg3a, AVG(fga) AS fga,
                   AVG(off_rating) AS off_rating, AVG(def_rating) AS def_rating,
                   AVG(net_rating) AS net_rating,
                   AVG(usg_pct) AS usg_pct, AVG(efg_pct) AS efg_pct,
                   AVG(ts_pct) AS ts_pct, AVG(pie) AS pie
            FROM ranked
            { 'WHERE rn <= ' + str(last_n) if last_n else '' }
            GROUP BY player_id, team_id
            """,
            conn,
        )
    # Attach name, team abbr, and demographics (if pulled)
    plyrs = pd.read_sql_query(
        "SELECT player_id, full_name AS player, position, birthdate, height, weight, draft_year "
        "FROM players",
        _connect(),
    )
    tms = teams(_mtime)[["team_id", "abbreviation"]].rename(columns={"abbreviation": "team"})
    df = df.merge(plyrs, on="player_id", how="left").merge(tms, on="team_id", how="left")
    df = df[(df["gp"] >= min_games) & (df["minutes"] >= min_minutes)]

    # Compute age in years (decimal) from birthdate where available
    if "birthdate" in df.columns:
        df["birthdate_dt"] = pd.to_datetime(df["birthdate"], errors="coerce")
        today = pd.Timestamp("today").normalize()
        df["age"] = ((today - df["birthdate_dt"]).dt.days / 365.25).round(1)
        df = df.drop(columns=["birthdate_dt"])

    # Normalize position (NBA returns "Forward", "Guard-Forward" etc — collapse to G/F/C buckets)
    if "position" in df.columns:
        df["pos_bucket"] = df["position"].apply(_position_bucket)

    return df


def _position_bucket(pos: str | None) -> str:
    if not pos or not isinstance(pos, str):
        return "—"
    p = pos.upper()
    if "GUARD" in p and "FORWARD" in p: return "G/F"
    if "FORWARD" in p and "CENTER" in p: return "F/C"
    if "GUARD" in p: return "G"
    if "FORWARD" in p: return "F"
    if "CENTER" in p: return "C"
    return pos


# Player stats where LOWER is better
PLAYER_LOWER_IS_BETTER = {"def_rating", "tov", "tov_pct"}


def compute_player_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """Add `_rank` columns to player table."""
    out = df.copy()
    skip = {"player_id", "team_id", "player", "team", "position", "pos_bucket",
            "birthdate", "height", "weight", "draft_year", "age", "gp", "starts"}
    for c in df.columns:
        if c in skip or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        ascending = c in PLAYER_LOWER_IS_BETTER
        out[f"{c}_rank"] = df[c].rank(method="min", ascending=ascending,
                                        na_option="bottom").astype("Int64")
    return out


# =========================================================================
# INJURIES + TEAM NEWS (ESPN data)
# =========================================================================

@st.cache_data(show_spinner=False)
def team_injuries(team_id: int, _mtime: float = 0.0) -> pd.DataFrame:
    """Current injuries for a team. Empty DataFrame if no data."""
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return pd.read_sql_query(
                """
                SELECT player_name, status, detail, return_date, fetched_utc
                FROM injuries
                WHERE team_id = ?
                ORDER BY
                    CASE status
                        WHEN 'Out' THEN 1
                        WHEN 'Out For Season' THEN 1
                        WHEN 'Doubtful' THEN 2
                        WHEN 'Questionable' THEN 3
                        WHEN 'Day-To-Day' THEN 4
                        WHEN 'Probable' THEN 5
                        ELSE 6
                    END,
                    player_name
                """,
                conn, params=(team_id,),
            )
    except sqlite3.OperationalError:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def all_team_injury_counts(_mtime: float = 0.0) -> dict[int, int]:
    """Return team_id -> count of injuries (Out/Doubtful only — not Probable/D-T-D).

    Used for compact badges on Today page game cards.
    """
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT team_id, COUNT(*) AS n
                FROM injuries
                WHERE status IN ('Out', 'Out For Season', 'Doubtful', 'Suspended')
                GROUP BY team_id
                """
            ).fetchall()
            return {r["team_id"]: r["n"] for r in rows}
    except sqlite3.OperationalError:
        return {}


@st.cache_data(show_spinner=False)
def team_news(team_id: int, limit: int = 5, _mtime: float = 0.0) -> pd.DataFrame:
    """Latest news headlines for a team. Empty DataFrame if no data."""
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return pd.read_sql_query(
                """
                SELECT headline, summary, category, published_utc, url
                FROM team_news
                WHERE team_id = ?
                ORDER BY published_utc DESC
                LIMIT ?
                """,
                conn, params=(team_id, limit),
            )
    except sqlite3.OperationalError:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def league_news(limit: int = 10, _mtime: float = 0.0) -> pd.DataFrame:
    """Latest news headlines across all teams. Used for Today landing."""
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return pd.read_sql_query(
                """
                SELECT n.headline, n.summary, n.category, n.published_utc, n.url,
                       n.team_id, t.abbreviation AS team_abbr
                FROM team_news n
                JOIN teams t ON t.team_id = n.team_id
                ORDER BY n.published_utc DESC
                LIMIT ?
                """,
                conn, params=(limit,),
            )
    except sqlite3.OperationalError:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def league_injuries_top(limit: int = 10, _mtime: float = 0.0) -> pd.DataFrame:
    """League-wide injury watch — Out and Doubtful, top N by status severity.

    Used for the "League injury watch" panel on Today landing.
    """
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return pd.read_sql_query(
                """
                SELECT i.player_name, i.status, i.detail, i.team_id,
                       t.abbreviation AS team_abbr
                FROM injuries i
                JOIN teams t ON t.team_id = i.team_id
                WHERE i.status IN ('Out', 'Out For Season', 'Doubtful', 'Suspended', 'Questionable')
                ORDER BY
                    CASE i.status
                        WHEN 'Out' THEN 1
                        WHEN 'Out For Season' THEN 1
                        WHEN 'Suspended' THEN 1
                        WHEN 'Doubtful' THEN 2
                        WHEN 'Questionable' THEN 3
                        ELSE 4
                    END,
                    i.player_name
                LIMIT ?
                """,
                conn, params=(limit,),
            )
    except sqlite3.OperationalError:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def conference_standings(conference: str, season_filter: str = "reg",
                          _mtime: float = 0.0) -> pd.DataFrame:
    """Return teams in a conference ranked by season win pct.

    Args:
        conference: 'East' or 'West'
        season_filter: 'reg', 'po', or 'both'

    Returns DataFrame with: rank, team_id, abbreviation, full_name, w, l, win_pct
    """
    rows = []
    for tm in teams(_mtime).itertuples(index=False):
        if str(getattr(tm, "conference", "") or "").lower() != conference.lower():
            continue
        w, l = team_record(int(tm.team_id), "Season", season_filter, _mtime=_mtime)
        win_pct = w / (w + l) if (w + l) > 0 else 0.0
        rows.append({
            "team_id": int(tm.team_id),
            "abbreviation": tm.abbreviation,
            "full_name": tm.full_name,
            "w": w,
            "l": l,
            "win_pct": win_pct,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("win_pct", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df


@st.cache_data(show_spinner=False)
def stat_leaders(stat: str, season_filter: str = "reg",
                  min_games: int = 5, top_n: int = 5,
                  _mtime: float = 0.0) -> pd.DataFrame:
    """Top N players for a stat over the current season.

    Args:
        stat: column name in player_box_traditional, e.g. 'pts', 'ast', 'reb',
              'stl', 'blk', 'fg_pct', 'fg3_pct'
        season_filter: 'reg', 'po', or 'both'
        min_games: minimum games played to qualify
        top_n: how many players to return

    Returns DataFrame: player_id, player_name, team_id, team_abbr, gp, value
    """
    season_clause = _season_filter_clause(season_filter)

    # For percentage stats, average; for counting stats, average too
    # (basketball ref reports per-game averages)
    sql = f"""
        SELECT pbt.player_id,
               p.full_name AS player_name,
               pbt.team_id,
               t.abbreviation AS team_abbr,
               COUNT(*) AS gp,
               AVG(pbt.{stat}) AS value
        FROM player_box_traditional pbt
        JOIN games g ON g.game_id = pbt.game_id AND g.status = 'Final'
        JOIN players p ON p.player_id = pbt.player_id
        JOIN teams t ON t.team_id = pbt.team_id
        WHERE pbt.minutes IS NOT NULL AND pbt.minutes > 0 {season_clause}
        GROUP BY pbt.player_id, pbt.team_id
        HAVING COUNT(*) >= ?
        ORDER BY value DESC
        LIMIT ?
    """
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return pd.read_sql_query(sql, conn, params=(min_games, top_n))
    except sqlite3.OperationalError:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def closing_line_for_game(game_id: str, _mtime: float = 0.0) -> dict:
    """Return the most-recent (closest-to-tip) odds snapshot for a game.

    Returns dict with: spread (str), total (str), or empty dict if no odds.
    """
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            # Take the latest snapshot per market for this game, prefer DraftKings
            row = conn.execute(
                """
                SELECT market, point, name, price, home_team, away_team
                FROM odds_snapshots
                WHERE game_id = ?
                ORDER BY snapshot_utc DESC
                """,
                (game_id,),
            ).fetchall()
            if not row:
                return {}
            # Group by market, take first (= most recent)
            spread_pt = None
            total_pt = None
            for r in row:
                if r["market"] == "spreads" and spread_pt is None:
                    # Pick the home team's spread
                    if r["name"] == r["home_team"]:
                        spread_pt = r["point"]
                elif r["market"] == "totals" and total_pt is None:
                    total_pt = r["point"]
                if spread_pt is not None and total_pt is not None:
                    break
            out = {}
            if spread_pt is not None:
                # Format e.g. -5.5 or +3
                out["spread"] = f"{spread_pt:+.1f}"
            if total_pt is not None:
                out["total"] = f"{total_pt:.1f}"
            return out
    except sqlite3.OperationalError:
        return {}


# =========================================================================
# REST DAYS — days since the team's last game
# =========================================================================

@st.cache_data(show_spinner=False)
def team_rest_days(team_id: int, game_date: str, _mtime: float = 0.0) -> int | None:
    """Return days of rest before this game. None if no prior game in DB.

    Rest = (game_date - prior_game_date) - 1.
    Examples:
      Team played yesterday, game today -> 0 (back-to-back)
      Team played 2 days ago, game today -> 1
      First game of season -> None (returns None to display as "—")
    """
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT MAX(g.game_date) AS prior_date
            FROM games g
            WHERE (g.home_team_id = ? OR g.away_team_id = ?)
              AND g.status = 'Final'
              AND g.game_date < ?
            """,
            (team_id, team_id, game_date),
        ).fetchone()
    if not row or not row["prior_date"]:
        return None
    from datetime import date
    try:
        d_game = date.fromisoformat(game_date)
        d_prior = date.fromisoformat(row["prior_date"])
        return (d_game - d_prior).days - 1
    except (ValueError, TypeError):
        return None


# =========================================================================
# HEAD-TO-HEAD
# =========================================================================

@st.cache_data(show_spinner=False)
def head_to_head(team_a_id: int, team_b_id: int, _mtime: float = 0.0) -> pd.DataFrame:
    """All games this season between the two teams."""
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT g.game_id, g.game_date, g.season_type,
                   g.home_team_id, ht.abbreviation AS home_abbr,
                   g.away_team_id, at.abbreviation AS away_abbr,
                   g.home_score, g.away_score
            FROM games g
            JOIN teams ht ON ht.team_id = g.home_team_id
            JOIN teams at ON at.team_id = g.away_team_id
            WHERE g.status = 'Final'
              AND ((g.home_team_id = ? AND g.away_team_id = ?)
                OR (g.home_team_id = ? AND g.away_team_id = ?))
            ORDER BY g.game_date DESC
            """,
            conn, params=(team_a_id, team_b_id, team_b_id, team_a_id),
        )


@st.cache_data(show_spinner=False)
def last_starting_lineup(team_id: int, _mtime: float = 0.0) -> pd.DataFrame:
    """Most recent game's starters — proxy for likely starters tonight."""
    with _connect() as conn:
        latest = conn.execute(
            """
            SELECT g.game_id FROM games g
            WHERE g.status = 'Final' AND (g.home_team_id = ? OR g.away_team_id = ?)
            ORDER BY g.game_date DESC LIMIT 1
            """,
            (team_id, team_id),
        ).fetchone()
        if not latest:
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT p.full_name AS player, pbt.minutes, pbt.pts, pbt.reb, pbt.ast
            FROM player_box_traditional pbt
            JOIN players p ON p.player_id = pbt.player_id
            WHERE pbt.game_id = ? AND pbt.team_id = ? AND pbt.is_starter = 1
            ORDER BY pbt.minutes DESC
            """,
            conn, params=(latest["game_id"], team_id),
        )


@st.cache_data(show_spinner=False)
def team_minutes_forecast(team_id: int, _mtime: float = 0.0) -> pd.DataFrame:
    """L5 minutes forecast + L5 plus/minus + injury redistribution flag.

    Returns one row per player who appeared in the team's last game.
    Columns:
        player_id, player_name, last_min, l5_min, l5_pm, l5_gp,
        is_starter_last, is_out, is_doubtful, will_absorb

    will_absorb: True if this player is in the top 3 minutes-eaters AND
        someone with significant L5 minutes (>15) is OUT/DOUBTFUL on the team.
    """
    with _connect() as conn:
        # Latest game for the team
        latest = conn.execute(
            """
            SELECT g.game_id FROM games g
            WHERE g.status = 'Final' AND (g.home_team_id = ? OR g.away_team_id = ?)
            ORDER BY g.game_date DESC LIMIT 1
            """,
            (team_id, team_id),
        ).fetchone()
        if not latest:
            return pd.DataFrame()

        last_game_id = latest["game_id"]

        # Step 1: players who appeared in the last game (and their stats from that game)
        last_game_players = pd.read_sql_query(
            """
            SELECT pbt.player_id, p.full_name AS player_name,
                   pbt.minutes AS last_min, pbt.is_starter AS is_starter_last
            FROM player_box_traditional pbt
            JOIN players p ON p.player_id = pbt.player_id
            WHERE pbt.game_id = ? AND pbt.team_id = ?
            ORDER BY pbt.minutes DESC
            """,
            conn, params=(last_game_id, team_id),
        )
        if last_game_players.empty:
            return pd.DataFrame()

        # Step 2: for each player, compute L5 averages
        # Get the last 5 game_ids for this team
        recent_games = pd.read_sql_query(
            """
            SELECT g.game_id FROM games g
            WHERE g.status = 'Final' AND (g.home_team_id = ? OR g.away_team_id = ?)
            ORDER BY g.game_date DESC LIMIT 5
            """,
            conn, params=(team_id, team_id),
        )
        if recent_games.empty:
            return pd.DataFrame()
        recent_ids = recent_games["game_id"].tolist()
        placeholders = ",".join("?" * len(recent_ids))

        l5_stats = pd.read_sql_query(
            f"""
            SELECT pbt.player_id,
                   AVG(pbt.minutes) AS l5_min,
                   AVG(pbt.plus_minus) AS l5_pm,
                   COUNT(*) AS l5_gp
            FROM player_box_traditional pbt
            WHERE pbt.team_id = ? AND pbt.game_id IN ({placeholders})
              AND pbt.minutes IS NOT NULL
            GROUP BY pbt.player_id
            """,
            conn, params=[team_id] + recent_ids,
        )

    # Merge: last game players (left), L5 stats (right)
    df = last_game_players.merge(l5_stats, on="player_id", how="left")

    # Step 3: tag injuries
    inj_df = team_injuries(team_id, _mtime=_mtime)
    if not inj_df.empty:
        # Build a name -> status map (case-insensitive contains for robustness)
        inj_map = {}
        for _, row in inj_df.iterrows():
            inj_map[row["player_name"].lower()] = row["status"]

        def _injury_for(name: str) -> str | None:
            return inj_map.get(name.lower())

        df["injury_status"] = df["player_name"].apply(_injury_for)
        df["is_out"] = df["injury_status"].fillna("").str.lower().str.contains(
            "out|suspended", regex=True
        )
        df["is_doubtful"] = df["injury_status"].fillna("").str.lower().str.contains(
            "doubtful", regex=True
        )
        df["is_questionable"] = df["injury_status"].fillna("").str.lower().str.contains(
            "questionable", regex=True
        )
    else:
        df["injury_status"] = None
        df["is_out"] = False
        df["is_doubtful"] = False
        df["is_questionable"] = False

    # Step 4: minutes redistribution flag
    # If any player with L5 min > 15 is OUT or DOUBTFUL, flag the top 3
    # available rotation players (by L5 min) as likely to absorb minutes.
    significant_missing = df[
        ((df["is_out"] | df["is_doubtful"])) & (df["l5_min"].fillna(0) > 15)
    ]
    df["will_absorb"] = False
    if not significant_missing.empty:
        # Top 3 available players (not out, not doubtful) by L5 min
        available = df[~df["is_out"] & ~df["is_doubtful"]].sort_values(
            "l5_min", ascending=False
        )
        if not available.empty:
            top3_ids = set(available.head(3)["player_id"].tolist())
            df.loc[df["player_id"].isin(top3_ids), "will_absorb"] = True

    # Sort by L5 min desc (most-played first), put OUT/DOUBTFUL at bottom
    df["sort_key"] = df["l5_min"].fillna(0)
    df.loc[df["is_out"], "sort_key"] = -1
    df.loc[df["is_doubtful"], "sort_key"] = -0.5
    df = df.sort_values("sort_key", ascending=False).drop(columns=["sort_key"])
    return df.reset_index(drop=True)


# =========================================================================
# ODDS QUERIES (Phase 6)
# =========================================================================

@st.cache_data(show_spinner=False)
def odds_for_game(game_id: str, _mtime: float = 0.0) -> pd.DataFrame:
    """All odds_snapshots rows for a specific NBA game_id."""
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT fetched_utc, snapshot_phase, bookmaker, market,
                   home_price, away_price,
                   spread_home, spread_away,
                   total_line, over_price, under_price,
                   commence_time_utc, home_team_name, away_team_name,
                   bookmaker_last_update
            FROM odds_snapshots
            WHERE game_id = ?
            ORDER BY fetched_utc, bookmaker, market
            """,
            conn, params=(game_id,),
        )


@st.cache_data(show_spinner=False)
def odds_for_event(event_id: str, _mtime: float = 0.0) -> pd.DataFrame:
    """Same but by The Odds API event_id (for unmatched games)."""
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT fetched_utc, snapshot_phase, bookmaker, market,
                   home_price, away_price,
                   spread_home, spread_away,
                   total_line, over_price, under_price,
                   commence_time_utc, home_team_name, away_team_name,
                   bookmaker_last_update
            FROM odds_snapshots
            WHERE event_id = ?
            ORDER BY fetched_utc, bookmaker, market
            """,
            conn, params=(event_id,),
        )


@st.cache_data(show_spinner=False)
def latest_odds_snapshot(_mtime: float = 0.0) -> str | None:
    """When was the last odds fetch, in UTC ISO."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(fetched_utc) AS t FROM odds_snapshots"
        ).fetchone()
    return row["t"] if row and row["t"] else None
