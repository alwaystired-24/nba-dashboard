# NBA Dashboard

A local NBA stats database + dashboard for post-game trend analysis.
Phase 1 ships the data foundation — Phases 2–6 add automation, UI, and odds.

## What's in Phase 1

A working SQLite database that pulls **every game's box score** for the current
NBA season, both traditional and advanced, for teams and players. The schema
already has stubs for shot data, play-by-play, defensive matchups, refs, and
odds — those get populated in Phase 5/6.

Files you care about:

```
nba-dashboard/
├── sql/schema.sql           # the database schema
├── scripts/
│   ├── db.py                # SQLite helpers
│   ├── nba.py               # rate limiting + season utilities
│   ├── etl.py               # the actual scrapers
│   └── run.py               # CLI entrypoint (you run this)
├── data/                    # nba.db will live here after first init
├── requirements.txt
└── README.md
```

## One-time setup (Mac)

You need Python 3.10+ (built-in on macOS Sonoma+, otherwise install via
Homebrew: `brew install python@3.12`).

```bash
cd ~/path/to/nba-dashboard

# Create an isolated environment so this project doesn't pollute system Python
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize the database (creates data/nba.db, seeds 30 teams)
python -m scripts.run init
```

Expected output:
```
Schema applied. Seeded 30 teams. Current season: 2025-26
```

## First backfill — current season

This pulls the schedule and box scores for every completed game so far.
At ~0.6 sec per request and 4 endpoints per game, expect roughly **~25–35
minutes per 1000 games**. Late-season backfill is the biggest hit; from here
on, daily updates take ~1 minute.

```bash
# Make sure the venv is active: `source .venv/bin/activate`
python -m scripts.run backfill
```

You'll see progress every 25 games. If the NBA endpoint flakes out (it will
occasionally — it's an unofficial API), the script retries with backoff and
records failures to the `etl_runs` table so the next run picks them up.

To dry-run with a small sample first:
```bash
python -m scripts.run backfill --limit 5
```

## Daily refresh (manual for now, automated in Phase 2)

```bash
source .venv/bin/activate
python -m scripts.run daily
```

This refreshes the schedule and ingests anything that finished since the
last run. Safe to run any number of times — uses `INSERT … ON CONFLICT
DO UPDATE` everywhere.

## Quick health check

```bash
python -m scripts.run status
```

Shows row counts in every table plus the timestamp of the last scrape.

## Querying the data

The DB is just `data/nba.db`. Open it however you want — for ad-hoc poking
around, the `sqlite3` CLI is built into macOS:

```bash
sqlite3 data/nba.db
sqlite> .schema games
sqlite> SELECT COUNT(*) FROM team_box_traditional;
sqlite> .quit
```

For visual browsing I'd recommend [DB Browser for SQLite](https://sqlitebrowser.org/)
(free, Mac-native).

Example query — last 10 LAL games, off and def rating:
```sql
SELECT g.game_date,
       (SELECT abbreviation FROM teams WHERE team_id = g.home_team_id) AS home,
       (SELECT abbreviation FROM teams WHERE team_id = g.away_team_id) AS away,
       a.off_rating, a.def_rating, a.pace
FROM team_box_advanced a
JOIN games g ON g.game_id = a.game_id
JOIN teams t ON t.team_id = a.team_id
WHERE t.abbreviation = 'LAL' AND g.status = 'Final'
ORDER BY g.game_date DESC
LIMIT 10;
```

## What's NOT in Phase 1 (coming next)

- **Phase 2**: GitHub Actions workflow that runs `daily` automatically every
  morning HKT and pushes the updated `nba.db` back to the repo so your Mac
  pulls fresh data when you open the dashboard.
- **Phase 3**: Streamlit dashboard — Today's Games (HKT), Matchup view,
  Team Stats with the 4-layer toggle.
- **Phase 4**: Player stats page + L5/L10/L20/season form toggles.
- **Phase 5**: Shot zones, play-by-play, defensive matchups, ref data.
- **Phase 6**: Odds API integration — go-forward closers + historical pulls.

## Troubleshooting

**`ModuleNotFoundError: No module named 'nba_api'`** — your venv isn't
activated. Run `source .venv/bin/activate` before any `python` command.

**`Read timed out` errors during backfill** — normal. The script retries 4×
with backoff. If a game keeps failing, it's logged to `etl_runs` with
`status='failed'` and the next `daily` or `backfill` run will retry it.

**Backfill seems stuck** — it's just rate-limited (0.6s/request). Check the
progress lines that print every 25 games.

**Want to start over from scratch** — delete `data/nba.db` and re-run
`python -m scripts.run init`.
