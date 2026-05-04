# Kickoff — Phase 2 (Repo Split)

**Paste this into a new Claude conversation to start the repo split.**

This is a **one-time** thread. When Phase 2 is done, this thread closes.

---

## Who I am

I'm Eddy. Former HKJC Junior Basketball Trader. 5 years sales background. Beginner Python, Mac (Apple Silicon, macOS Sonoma), MS Office basic. Building a basketball podcast on the side.

## How I want you to work with me

- **Direct, no fluff.**
- **Push back when ideas have problems.**
- **Ask clarifying questions before diving in.**
- **No generic advice.**
- **Don't hedge.**
- **Mac-only.**
- **Treat me as someone who knows betting markets deeply** but is a Python beginner.
- **Step-by-step rigor before responding.**
- **Be proactive.**

## What this thread is for

**Phase 2 (Repo Split) ONLY.**

- Split current monorepo into 3 separate repos: nba-data, nba-dashboard, win
- Set up git submodules so nba-dashboard and win share the data layer
- Verify all 3 repos work independently after split

When Phase 2 is done, this thread closes. Future work happens in:
- **basketball thread** (improvements to nba-dashboard)
- **Win thread** (Phase 3+ for betting dashboard)
- **data ops thread** (improvements to nba-data ETL or schema)

Out of scope:
- New features in any dashboard
- Phase 1 data migration (already done before this thread)
- Phase 3+ Win build (next thread after this)

## Prerequisite

Phase 1 (Data Foundation, Supabase migration) must be 100% complete. Verify:
- All ETL writes to Supabase Postgres
- `data/nba.db` is in `.gitignore`, no DB committed
- Existing nba-dashboard pages query Postgres successfully
- Tag `v1.1-postgres-migration` exists in git

If any are NO, go back to data foundation thread first.

## Locked architecture (from roadmap)

```
nba-data/                       Shared data layer
├── infra/migrations/           Schema files
├── ingest/                     ETL scripts (NBA, ESPN, Odds)
├── jobs/                       daily, odds_capture, espn_hourly
├── shared/                     Python lib both dashboards import
└── .github/workflows/          All cron + automation

nba-dashboard/                  Basketball analysis
├── app/                        Streamlit pages
├── lib/                        Imports from nba-data submodule
└── lib/viz/                    Charts, tables, theme

win/                            NEW — empty Streamlit shell (was "betting-dashboard")
├── app/                        Will be filled in Phase 3
├── lib/
└── lib/model/                  Future Compiler models (Phase 3 starts with this)
```

**Sharing pattern: git submodule.** nba-data is added as a submodule under `nba-dashboard/external/nba-data` and `win/external/nba-data`. Both dashboards do `from external.nba_data.shared.db import get_connection`.

**Note: betting dashboard is named "Win".** Repo URL: `https://github.com/alwaystired-24/win`

## What you need from me first thing

Open the conversation by asking me:

1. **Verify Phase 1 done:** `git tag --list` should show `v1.1-postgres-migration`
2. **Confirm Supabase connection works** by running a sample query from Python
3. **Confirm GitHub Actions are green** for at least 24h since Phase 1 completion

Then propose the Phase 2 step plan, get my approval, execute.

## Phase 2 checklist

### 2.1 Create nba-data repo (~1h)
- [ ] Create new GitHub repo `alwaystired-24/nba-data` (private or public, your call)
- [ ] Copy `scripts/`, `sql/`, `.github/workflows/`, `requirements.txt` from current monorepo
- [ ] Create `shared/` folder with read-only DB query helpers — extract read-functions from current `dashboard/lib/data.py`
- [ ] Test `nba-data` standalone: workflows still fire, ETL still works, can query DB from Python
- [ ] Tag `v1.0-data-layer` as first stable release

### 2.2 Refactor nba-dashboard (~1.5h)
- [ ] Add `nba-data` as git submodule under `external/nba-data`
- [ ] Delete `scripts/` and `sql/` from nba-dashboard (now in nba-data)
- [ ] Update `dashboard/lib/data.py` to import from `external.nba_data.shared.db`
- [ ] Verify all pages still work
- [ ] Update README to document submodule init steps
- [ ] Tag `v2.0-post-split` after verification

### 2.3 Create win (~1h)
- [ ] Create new GitHub repo `alwaystired-24/win`
- [ ] Set up basic Streamlit shell: theme + horizontal nav (reuse from nba-dashboard)
- [ ] Add `nba-data` as submodule
- [ ] Add placeholder pages: home, compiler, odds_board, matchup_detail, line_moves, clv_tracker
- [ ] Verify it can connect to Supabase and read data
- [ ] Tag `v0.1-shell` as the empty starting point

### 2.4 Verify isolation (~30min)
- [ ] Make trivial change in nba-data → verify both dashboards see it (after submodule update)
- [ ] Make change in nba-dashboard → verify win unaffected
- [ ] Verify cron-job.org and GitHub Actions all still fire correctly
- [ ] Document submodule update flow in each repo's README

## Definition of done

- 3 working repos on GitHub
- nba-data hosts all ETL + schema; both dashboards depend on it
- nba-dashboard works exactly as before, just with imports refactored
- win runs but is empty (Phase 3 fills it)
- Submodule update flow documented and tested
- All workflows green in nba-data

## Session discipline

- **Cap at 4 hours.**
- **Tag at each sub-phase** (2.1, 2.2, 2.3) for rollback.
- **Don't add features mid-split.** Pure refactor.
- **Don't add ETL features mid-split.** Pure structural work.

## When this thread closes

Phase 2 done = post a final summary including:
- Three repo URLs
- How to update submodules (cheat sheet)
- Status: which workflows fire where, which DB they all connect to

Then I open new threads for ongoing work:
- **basketball thread** for nba-dashboard improvements
- **Win thread** for Phase 3+ build
- **data ops thread** for data layer changes
