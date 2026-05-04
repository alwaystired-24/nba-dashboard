# NBA Project — Locked Roadmap v3

**Owner:** Eddy
**Locked:** 2026-05-04
**Status:** Active — Phase R next session

---

## Vision

A two-dashboard system on a shared data foundation. Built for syndicate-grade work, sized for personal use. Designed to scale to a real edge-finding operation without architectural rework.

- **Basketball analysis** → `nba-dashboard` — podcast prep, narrative analysis, trend storytelling
- **Betting/trading** → `win` (renamed from "betting-dashboard") — line shopping, market moves, CLV tracking, model vs market deltas
- **Data ingestion** → `nba-data` — ETL + schema, shared by both dashboards

This separation mirrors how real syndicates operate: data ops, trading tools, and content/research are different teams with different priorities.

---

## Architecture

```
nba-data/                       Postgres (Supabase) + ETL + automation
├── infra/migrations/           Schema files (versioned, append-only)
├── ingest/                     NBA stats, ESPN, Odds API, future sources
├── jobs/                       daily, odds_capture, espn_hourly
├── shared/                     Python lib both dashboards import (git submodule)
└── .github/workflows/          All cron + automation lives here

nba-dashboard/                  Basketball analysis
├── app/                        Streamlit pages
│   ├── home_today.py           MERGED landing page (Home + Today combined)
│   ├── matchup.py              Per-game deep dive (Edge Finder rebuilt)
│   ├── team_stats.py           Team-level table/chart
│   ├── player_stats.py         Player-level table/chart
│   ├── team_profile.py         NEW — team deep dive + Compare button
│   └── player_profile.py       NEW — player deep dive + Compare button
├── lib/                        Imports from nba-data submodule
└── lib/viz/                    Charts, tables, theme

win/                            Betting/trading view (formerly "betting-dashboard")
├── app/
│   ├── home.py                 Landing — slate summary + alerts + CLV stats
│   ├── compiler.py             FIRST — Port my Excel Compiler workflow
│   ├── odds_board.py           Unabated-style matrix
│   ├── matchup_detail.py       Goaloo-style drill-down
│   ├── line_moves.py           Move detection + alerts
│   └── clv_tracker.py          Manual bet entry + CLV calc
├── lib/
│   ├── data.py                 Imports from nba-data submodule
│   └── model/                  6-model Compiler stack
│       ├── pythagorean.py
│       ├── sos.py
│       ├── srs.py
│       ├── power_rating.py
│       ├── four_factors.py
│       └── supremacy.py
└── lib/backtest/               Backtest framework (against 1500-game seed)
```

### Data layer: Supabase Postgres
- Free tier: 500 MB DB, 5 GB bandwidth — plenty for years of NBA data
- No more git-merge corruption — Postgres handles concurrent writes natively
- Both dashboards connect via `psycopg2` over connection string
- GitHub Actions workflows write directly to Supabase, no DB-in-git
- Cron-job.org continues triggering workflows

---

## Locked design decisions (consolidated)

### Architecture (3)
| # | Decision | Rationale |
|---|---|---|
| 1 | **3 repos:** nba-data, nba-dashboard, win | Independent deployment, schema independence, access separation |
| 2 | **Supabase Postgres** | SQLite-in-git corrupted 3x in 24h |
| 3 | **NBA only scope** | Stay focused; Asian leagues = Phase 5+ |

### Basketball dashboard (8)
| # | Decision | Rationale |
|---|---|---|
| 4 | **Merge Home + Today** into single landing page | Currently overlap, today's prep is the real landing experience |
| 5 | **Edge Finder rebuild: Phase A + B** | Top 10 percentile ranks vs league avg, then "what changed" delta view |
| 6 | **Move EVERYTHING into filter popover** | Cleanest UI, accept the 1-click cost |
| 7 | **Team/Player Profile pages with `+ Compare` button** | 1 or 2 entity comparison; default season-only with stat window applied |
| 8 | **News categorization (8 cats) in Phase 1** | ~3h, use ESPN's category field if available |
| 9 | **Drop Schedule view from current scope** | Not compulsory now |
| 10 | **Top horizontal nav, full-screen** | Already built; full canvas for info density |
| 11 | **Move all odds sections to Win** | Basketball dashboard becomes purely about basketball |

### Win betting dashboard (10)
| # | Decision | Rationale |
|---|---|---|
| 12 | **Renamed to "Win"** (was "betting-dashboard") | Eddy's preference |
| 13 | **REVISED build order: Compiler FIRST**, then Odds Board / Line Moves / CLV | Port proven Excel work first; build discovery features after |
| 14 | **Compiler has BOTH detail + summary view** | Detail = port my Excel; Summary = final price + override |
| 15 | **Daily batch compile** of every NBA game | Wake up, see edges across slate |
| 16 | **Manual override field** — final = blended model + override | Keep my workflow, structure the data |
| 17 | **6-model stack** (port from my Excel) | Pythagorean Wins, SOS, SRS, Power Rating + Recent Form, Four Factors, Supremacy |
| 18 | **Weights from backtest** against 1500-game historical log | Don't lock weights from intuition |
| 19 | **Layouts: Unabated matrix + Goaloo detail + Pinnacle anchor** | Trader-grade primary; familiar drill-down; sharp benchmark |
| 20 | **Manual bet entry only** for CLV | MVP-appropriate; CSV import = Phase 4+ |
| 21 | **Pinnacle integration** (requires Odds API plan upgrade) | Sharp benchmark column; budget decision deferred to Win kickoff |

### Data ops (3)
| # | Decision | Rationale |
|---|---|---|
| 22 | **NBA stats API for team advanced stats** (not BBRef) | Already integrated, all Four Factor stats available |
| 23 | **Append-only schema migrations** | Never modify existing migrations |
| 24 | **Import 1500-game historical Excel as backtest seed** | Bootstrap Compiler weight tuning |

---

## Phase plan

### Phase R — Recovery (~2h, next session)

Fix current GitHub mess. No features.

- [ ] Inspect actual GitHub state (browser + git log)
- [ ] Recover team_quarter_scores backfill if lost
- [ ] Verify drops 3.1-3.5 committed and pushed
- [ ] Verify launchd job, cron-job.org slots, workflows all healthy
- [ ] Tag clean commit as `v1.0-pre-migration`

### Phase 1 — Data Foundation (~6-8h)

Migrate to Supabase. After: no more SQLite-in-git.

- [ ] Supabase setup (~1h)
- [ ] Schema port from SQLite to Postgres syntax (~2h)
- [ ] Data export/import migration script + run (~2h)
- [ ] ETL refactor — `db.py`, INSERT patterns, scripts (~2h)
- [ ] Workflow refactor — DATABASE_URL, no DB commits (~1h)
- [ ] Dashboard refactor — query Postgres (~1h)
- Tag `v1.1-postgres-migration` when done

### Phase 2 — Repo Split (~4h)

Split into 3 repos.

- [ ] Create `nba-data` repo, copy ETL + schema, tag `v1.0-data-layer`
- [ ] Refactor `nba-dashboard` to use submodule, tag `v2.0-post-split`
- [ ] Create `win` repo with Streamlit shell, tag `v0.1-shell`
- [ ] Verify isolation: changes in one don't break others

### Phase 3 — Win MVP (~14-18h, REVISED ORDER)

#### 3a — Win infrastructure + Compiler (FIRST, ~6-8h)
- [ ] Streamlit shell, theme, top nav
- [ ] Schema migrations (data ops): `team_advanced_stats`, `team_ratings`, `compiled_lines`, `historical_games_seed`
- [ ] ETL: NBA stats API team advanced stats (data ops)
- [ ] Import 1500-game historical Excel (data ops)
- [ ] Implement 6-model stack in `win/lib/model/`
- [ ] Compiler page: detail view (port Excel layout)
- [ ] Compiler page: summary view (final price + manual override)
- [ ] Daily batch compile job (data ops or Win-side)
- [ ] Backtest framework, tune initial weights

#### 3b — Odds Board (Unabated matrix, ~3h)
- [ ] Pinnacle integration (data ops, requires Odds API plan upgrade)
- [ ] Matrix layout, books, markets, color-coded moves
- [ ] Sortable, filterable

#### 3c — Matchup Detail (Goaloo-style, ~2h)
- [ ] Reuse existing Goaloo cards from old nba-dashboard
- [ ] Multi-book line chart per market

#### 3d — Line Moves (~2h)
- [ ] Move detection logic, threshold defaults
- [ ] Alerts page, steam-move flag
- [ ] Click-through to Matchup Detail

#### 3e — CLV Tracker (~3h)
- [ ] Bet entry form
- [ ] Schema migration: `bets` table (data ops)
- [ ] CLV calc on settlement
- [ ] Aggregate stats panel

### Phase 4 — Compiler Improvements (10h+)

- [ ] Refine model weights via continuous backtest
- [ ] Add HCA per-team (currently constant)
- [ ] Injury impact modeling (currently free-form)
- [ ] Per-model toggle (disable models for specific games)
- [ ] Edge alert thresholds tuning

### Phase 5 — Polish & Deploy (~4h)

- [ ] Deploy both dashboards (Streamlit Cloud or Railway)
- [ ] Slack webhook for line move alerts
- [ ] Email digest of daily CLV summary
- [ ] Mobile-friendly views

---

## Time budget

| Phase | Estimate | Cumulative |
|---|---|---|
| R Recovery | 2h | 2h |
| 1 Data Foundation | 6-8h | 8-10h |
| 2 Repo Split | 4h | 12-14h |
| 3 Win MVP (Compiler-first) | 14-18h | 26-32h |
| 4 Compiler Improvements | 10h+ | 36-42h+ |
| 5 Polish & Deploy | 4h | 40-46h+ |

**Realistic cadence (4-6h per weekend):**
- Phase R + Phase 1: weekend 1 (next)
- Phase 2: weekend 2
- Phase 3a (Compiler): weekends 3-4
- Phase 3b-e (other Win pages): weekends 5-6
- Basketball dashboard improvements parallel to all of above

---

## Lessons learned

1. **SQLite in git doesn't survive concurrent writes.** Three corruptions in 24h. Postgres is non-negotiable.
2. **"Stop building" without a clear rollback point is worthless.** Every phase tags a clean commit.
3. **Schema migrations on a tired brain cause bugs that cost more than the migration.** Migrations only at start of session.
4. **Building two products in one app made both worse.** Hence the split.
5. **Multi-hour marathons produce code that next-day-me regrets.** Cap sessions at 4h.
6. **Build proven things first.** Hence: Compiler before Odds Board.

---

## Out of scope (deliberate)

- Asian basketball leagues (CBA, KBL, B.League) — Phase 5+
- NFL / MLB — never
- Sharp/public splits (Action Network) — Phase 5+
- Live in-game odds — Phase 5+
- Player props markets — Phase 4+
- Parlays / prop trees — much later
- Discord/Twitter integration — separate project
- Podcast script generation — separate project

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Supabase free tier limits exceeded | Low | Medium | Monitor row counts; ~5M rows fits 500MB |
| The Odds API rate limit hit | High | Medium | Already at 496/500; upgrade plan when adding Pinnacle |
| NBA stats API rate limit | Medium | High | Already broken once via Azure IP; consider local-only ETL |
| Cron-job.org outage | Low | Low | GitHub native cron as standby |
| Postgres migration data loss | Medium | High | Backup SQLite before, verify row counts after |
| 6-model Compiler weights overfit to 1500-game seed | Medium | Medium | Hold out test set; track live performance after deployment |
| Compiler doesn't beat market closing line MAE | Possible | Low | Fallback to manual workflow; ports my Excel exactly |

---

## Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-03 | SQLite in git is the architecture | Initial, didn't anticipate concurrent writes |
| 2026-05-04 | Migrate to Supabase Postgres | 3 corruptions in 24h |
| 2026-05-04 | Split into 3 repos | Two dashboards = two products = clean separation |
| 2026-05-04 | Unabated matrix as primary betting view | Trader-grade density |
| 2026-05-04 | NBA-only scope | Stay focused |
| 2026-05-04 | Manual bet entry, no CSV import | MVP-appropriate |
| 2026-05-04 | Merge Home + Today | Functional overlap, prep view is the real landing |
| 2026-05-04 | Edge Finder rebuild (Phase A + B) | Top-10 percentile + delta detection = real edge work |
| 2026-05-04 | Filter popover for everything | Clean UI, accept the click |
| 2026-05-04 | Compare button on profiles | 1 or 2 entity comparison flexibly |
| 2026-05-04 | News categorization in Phase 1 | Faster prep |
| 2026-05-04 | Win Compiler: detail + summary view | Both prep and trading workflows supported |
| 2026-05-04 | Daily batch compile | Predictable, scalable |
| 2026-05-04 | Manual override field | Keep my workflow, structure the data |
| 2026-05-04 | Rename betting-dashboard to "Win" | Eddy's preference |
| 2026-05-04 | Build order swap: Compiler first | Port proven work before discovery features |
| 2026-05-04 | 6-model stack | Add Pythagorean Wins, SOS, Supremacy back from older workbook |
| 2026-05-04 | Import 1500-game Excel as seed | Backtest bootstrap |
| 2026-05-04 | NBA stats API for team advanced stats | Already integrated, no new scraper |

---

*This document is the source of truth. Update it when decisions change. Don't change scope mid-phase.*
