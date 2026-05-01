-- Migration 002: extend odds_snapshots for The Odds API integration
-- Idempotent — uses ALTER TABLE IF NOT EXISTS pattern via try/except in code
-- Run via: python -m scripts.run odds_init

-- Phase columns
ALTER TABLE odds_snapshots ADD COLUMN snapshot_phase TEXT;
ALTER TABLE odds_snapshots ADD COLUMN event_id TEXT;
ALTER TABLE odds_snapshots ADD COLUMN commence_time_utc TEXT;
ALTER TABLE odds_snapshots ADD COLUMN game_date TEXT;

-- Unique constraint via index — prevents duplicate snapshots
-- (one row per game/phase/book/market combo)
CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_unique
    ON odds_snapshots (event_id, snapshot_phase, bookmaker, market);

-- Lookup index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_odds_game_phase
    ON odds_snapshots (game_id, snapshot_phase, bookmaker, market);

-- The Odds API event_id <-> nba_api game_id mapping
-- Built up by matching team names + commence_time
CREATE TABLE IF NOT EXISTS odds_event_mapping (
    event_id        TEXT PRIMARY KEY,                  -- The Odds API's game id
    game_id         TEXT,                              -- nba_api's game_id (nullable - may not match)
    home_team_name  TEXT NOT NULL,
    away_team_name  TEXT NOT NULL,
    commence_utc    TEXT NOT NULL,
    created_utc     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_odds_mapping_game ON odds_event_mapping(game_id);
