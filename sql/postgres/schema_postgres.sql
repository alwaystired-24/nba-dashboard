-- =========================================================================
-- NBA Dashboard — Postgres Schema (Supabase)
-- Consolidated from SQLite schema.sql + migrations 002, 003, 004
-- Phase 1 migration: Option A (booleans kept as INTEGER for code compat)
-- =========================================================================

-- =========================================================================
-- CORE ENTITIES
-- =========================================================================

CREATE TABLE IF NOT EXISTS teams (
    team_id          INTEGER PRIMARY KEY,
    abbreviation     TEXT NOT NULL UNIQUE,
    full_name        TEXT NOT NULL,
    nickname         TEXT,
    city             TEXT,
    conference       TEXT,
    division         TEXT
);

CREATE TABLE IF NOT EXISTS players (
    player_id        INTEGER PRIMARY KEY,
    full_name        TEXT NOT NULL,
    first_name       TEXT,
    last_name        TEXT,
    is_active        INTEGER NOT NULL DEFAULT 1,
    last_seen_date   TEXT
);

-- =========================================================================
-- SCHEDULE / GAMES
-- =========================================================================

CREATE TABLE IF NOT EXISTS games (
    game_id          TEXT PRIMARY KEY,
    season           TEXT NOT NULL,
    season_type      TEXT NOT NULL,
    game_date        TEXT NOT NULL,
    game_datetime_et TEXT,
    home_team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    away_team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    home_score       INTEGER,
    away_score       INTEGER,
    status           TEXT,
    arena            TEXT,
    attendance       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_games_date   ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_games_season ON games(season, season_type);
CREATE INDEX IF NOT EXISTS idx_games_home   ON games(home_team_id);
CREATE INDEX IF NOT EXISTS idx_games_away   ON games(away_team_id);

-- =========================================================================
-- TEAM BOX SCORES — TRADITIONAL
-- =========================================================================

CREATE TABLE IF NOT EXISTS team_box_traditional (
    game_id          TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    team_id          INTEGER NOT NULL REFERENCES teams(team_id),
    is_home          INTEGER NOT NULL,
    minutes          DOUBLE PRECISION,
    fgm              INTEGER, fga              INTEGER, fg_pct  DOUBLE PRECISION,
    fg3m             INTEGER, fg3a             INTEGER, fg3_pct DOUBLE PRECISION,
    ftm              INTEGER, fta              INTEGER, ft_pct  DOUBLE PRECISION,
    oreb             INTEGER, dreb             INTEGER, reb     INTEGER,
    ast              INTEGER, stl              INTEGER, blk     INTEGER,
    tov              INTEGER, pf               INTEGER,
    pts              INTEGER,
    plus_minus       INTEGER,
    PRIMARY KEY (game_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_tbt_team ON team_box_traditional(team_id);

-- =========================================================================
-- TEAM BOX SCORES — ADVANCED
-- =========================================================================

CREATE TABLE IF NOT EXISTS team_box_advanced (
    game_id          TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    team_id          INTEGER NOT NULL REFERENCES teams(team_id),
    minutes          DOUBLE PRECISION,
    off_rating       DOUBLE PRECISION,
    def_rating       DOUBLE PRECISION,
    net_rating       DOUBLE PRECISION,
    pace             DOUBLE PRECISION,
    pie              DOUBLE PRECISION,
    ast_pct          DOUBLE PRECISION,
    ast_to_tov       DOUBLE PRECISION,
    ast_ratio        DOUBLE PRECISION,
    oreb_pct         DOUBLE PRECISION,
    dreb_pct         DOUBLE PRECISION,
    reb_pct          DOUBLE PRECISION,
    tov_pct          DOUBLE PRECISION,
    efg_pct          DOUBLE PRECISION,
    ts_pct           DOUBLE PRECISION,
    poss             DOUBLE PRECISION,
    PRIMARY KEY (game_id, team_id)
);

-- =========================================================================
-- PLAYER BOX SCORES — TRADITIONAL
-- =========================================================================

CREATE TABLE IF NOT EXISTS player_box_traditional (
    game_id          TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    player_id        INTEGER NOT NULL REFERENCES players(player_id),
    team_id          INTEGER NOT NULL REFERENCES teams(team_id),
    is_starter       INTEGER,
    minutes          DOUBLE PRECISION,
    fgm              INTEGER, fga              INTEGER, fg_pct  DOUBLE PRECISION,
    fg3m             INTEGER, fg3a             INTEGER, fg3_pct DOUBLE PRECISION,
    ftm              INTEGER, fta              INTEGER, ft_pct  DOUBLE PRECISION,
    oreb             INTEGER, dreb             INTEGER, reb     INTEGER,
    ast              INTEGER, stl              INTEGER, blk     INTEGER,
    tov              INTEGER, pf               INTEGER,
    pts              INTEGER,
    plus_minus       INTEGER,
    PRIMARY KEY (game_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_pbt_player ON player_box_traditional(player_id);
CREATE INDEX IF NOT EXISTS idx_pbt_team   ON player_box_traditional(team_id);

-- =========================================================================
-- PLAYER BOX SCORES — ADVANCED
-- =========================================================================

CREATE TABLE IF NOT EXISTS player_box_advanced (
    game_id          TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    player_id        INTEGER NOT NULL REFERENCES players(player_id),
    team_id          INTEGER NOT NULL REFERENCES teams(team_id),
    minutes          DOUBLE PRECISION,
    off_rating       DOUBLE PRECISION,
    def_rating       DOUBLE PRECISION,
    net_rating       DOUBLE PRECISION,
    usg_pct          DOUBLE PRECISION,
    pie              DOUBLE PRECISION,
    ast_pct          DOUBLE PRECISION,
    ast_to_tov       DOUBLE PRECISION,
    ast_ratio        DOUBLE PRECISION,
    oreb_pct         DOUBLE PRECISION,
    dreb_pct         DOUBLE PRECISION,
    reb_pct          DOUBLE PRECISION,
    tov_pct          DOUBLE PRECISION,
    efg_pct          DOUBLE PRECISION,
    ts_pct           DOUBLE PRECISION,
    pace             DOUBLE PRECISION,
    poss             DOUBLE PRECISION,
    PRIMARY KEY (game_id, player_id)
);

-- =========================================================================
-- ETL BOOKKEEPING
-- =========================================================================

CREATE TABLE IF NOT EXISTS etl_runs (
    game_id          TEXT NOT NULL,
    endpoint         TEXT NOT NULL,
    status           TEXT NOT NULL,
    last_attempt_utc TEXT NOT NULL,
    error            TEXT,
    PRIMARY KEY (game_id, endpoint)
);

-- =========================================================================
-- PHASE 5 STUBS
-- =========================================================================

CREATE TABLE IF NOT EXISTS shots (
    shot_id          BIGSERIAL PRIMARY KEY,
    game_id          TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    player_id        INTEGER NOT NULL,
    team_id          INTEGER NOT NULL,
    period           INTEGER, game_clock TEXT,
    shot_made        INTEGER,
    shot_type        TEXT,
    shot_zone        TEXT, shot_zone_area TEXT, shot_zone_range TEXT,
    loc_x            INTEGER, loc_y INTEGER,
    shot_distance    INTEGER,
    action_type      TEXT
);
CREATE INDEX IF NOT EXISTS idx_shots_game   ON shots(game_id);
CREATE INDEX IF NOT EXISTS idx_shots_player ON shots(player_id);

CREATE TABLE IF NOT EXISTS play_by_play (
    game_id          TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    event_num        INTEGER NOT NULL,
    period           INTEGER, game_clock TEXT,
    home_score       INTEGER, away_score INTEGER,
    event_type       INTEGER, event_action_type INTEGER,
    description_home TEXT, description_neutral TEXT, description_away TEXT,
    player1_id       INTEGER, player2_id INTEGER, player3_id INTEGER,
    PRIMARY KEY (game_id, event_num)
);

CREATE TABLE IF NOT EXISTS defensive_matchups (
    game_id          TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    off_player_id    INTEGER NOT NULL,
    def_player_id    INTEGER NOT NULL,
    matchup_minutes  DOUBLE PRECISION,
    partial_poss     DOUBLE PRECISION,
    player_pts       INTEGER,
    team_pts         INTEGER,
    matchup_ast      INTEGER,
    matchup_tov      INTEGER,
    matchup_blk      INTEGER,
    matchup_fgm      INTEGER,
    matchup_fga      INTEGER,
    matchup_fg3m     INTEGER,
    matchup_fg3a     INTEGER,
    PRIMARY KEY (game_id, off_player_id, def_player_id)
);

CREATE TABLE IF NOT EXISTS officials_per_game (
    game_id          TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    official_id      INTEGER NOT NULL,
    first_name       TEXT, last_name TEXT,
    jersey_num       TEXT,
    PRIMARY KEY (game_id, official_id)
);

-- =========================================================================
-- INJURIES + TEAM NEWS (per migration 003 — overrides Phase 3 stubs)
-- =========================================================================

CREATE TABLE IF NOT EXISTS injuries (
    team_id         INTEGER NOT NULL REFERENCES teams(team_id),
    player_id       INTEGER,
    player_name     TEXT NOT NULL,
    status          TEXT NOT NULL,
    detail          TEXT,
    return_date     TEXT,
    fetched_utc     TEXT NOT NULL,
    PRIMARY KEY (team_id, player_name)
);
CREATE INDEX IF NOT EXISTS idx_injuries_team   ON injuries(team_id);
CREATE INDEX IF NOT EXISTS idx_injuries_status ON injuries(status);

CREATE TABLE IF NOT EXISTS team_news (
    article_id      TEXT NOT NULL,
    team_id         INTEGER NOT NULL REFERENCES teams(team_id),
    headline        TEXT NOT NULL,
    summary         TEXT,
    category        TEXT,
    published_utc   TEXT NOT NULL,
    url             TEXT,
    fetched_utc     TEXT NOT NULL,
    PRIMARY KEY (article_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_team_news_team_date ON team_news(team_id, published_utc DESC);

-- =========================================================================
-- ODDS SNAPSHOTS (base + migration 002)
-- =========================================================================

CREATE TABLE IF NOT EXISTS odds_snapshots (
    snapshot_id        BIGSERIAL PRIMARY KEY,
    fetched_utc        TEXT NOT NULL,
    game_id            TEXT,
    home_team_id       INTEGER, away_team_id INTEGER,
    bookmaker          TEXT NOT NULL,
    market             TEXT NOT NULL,
    home_price         DOUBLE PRECISION, away_price  DOUBLE PRECISION,
    spread_home        DOUBLE PRECISION, spread_away DOUBLE PRECISION,
    total_line         DOUBLE PRECISION, over_price  DOUBLE PRECISION, under_price DOUBLE PRECISION,
    is_closing         INTEGER NOT NULL DEFAULT 0,
    snapshot_phase     TEXT,
    event_id           TEXT,
    commence_time_utc  TEXT,
    game_date          TEXT
);
CREATE INDEX        IF NOT EXISTS idx_odds_game       ON odds_snapshots(game_id, market, bookmaker);
CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_unique     ON odds_snapshots(event_id, snapshot_phase, bookmaker, market);
CREATE INDEX        IF NOT EXISTS idx_odds_game_phase ON odds_snapshots(game_id, snapshot_phase, bookmaker, market);

CREATE TABLE IF NOT EXISTS odds_event_mapping (
    event_id        TEXT PRIMARY KEY,
    game_id         TEXT,
    home_team_name  TEXT NOT NULL,
    away_team_name  TEXT NOT NULL,
    commence_utc    TEXT NOT NULL,
    created_utc     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_odds_mapping_game ON odds_event_mapping(game_id);

-- =========================================================================
-- TEAM QUARTER SCORES (migration 004)
-- =========================================================================

CREATE TABLE IF NOT EXISTS team_quarter_scores (
    game_id     TEXT    NOT NULL,
    team_id     INTEGER NOT NULL,
    pts_q1      INTEGER,
    pts_q2      INTEGER,
    pts_q3      INTEGER,
    pts_q4      INTEGER,
    pts_ot1     INTEGER,
    pts_ot2     INTEGER,
    pts_ot3     INTEGER,
    pts_ot4     INTEGER,
    pts_total   INTEGER,
    fetched_utc TEXT    NOT NULL,
    PRIMARY KEY (game_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_qs_game ON team_quarter_scores(game_id);
CREATE INDEX IF NOT EXISTS idx_qs_team ON team_quarter_scores(team_id);
