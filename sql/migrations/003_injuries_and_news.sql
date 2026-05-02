-- Phase 7: Injuries + Team News from ESPN
--
-- Both tables are "snapshot" tables: each refresh deletes-then-inserts,
-- because ESPN's data is current state, not historical.

-- =========================================================================
-- INJURIES — current league-wide injury report (refreshed every 4h)
-- =========================================================================
CREATE TABLE IF NOT EXISTS injuries (
    team_id         INTEGER NOT NULL,
    player_id       INTEGER,                    -- nullable: ESPN may have player not in our DB
    player_name     TEXT NOT NULL,              -- always have name
    status          TEXT NOT NULL,              -- 'Out', 'Day-To-Day', 'Doubtful', 'Probable', 'Questionable', 'Suspended', etc.
    detail          TEXT,                       -- e.g., "Knee surgery, expected return mid-May"
    return_date     TEXT,                       -- ISO date if ESPN provides one
    fetched_utc     TEXT NOT NULL,
    PRIMARY KEY (team_id, player_name),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE INDEX IF NOT EXISTS idx_injuries_team ON injuries(team_id);
CREATE INDEX IF NOT EXISTS idx_injuries_status ON injuries(status);

-- =========================================================================
-- TEAM_NEWS — latest news headlines per team (refreshed every 4h)
-- =========================================================================
CREATE TABLE IF NOT EXISTS team_news (
    article_id      TEXT NOT NULL,              -- ESPN article ID for dedup
    team_id         INTEGER NOT NULL,
    headline        TEXT NOT NULL,
    summary         TEXT,
    category        TEXT,                       -- e.g., 'NBA', 'Trade', 'Injury' if classifiable
    published_utc   TEXT NOT NULL,
    url             TEXT,                       -- link back to ESPN article
    fetched_utc     TEXT NOT NULL,
    PRIMARY KEY (article_id, team_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE INDEX IF NOT EXISTS idx_team_news_team_date ON team_news(team_id, published_utc DESC);
