# Kickoff — Phase R + Phase 1 (Data Foundation)

**Paste this into a new Claude conversation to start the data foundation work.**

This is a **one-time** thread. When Phase 1 is done, this thread closes.

---

## Who I am

I'm Eddy. Former HKJC Junior Basketball Trader. Compiled odds, analyzed betting market and customer behavior, prepared game analysis for podcast/social. 5 years sales background. Beginner Python, Mac (Apple Silicon, macOS Sonoma), MS Office basic. Building a basketball podcast on the side.

## How I want you to work with me

- **Direct, no fluff.**
- **Push back when ideas have problems.**
- **Ask clarifying questions before diving in.**
- **No generic advice.**
- **Don't hedge with "it depends."**
- **Mac-only.** No Windows workflows.
- **Treat me as someone who knows betting markets deeply** but is a Python beginner.
- **Step-by-step rigor before responding.**
- **Be proactive.**

## What this thread is for

**Phase R (Recovery) + Phase 1 (Data Foundation) ONLY.**

- Phase R: fix GitHub state from previous sessions, recover any lost data, tag a clean rollback point
- Phase 1: migrate from SQLite-in-git to Supabase Postgres

Out of scope:
- New features in nba-dashboard → basketball thread
- Anything betting/Win-related → Win thread
- Repo split → next thread (Phase 2)
- Discussion about dashboard UX → wrong thread

## Project context

I have a working basketball dashboard at `https://github.com/alwaystired-24/nba-dashboard` built over 38+ hours across 2 days. It uses SQLite committed to git for storage. That architecture corrupted the DB three times in 24 hours due to concurrent workflow writes. Migration to Supabase Postgres is the agreed fix. After migration, I'll split into 3 repos (nba-data, nba-dashboard, win) — but that's the next thread, not this one.

## Locked architecture decisions

- **3 repos planned:** nba-data (shared), nba-dashboard (basketball), win (betting). Phase 2 work, not this thread.
- **Data layer:** Supabase Postgres free tier
- **Sharing pattern:** git submodule for nba-data/shared
- **Cron trigger:** Cron-job.org (already set up, 8 slots/day for odds)
- **Sports scope:** NBA only

## Current technical state

- Repo: `https://github.com/alwaystired-24/nba-dashboard` (PUBLIC, single repo currently)
- Local path: `/Users/edwardlam/Documents/nba-dashboard`
- venv: `.venv` Python 3.12
- DB: SQLite at `data/nba.db`, committed to git (the problem we're fixing)
- Streamlit dashboard: works, ~5 pages
- Workflows: ESPN (hourly), Odds (8x/day via cron-job.org), NBA daily (launchd local)
- The Odds API budget: 500 credits/month, currently using ~496
- ETL scripts: `scripts/etl.py`, `scripts/odds.py`, `scripts/espn.py`, `scripts/quarters.py`, `scripts/run.py`
- Schema: `sql/schema.sql` + 4 migrations under `sql/migrations/`

## What you need from me first thing

Open the conversation by asking me to paste:

1. **What `https://github.com/alwaystired-24/nba-dashboard` shows in browser** — file tree + commit count (we need to know if anything got lost)
2. **Output of:** `cd /Users/edwardlam/Documents/nba-dashboard && git log --oneline origin/main -10 && git status`
3. **Output of:** `sqlite3 data/nba.db "SELECT COUNT(*) FROM team_quarter_scores;" 2>&1`

The third tells you whether the team_quarter_scores backfill survived a merge conflict that was unresolved when we paused.

Then propose Phase R steps, get my approval, execute.

## Phase R checklist

- [ ] Inspect actual GitHub state (browser + git log)
- [ ] Recover team_quarter_scores backfill if lost
- [ ] Verify all yesterday's drops (3.1 through 3.5) are committed and pushed
- [ ] Verify launchd nightly job, cron-job.org slots, and workflows all healthy
- [ ] Tag a clean commit as `v1.0-pre-migration` for rollback safety

## Phase 1 checklist

### 1.1 Supabase setup (~1h)
- [ ] Create Supabase project (free tier)
- [ ] Save connection string + anon key to `.env` and GitHub Secrets
- [ ] Set up local `psql` access from Mac
- [ ] Test connection from Python

### 1.2 Schema port (~2h)
- [ ] Convert SQLite schema/migrations to Postgres syntax
- [ ] Apply schema to Supabase
- [ ] Verify with `\dt`

### 1.3 Data export/import (~2h)
- [ ] Write `scripts/migrate_sqlite_to_pg.py`
- [ ] Run migration end-to-end (~5-15 min)
- [ ] Verify row counts match
- [ ] Backup SQLite as `data/nba.db.pre-postgres-migration`

### 1.4 ETL refactor (~2h)
- [ ] Update `scripts/db.py` for Postgres
- [ ] Update each ETL script's INSERT patterns
- [ ] Test each script in isolation
- [ ] Add `data/nba.db` to `.gitignore`

### 1.5 Workflow refactor (~1h)
- [ ] Update GitHub Actions to use `DATABASE_URL` from secrets
- [ ] Remove all DB commit/push steps from workflows
- [ ] Verify workflows green against Postgres

### 1.6 Dashboard refactor (~1h)
- [ ] Update `dashboard/lib/data.py` to query Postgres
- [ ] Verify all pages render
- [ ] Smoke test full workflow

## Definition of done

- All ETL writes to Postgres
- No data files in git
- Dashboard reads from Postgres
- All workflows green
- Tagged commit `v1.1-postgres-migration` for rollback safety

## Session discipline

- **Cap session at 4 hours.** No marathons.
- **Tag a commit at every phase boundary** for rollback points.
- **Don't expand scope.** New feature ideas → write down for the basketball thread.
- **Verify before pushing.**
- **Stop at first sign of fatigue.**

## When this thread closes

Phase 1 done = post a final summary, then I open a new thread for Phase 2 with that thread's kickoff doc.
