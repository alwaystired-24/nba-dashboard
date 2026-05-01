# NBA Dashboard

Local NBA stats database + dashboard for post-game podcast prep and odds compilation.

## Daily workflow

```bash
cd /Users/edwardlam/Documents/nba-dashboard
source .venv/bin/activate
python -m scripts.run daily && streamlit run dashboard/app.py
```

The dashboard opens at `http://localhost:8501`. Press Ctrl+C in Terminal to stop.

## What's in the dashboard

- **Today** — games today, tomorrow, and the next 7 days, grouped by HKT
- **Matchup** — pick a game, see form, trends, edge finder, lineups
- **Team Stats** — 4-layer split (Traditional / Advanced / Offence / Defence) for all 30 teams, with rank toggle (1 = best) and league-average row
- **Player Stats** — 4-layer split for individual players, with percentile toggle (100 = best), team/position/age filters

Click any team or player row to drill into their last 20 games.

## CLI reference

```bash
python -m scripts.run init              # create DB + seed teams (one-time)
python -m scripts.run schedule          # refresh games table only
python -m scripts.run backfill          # ingest box scores for unprocessed games
python -m scripts.run backfill --limit 5   # smoke test
python -m scripts.run daily             # schedule refresh + ingest new finished games
python -m scripts.run demographics      # pull position, age, height for active players
python -m scripts.run status            # row counts + last run timestamp
```

## Project structure

```
nba-dashboard/
├── dashboard/                # Streamlit UI
│   ├── app.py                # Home page
│   ├── lib/                  # shared queries, formatters, filters
│   └── pages/                # 1_Today, 2_Matchup, 3_Team_Stats, 4_Player_Stats
├── scripts/                  # ETL — pulls data from nba_api
│   ├── run.py                # CLI entrypoint
│   ├── etl.py                # box score scrapers (V3 endpoints)
│   ├── demographics.py       # player metadata scraper
│   ├── nba.py                # rate limiting + season utilities
│   └── db.py                 # SQLite helpers
├── sql/schema.sql            # database schema
├── data/nba.db               # the SQLite database (auto-created)
└── requirements.txt
```

## Setup (first time on a new machine)

```bash
# Clone via GitHub Desktop or git clone

cd nba-dashboard
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.run init
python -m scripts.run backfill          # ~30-60 min on first run
python -m scripts.run demographics      # ~10 min one-time
streamlit run dashboard/app.py
```

## Troubleshooting

**`No module named 'matplotlib'` (or any other module)** → activate the venv first: `source .venv/bin/activate`, then `pip install -r requirements.txt`.

**Many ETL failures in a row** → likely an `nba_api` library version drift. Update with `pip install --upgrade nba_api` and re-run.

**Streamlit shows old data after `daily` ETL** → press `R` in the dashboard to clear cache.

**"No database found" on dashboard load** → run `python -m scripts.run init` then `python -m scripts.run backfill`.

**Want to start over from scratch** → `rm data/nba.db` then re-run init + backfill.
