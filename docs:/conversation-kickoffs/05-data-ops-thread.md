# Kickoff — Data Ops (nba-data)

**Paste this into a new Claude conversation to start work on the data layer.**

This thread is **ongoing** — bring it up whenever you need to add data sources, change the schema, fix ETL bugs, or improve automation.

---

## Who I am

I'm Eddy. Former HKJC Junior Basketball Trader. 5 years sales background before that. Beginner Python, Mac (Apple Silicon, macOS Sonoma), MS Office basic. Building a basketball podcast on the side.

## How I want you to work with me

- **Direct, no fluff.**
- **Push back when ideas have problems.**
- **Treat me as someone who knows betting markets and basketball deeply** but is a Python beginner.
- **Don't hedge.** Give your actual recommendation.
- **Mac-only.**
- **Step-by-step rigor before responding.**
- **Be proactive about edge cases** — NULL handling, schema migrations on live DB, race conditions.
- **Push back on schema changes** that risk breaking dashboards.

## What this thread is for

**nba-data ONLY.** The shared data layer powering both dashboards.

In scope:
- New ETL scripts (new data sources, new endpoints)
- Schema migrations (add tables, columns, indexes)
- Workflow changes (cron schedules, GitHub Actions YAML)
- ETL bug fixes
- Data quality checks
- Performance optimization
- Backfill scripts

Out of scope:
- Dashboard UI/UX → wrong thread
- Charts, tables, filters → wrong thread
- Anything that doesn't write to or read from the database directly

## Project context

`nba-data` is the shared data layer. ETL scripts pull from external APIs, write to Supabase Postgres. Both dashboards (basketball + Win) read from it via `shared/` Python library imported as a git submodule.

**Repo:** `https://github.com/alwaystired-24/nba-data`
**Local path:** `/Users/edwardlam/Documents/nba-data`
**Database:** Supabase Postgres (free tier, ~500 MB cap)
**Connection:** `DATABASE_URL` env var (from `.env` locally, GitHub Secrets in CI)
**Stack:** Python 3.12, psycopg2, nba_api, requests

## Locked architecture

- **Supabase Postgres** — single source of truth
- **Schema versioning** via `infra/migrations/` — append-only, never modify existing migrations
- **All workflows live here.** Both dashboard repos have ZERO `.github/workflows/*.yml` files.
- **Cron-job.org** triggers odds workflows (8 slots/day for NBA odds)
- **launchd local Mac job** runs nightly NBA daily ETL (NBA stats blocks Azure IPs)
- **No data files in git ever.** SQLite-in-git was the original sin; never repeat.

## Current data sources

- **NBA stats** (via `nba_api`) — schedule, box scores, line scores. Rate-limited.
- **ESPN** — injuries + team news. Hourly via GitHub Actions.
- **The Odds API** — odds from DraftKings + FanDuel. 500 credits/month. Currently using ~496.
- **Future:** Pinnacle (will add as Win builds — region: eu). Budget impact below.

## Tables in DB (current)

- `teams`, `players`, `games` — core entities
- `team_box_traditional`, `team_box_advanced` — team game stats
- `player_box_traditional`, `player_box_advanced` — player game stats
- `team_quarter_scores` — Q-by-Q scoring
- `injuries`, `team_news` — ESPN data
- `odds_snapshots`, `odds_event_mapping` — odds + event ID mapping
- `etl_runs` — log of every ETL run
- Stubs (defined but empty): `shots`, `play_by_play`, `defensive_matchups`, `officials_per_game`

## Tables to add (Win project — locked but not built)

These will be requested as Win builds — design discussion before each:

### `bets`
Manual bet entry from Win CLV Tracker. Schema sketch:
```sql
bet_id BIGSERIAL PRIMARY KEY,
placed_utc TIMESTAMPTZ NOT NULL,
game_id TEXT REFERENCES games(game_id),
market TEXT NOT NULL,        -- 'spread' | 'total' | 'moneyline'
side TEXT NOT NULL,          -- 'home' | 'away' | 'over' | 'under'
line NUMERIC,                -- handicap or total
odds NUMERIC NOT NULL,       -- decimal odds at time of bet
stake NUMERIC NOT NULL,      -- units staked
book TEXT NOT NULL,          -- DK, FD, Pinnacle, etc.
notes TEXT,
result TEXT,                 -- 'win' | 'loss' | 'push' | 'pending'
profit_loss NUMERIC,         -- computed after settlement
clv_basis_points NUMERIC,    -- computed: (your_odds vs closing line) in bp
closing_line NUMERIC         -- snapshot of closing line for CLV calc
```

### `compiled_lines`
Daily Compiler output per game per market. Schema sketch:
```sql
compile_id BIGSERIAL PRIMARY KEY,
game_id TEXT REFERENCES games(game_id),
compiled_utc TIMESTAMPTZ NOT NULL,
market TEXT NOT NULL,        -- 'spread' | 'total' | 'moneyline'
model_a_value NUMERIC,        -- Pace × oEFF projection
model_b_value NUMERIC,        -- Power Rating Spread
model_c_value NUMERIC,        -- SRS Spread
compiler_value NUMERIC,       -- weighted blend
manual_override NUMERIC,      -- my adjustment
final_value NUMERIC,          -- compiler + override
edge_vs_market NUMERIC,       -- delta from current market
weights_used JSONB,           -- track which weights were applied
notes TEXT
```

### `team_advanced_stats`
Source: NBA stats API (not Basketball-Reference per locked decision). Stats needed by 6-model stack:
- ORtg, DRtg, NRtg, Pace
- eFG%, TOV%, ORB%, FT/FGA (Four Factors — offense)
- oEFG%, oTOV%, DRB%, oFT/FGA (Four Factors — defense)
- SRS, MOV, SOS

Update frequency: weekly during regular season, daily during compressed schedules. Decide pace at build time.

### `team_ratings`
Materialized view (or just a table refreshed nightly). Output of the 6 models per team:
- Pythagorean W%
- SOS-adjusted rating
- SRS
- Power Rating (Season Margin)
- Recent Form (30-day)
- Four Factors composite
- Supremacy (closing-line-derived)
- ★ Compiler Rating (weighted blend, weights TBD by backtest)

### `historical_games_seed`
One-time import of my 1500-game Excel historical log. Used as backtest seed for tuning Compiler weights. Schema mirrors `games` + `odds_snapshots` simplified to (open_hcap, open_total, close_hcap, close_total, sharp_signal, q1-q4 scores).

## Common requests on this thread

### Adding a new data source
1. Discuss feasibility, budget impact, rate limits
2. Propose schema additions
3. Write migration file in `infra/migrations/00X_description.sql`
4. Write ingest script in `ingest/<source>/`
5. Test locally with `--limit 5` smoke test
6. Verify row counts + integrity
7. Add to `jobs/daily.py` or new dedicated job + workflow
8. Run full backfill if applicable
9. Update `shared/db.py` read helpers if dashboards need access
10. Notify both dashboard threads

### Schema change (existing table)
1. Discuss what breaks (which queries, which dashboards)
2. **Append-only:** ADD COLUMN, ADD INDEX (no DROP, no rename, no type change)
3. Write migration file
4. Apply to Supabase: `psql $DATABASE_URL -f infra/migrations/00X_description.sql`
5. Verify with `\d <table>` in psql
6. Update `shared/db.py` if applicable
7. Tag commit with migration version

### ETL bug fix
1. Reproduce locally
2. Patch
3. Test against single edge-case input
4. Push, verify next workflow run is green
5. If data was corrupted, write re-fetch script, run, verify

## What lives in `shared/`

Python lib both dashboards import. **Read-only against Postgres.** Don't put dashboard logic here.

- `shared/db.py` — connection helper, returns psycopg2 connection
- `shared/queries/` — query builders by table
  - `games.py`, `boxes.py`, `odds.py`, `injuries.py`, `teams.py`, `players.py`
  - (Win-related, when added) `bets.py`, `compiled_lines.py`, `ratings.py`
- `shared/models.py` — type hints / dataclasses (optional, defer)

Convention: every function is read-only, returns a pandas DataFrame or dict. Never writes.

## Hard rules — never violate

- **Never edit a migration that's been applied.** Append a new one.
- **Never DROP a column without 2-week deprecation.**
- **Never modify a primary key on existing table.**
- **Never restore over a live DB without confirming.**
- **Never store secrets in code.** Always `os.getenv("DATABASE_URL")`.
- **Always backup before destructive operations** — `pg_dump` to `data/backups/<date>.sql`, gitignored.

## What you need from me first thing

When I open a new conversation, I'll bring:

**A. New data request:** "Capture X." Discuss feasibility, cost, schema impact. Then plan.

**B. Bug:** "Workflow Z is failing." Look at logs, diagnose, fix.

**C. Schema change:** "I need column X on table Y." Discuss, write migration, apply.

**D. Performance issue:** "Query Z is slow." EXPLAIN ANALYZE, propose index/query change.

In all cases:
1. Confirm you've read this kickoff doc
2. Ask clarifying questions before changing anything
3. Show migration / script plan before executing
4. **Always backup before destructive changes**

## Out of scope (deliberate)

- Asian basketball leagues — Phase 5+
- NFL / MLB — never
- Live in-game odds (WebSocket) — Phase 5+
- Sharp/public scraping (Action Network) — Phase 5+

## Reference

If broader context needed, reference `ROADMAP.md` in project root.
