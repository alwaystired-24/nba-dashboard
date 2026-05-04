# Conversation Kickoff Docs

Five purpose-built kickoff documents for starting new Claude conversations on the NBA project.

**Last updated:** 2026-05-04
**Status:** All 11 design decisions locked. Ready to execute.

## How to use

When you open a new Claude conversation, paste the **entire content** of the relevant kickoff doc as your first message. That gives Claude full context for that thread without re-explaining.

## The five threads

| # | File | Type | When to use |
|---|---|---|---|
| 1 | `01-data-foundation-thread.md` | One-time | Phase R recovery + Phase 1 (Supabase migration). Closes when Phase 1 done. |
| 2 | `02-repo-split-thread.md` | One-time | Phase 2 (split monorepo into 3 repos). After Phase 1 done. |
| 3 | `03-basketball-dashboard-thread.md` | Ongoing | All `nba-dashboard` work after split. |
| 4 | `04-win-betting-thread.md` | Ongoing | All `win` (betting dashboard) work — Phase 3+. |
| 5 | `05-data-ops-thread.md` | Ongoing | Data layer: ETL, schema, workflows. |

## Order of operations

```
NOW
  ↓ Save ROADMAP.md + kickoffs to repo
  ↓ Stop tonight
  ↓
Next session
  ↓ Open new conversation, paste 01-data-foundation-thread.md
  ↓ Execute Phase R + Phase 1 (Supabase migration)
  ↓ Tag v1.1-postgres-migration
  ↓ Close that thread
  ↓
Session after
  ↓ Open new conversation, paste 02-repo-split-thread.md
  ↓ Execute Phase 2 (split into 3 repos: nba-data, nba-dashboard, win)
  ↓ Close that thread
  ↓
Ongoing parallel work
  ├── Basketball thread (paste #3) — when working on nba-dashboard
  ├── Win thread (paste #4) — when working on win (betting)
  └── Data ops thread (paste #5) — when adding data sources or fixing ETL
```

## Locked design decisions (summary)

### Architecture
- **3 repos:** `nba-data` (shared data + ETL), `nba-dashboard` (basketball), `win` (betting)
- **Database:** Supabase Postgres (free tier)
- **Sharing:** git submodule pattern
- **Sports scope:** NBA only

### Basketball dashboard (nba-dashboard)
- Combine Home + Today into single landing page
- Edge Finder rebuild: Phase A (top-10 percentile ranks) + Phase B (delta "what changed" view)
- Filter UX: move EVERYTHING into popover (window, season, layer, secondary filters)
- Team Profile + Player Profile NEW pages with `+ Compare` button
- Comparison default: season-only, stat window filter applies
- News categorization: 8 categories, build in Phase 1 (~3h)
- Drop schedule view from current scope
- Top horizontal nav, full-screen layout
- All odds-related sections moved out (to Win)

### Win (betting dashboard)
- **REVISED build order: Compiler FIRST**, then Odds Board / Line Moves / CLV
- Compiler: BOTH detail view (port my Excel) AND summary view (final price + override)
- Daily batch compile of every NBA game
- Manual override field — final = blended model + override
- 6-model stack: Pythagorean Wins, SOS, SRS, Power Rating + Recent Form, Four Factors, Supremacy
- Weights TBD by backtest against my 1500-game historical log
- Pinnacle as sharp anchor (requires Odds API plan upgrade)
- Layouts: Unabated matrix + Goaloo detail + Pinnacle anchor

### Data ops (nba-data)
- Schema migrations append-only, never modify existing
- Backups before destructive ops
- Tables to add for Win: `bets`, `compiled_lines`, `team_advanced_stats`, `team_ratings`, `historical_games_seed`
- Team advanced stats source: NBA stats API (not BBRef)
- Historical Excel data imported as backtest seed

## When threads should reset

Even ongoing threads (3, 4, 5) eventually grow too long. Reset them when:
- Responses feel slower or repeating things
- Claude forgets decisions made earlier in the same thread
- Major scope shift in the conversation

Resetting = open a new Claude conversation and paste the same kickoff doc again.

## Cross-thread coordination

When work touches multiple threads:

- **"Add a new chart that needs a new data column"** → start in **data ops thread** to add the column, then go to basketball/Win thread to build the chart.
- **"Dashboard is broken because schema changed"** → check **data ops thread** for recent migrations, then fix dashboard in its own thread.
- **"Should this go in basketball or Win?"** → bring to planning thread (or just decide using kickoff doc scope sections).

Never dual-purpose a thread. If a request feels like it spans two, redirect explicitly: "That's a data ops change — let's pick this up in that thread."

## Source of truth

`ROADMAP.md` (in project root) is the master plan. These kickoff docs reference it but stay focused on their specific scope. If they conflict, ROADMAP.md wins.

## Maintenance

Update these docs when:
- A locked decision changes
- A phase completes (mark done)
- A new thread becomes necessary
- The "current state" section drifts from reality

Keep these in version control. Save to repo root or `docs/` folder.
