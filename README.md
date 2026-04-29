# NBA Dashboard

Local NBA stats database + dashboard for post-game podcast prep.

## Daily workflow

Open Terminal and run these 3 commands:

```bash
cd /Users/edwardlam/Documents/nba-dashboard
source .venv/bin/activate
python -m scripts.run daily
streamlit run dashboard/app.py
```

The dashboard opens at `http://localhost:8501` automatically. To stop it, press
Ctrl+C in Terminal.

## What's in the dashboard

- **Today** — games today and the next 3 days, in HKT
- **Matchup** — pick a game, see form, trends, edge-finder, lineups
- **Team Stats** — 4-layer (Traditional / Advanced / Offence / Defence) for all 30 teams
- **Player Stats** — 4-layer for all players, with team / GP / MPG filters

Click any team or player row to drill down into their last 20 games.

## CLI reference

```bash
python -m scripts.run init              # create DB + seed teams (one-time)
python -m scripts.run schedule          # refresh games table
python -m scripts.run backfill          # ingest box scores for unprocessed games
python -m scripts.run backfill --limit 5   # smoke test
python -m scripts.run daily             # schedule refresh + new-game ingest
python -m scripts.run status            # row counts + last run timestamp
```

## Troubleshooting

**"No database found" on dashboard load** → run `python -m scripts.run init` then
`python -m scripts.run backfill`.

**Daily run shows many failures in a row** → update nba_api:
`pip install --upgrade nba_api`.

**Streamlit shows old data** → press R in the dashboard.

**Updating dependencies after a code pull** → `pip install -r requirements.txt`.
