-- NBA Dashboard SQLite Schema
-- Phase 1: core entities, schedule, traditional & advanced box scores
-- Stubs for Phase 5 (PBP/shots/matchups/refs) and Phase 6 (odds)

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- =========================================================================
-- CORE ENTITIES
-- =========================================================================

CREATE TABLE IF NOT EXISTS teams (
    team_id          INTEGER PRIMARY KEY,           -- NBA stats team_id (e.g. 1610612737)
    abbreviation     TEXT NOT NULL UNIQUE,          -- ATL, BOS, etc.
    full_name        TEXT NOT NULL,                 -- Atlanta Hawks
    nickname         TEXT,                          -- Hawks
    city             TEXT,                          -- Atlanta
    conference       TEXT,                          -- East / West
    division         TEXT
);

CREATE TABLE IF NOT EXISTS players (
    player_id        INTEGER PRIMARY KEY,           -- NBA stats player_id
    full_name        TEXT NOT NULL,
    first_name       TEXT,
    last_name        TEXT,
    is_active        INTEGER NOT NULL DEFAULT 1,    -- 0/1
    last_seen_date   TEXT                           -- ISO date of most recent game seen
);

-- =========================================================================
-- SCHEDULE / GAMES
-- =========================================================================

CREATE TABLE IF NOT EXISTS games (
    game_id          TEXT PRIMARY KEY,              -- e.g. "0022500123" (leading zeros matter)
    season           TEXT NOT NULL,                 -- "2025-26"
    season_type      TEXT NOT NULL,                 -- Regular / Playoffs / PlayIn / PreSeason
    game_date        TEXT NOT NULL,                 -- ISO date (ET) YYYY-MM-DD
    game_datetime_et TEXT,                          -- ISO datetime in US/Eastern
    home_team_id     INTEGER NOT NULL,
    away_team_id     INTEGER NOT NULL,
    home_score       INTEGER,
    away_score       INTEGER,
    status           TEXT,                          -- Scheduled / Live / Final / PPD
    arena            TEXT,
    attendance       INTEGER,
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_games_season ON games(season, season_type);
CREATE INDEX IF NOT EXISTS idx_games_home ON games(home_team_id);
CREATE INDEX IF NOT EXISTS idx_games_away ON games(away_team_id);

-- =========================================================================
-- TEAM BOX SCORES — TRADITIONAL
-- One row per team per game.
-- =========================================================================

CREATE TABLE IF NOT EXISTS team_box_traditional (
    game_id          TEXT NOT NULL,
    team_id          INTEGER NOT NULL,
    is_home          INTEGER NOT NULL,
    minutes          REAL,
    fgm              INTEGER, fga              INTEGER, fg_pct  REAL,
    fg3m             INTEGER, fg3a             INTEGER, fg3_pct REAL,
    ftm              INTEGER, fta              INTEGER, ft_pct  REAL,
    oreb             INTEGER, dreb             INTEGER, reb     INTEGER,
    ast              INTEGER, stl              INTEGER, blk     INTEGER,
    tov              INTEGER, pf               INTEGER,
    pts              INTEGER,
    plus_minus       INTEGER,
    PRIMARY KEY (game_id, team_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);
CREATE INDEX IF NOT EXISTS idx_tbt_team ON team_box_traditional(team_id);

-- =========================================================================
-- TEAM BOX SCORES — ADVANCED
-- =========================================================================

CREATE TABLE IF NOT EXISTS team_box_advanced (
    game_id          TEXT NOT NULL,
    team_id          INTEGER NOT NULL,
    minutes          REAL,
    off_rating       REAL,         -- ORtg
    def_rating       REAL,         -- DRtg
    net_rating       REAL,
    pace             REAL,
    pie              REAL,
    ast_pct          REAL,
    ast_to_tov       REAL,
    ast_ratio        REAL,
    oreb_pct         REAL,
    dreb_pct         REAL,
    reb_pct          REAL,
    tov_pct          REAL,
    efg_pct          REAL,
    ts_pct           REAL,
    poss             REAL,
    PRIMARY KEY (game_id, team_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

-- =========================================================================
-- PLAYER BOX SCORES — TRADITIONAL
-- =========================================================================

CREATE TABLE IF NOT EXISTS player_box_traditional (
    game_id          TEXT NOT NULL,
    player_id        INTEGER NOT NULL,
    team_id          INTEGER NOT NULL,
    is_starter       INTEGER,
    minutes          REAL,
    fgm              INTEGER, fga              INTEGER, fg_pct  REAL,
    fg3m             INTEGER, fg3a             INTEGER, fg3_pct REAL,
    ftm              INTEGER, fta              INTEGER, ft_pct  REAL,
    oreb             INTEGER, dreb             INTEGER, reb     INTEGER,
    ast              INTEGER, stl              INTEGER, blk     INTEGER,
    tov              INTEGER, pf               INTEGER,
    pts              INTEGER,
    plus_minus       INTEGER,
    PRIMARY KEY (game_id, player_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);
CREATE INDEX IF NOT EXISTS idx_pbt_player ON player_box_traditional(player_id);
CREATE INDEX IF NOT EXISTS idx_pbt_team ON player_box_traditional(team_id);

-- =========================================================================
-- PLAYER BOX SCORES — ADVANCED
-- =========================================================================

CREATE TABLE IF NOT EXISTS player_box_advanced (
    game_id          TEXT NOT NULL,
    player_id        INTEGER NOT NULL,
    team_id          INTEGER NOT NULL,
    minutes          REAL,
    off_rating       REAL,
    def_rating       REAL,
    net_rating       REAL,
    usg_pct          REAL,
    pie              REAL,
    ast_pct          REAL,
    ast_to_tov       REAL,
    ast_ratio        REAL,
    oreb_pct         REAL,
    dreb_pct         REAL,
    reb_pct          REAL,
    tov_pct           REAL,
    efg_pct          REAL,
    ts_pct           REAL,
    pace             REAL,
    poss             REAL,
    PRIMARY KEY (game_id, player_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

-- =========================================================================
-- ETL BOOKKEEPING
-- Tracks which scrapers have completed for which games — lets daily_update
-- pick up only what's missing.
-- =========================================================================

CREATE TABLE IF NOT EXISTS etl_runs (
    game_id          TEXT NOT NULL,
    endpoint         TEXT NOT NULL,                 -- e.g. 'team_box_traditional'
    status           TEXT NOT NULL,                 -- success / failed
    last_attempt_utc TEXT NOT NULL,
    error            TEXT,
    PRIMARY KEY (game_id, endpoint)
);

-- =========================================================================
-- PHASE 5 STUBS (created empty now, populated later)
-- =========================================================================

CREATE TABLE IF NOT EXISTS shots (
    shot_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id          TEXT NOT NULL,
    player_id        INTEGER NOT NULL,
    team_id          INTEGER NOT NULL,
    period           INTEGER, game_clock TEXT,
    shot_made        INTEGER,                       -- 0/1
    shot_type        TEXT,                          -- 2PT / 3PT
    shot_zone        TEXT, shot_zone_area TEXT, shot_zone_range TEXT,
    loc_x            INTEGER, loc_y INTEGER,
    shot_distance    INTEGER,
    action_type      TEXT,
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_shots_game ON shots(game_id);
CREATE INDEX IF NOT EXISTS idx_shots_player ON shots(player_id);

CREATE TABLE IF NOT EXISTS play_by_play (
    game_id          TEXT NOT NULL,
    event_num        INTEGER NOT NULL,
    period           INTEGER, game_clock TEXT,
    home_score       INTEGER, away_score INTEGER,
    event_type       INTEGER, event_action_type INTEGER,
    description_home TEXT, description_neutral TEXT, description_away TEXT,
    player1_id       INTEGER, player2_id INTEGER, player3_id INTEGER,
    PRIMARY KEY (game_id, event_num),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS defensive_matchups (
    game_id          TEXT NOT NULL,
    off_player_id    INTEGER NOT NULL,
    def_player_id    INTEGER NOT NULL,
    matchup_minutes  REAL,
    partial_poss     REAL,
    player_pts       INTEGER,
    team_pts         INTEGER,
    matchup_ast      INTEGER,
    matchup_tov      INTEGER,
    matchup_blk      INTEGER,
    matchup_fgm      INTEGER,
    matchup_fga      INTEGER,
    matchup_fg3m     INTEGER,
    matchup_fg3a     INTEGER,
    PRIMARY KEY (game_id, off_player_id, def_player_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS officials_per_game (
    game_id          TEXT NOT NULL,
    official_id      INTEGER NOT NULL,
    first_name       TEXT, last_name TEXT,
    jersey_num       TEXT,
    PRIMARY KEY (game_id, official_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

-- =========================================================================
-- PHASE 3 STUBS — injuries / team news
-- =========================================================================

CREATE TABLE IF NOT EXISTS injuries (
    fetched_at_utc   TEXT NOT NULL,
    player_id        INTEGER,
    player_name      TEXT NOT NULL,
    team_id          INTEGER,
    status           TEXT,                          -- Out / Day-to-day / Questionable
    description      TEXT,
    source           TEXT,                          -- 'espn' etc
    PRIMARY KEY (fetched_at_utc, player_name)
);

CREATE TABLE IF NOT EXISTS team_news (
    news_id          TEXT PRIMARY KEY,
    team_id          INTEGER,
    published_utc    TEXT NOT NULL,
    headline         TEXT NOT NULL,
    summary          TEXT,
    url              TEXT,
    source           TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_team_date ON team_news(team_id, published_utc DESC);

-- =========================================================================
-- PHASE 6 STUBS — odds
-- =========================================================================

CREATE TABLE IF NOT EXISTS odds_snapshots (
    snapshot_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_utc      TEXT NOT NULL,
    game_id          TEXT,                          -- nullable: nba_api game_id may not be matched yet
    home_team_id     INTEGER, away_team_id INTEGER,
    bookmaker        TEXT NOT NULL,
    market           TEXT NOT NULL,                 -- h2h / spreads / totals
    home_price       REAL, away_price  REAL,
    spread_home      REAL, spread_away REAL,
    total_line       REAL, over_price  REAL, under_price REAL,
    is_closing       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_odds_game ON odds_snapshots(game_id, market, bookmaker);
