-- Migration 004: Per-team per-quarter scoring data
-- Adds team_quarter_scores table so we can chart Q-by-Q scoring runs.

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
