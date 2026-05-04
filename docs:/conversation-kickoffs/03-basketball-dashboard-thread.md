# Kickoff — Basketball Dashboard (nba-dashboard)

**Paste this into a new Claude conversation to start work on the basketball dashboard.**

This thread is **ongoing** — bring it up whenever you want to add features, fix bugs, or improve the basketball dashboard.

---

## Who I am

I'm Eddy. Former HKJC Junior Basketball Trader (one of the world's largest sports bookmakers). Compiled odds, analyzed betting market and customer behavior, prepared game analysis for podcast/social. 5 years sales background. Beginner Python, Mac (Apple Silicon, macOS Sonoma), MS Office basic. Building a basketball podcast on the side.

## How I want you to work with me

- **Direct, no fluff.** Get to the point.
- **Push back when ideas have problems.**
- **Ask clarifying questions before diving in.**
- **No generic advice.** Specific to my situation.
- **Don't hedge with "it depends."** Give your actual recommendation.
- **Mac-only.** No Windows workflows.
- **Treat me as someone who knows basketball deeply.** Don't over-explain basketball/betting concepts; do explain code patterns when introducing new ones.
- **Step-by-step rigor before responding.**
- **Be proactive.** Suggest improvements you spot.
- **Push back when I'm scope-creeping.** I will. Stop me.

## What this thread is for

**nba-dashboard ONLY.** Basketball analysis, podcast prep, narrative views.

In scope:
- New pages, charts, tables in `nba-dashboard`
- Bug fixes in basketball views
- Refining existing views
- Stats methodology questions

Out of scope:
- Anything betting/odds → goes to **Win thread** (betting dashboard)
- ETL changes → goes to **data ops thread**
- Repo split, infrastructure → done in earlier threads
- Cross-cutting changes (data → both dashboards) → start in data ops thread

## Project context

`nba-dashboard` is a Streamlit app for basketball analysis. Reads from Supabase Postgres via the `nba-data` submodule. Audience: me, for podcast prep.

**Repo:** `https://github.com/alwaystired-24/nba-dashboard` (post-split)
**Local path:** `/Users/edwardlam/Documents/nba-dashboard`
**Data layer:** Supabase Postgres, accessed via `external/nba-data/shared/db.py` submodule
**Stack:** Python 3.12, Streamlit ≥1.32, Plotly, pandas, psycopg2

## Locked design decisions (from planning thread, 2026-05-04)

### Page structure (final)

| Page | Status | Notes |
|---|---|---|
| **Home + Today (merged)** | Combined into single landing page | Drop the tile-shell Home; landing = today's prep view |
| Matchup | Keep, declutter | Reorder for prep flow; remove all odds sections (move to Win) |
| Team Stats | Keep | Reference: basketball-reference.com/leagues/NBA_2026.html |
| Player Stats | Keep | Reference: basketball-reference.com/leagues/NBA_2026_per_game.html |
| Team Profile | NEW | + Compare button for 2-team comparison |
| Player Profile | NEW | + Compare button for 2-player comparison |
| Schedule view | DEFER | Not compulsory now |

### Filter UX (final)

**Move EVERYTHING into the filter popover.** Window, season, layer, secondary filters all behind one button. Cleanest UI.

This applies to Team Stats, Player Stats. Filter popover lives in the top-right of each page.

### Edge Finder rebuild (Phase A + B)

Replace the current "Team A vs Team B index comparison" with two phases:

**Phase A — Top 10 percentile ranks vs league average**
- Pull the top 10 stats where each team ranks highest in the league under the chosen window
- Cover both general stats (PTS, REB, AST, etc.) and advanced stats (possessions/game, 3PA/game, points allowed in paint, etc.)
- Use percentile ranks so different stat units are comparable
- Display as a clean ranked list per team

**Phase B — "What changed" delta view**
- Same team's current window vs previous window
- Surface the biggest deltas (this team's pace went from 98 to 102 over the last 10 → flag it)
- Identifies real edges from style-of-play shifts mid-season

Both views support both general and advanced stats. Any statline qualifies.

### Comparison mode

`+ Compare` button on Team Profile and Player Profile. When clicked, page splits into 2-team / 2-player view.

Comparison defaults:
- **Default scope:** season-only (compare full-season averages)
- **Stat window filter applied:** the active window persists into the comparison view
- Side-by-side layout with delta indicators in center

### News categorization (Phase 1, ~3h)

Replace the flat news dump with categorized news. Use ESPN's `category` field if available; fall back to keyword classification.

**Categories:**
- 🏥 Injury/Health — direct line move trigger
- 🔄 Roster Move — trades, signings, waivers, G-League calls
- 👥 Coaching/Front Office — staff changes, suspensions, firings
- 🚨 Personal/Off-court — domestic, legal, social issues
- 📈 Team Performance — win streaks, blowouts, milestones
- 📰 Game Preview/Recap — daily preview/recap content (low signal)
- 💬 Speculation/Rumor — "reports suggest", "source says"
- 📋 League/Rules — schedule changes, rule updates

### Layout convention

Top horizontal nav bar (already built). Use full screen width — no centered narrow content blocks. All info lives in the main canvas.

### Other locked decisions

- Odds-related sections **deleted from all basketball pages** (move to Win)
- Schedule view dropped from current scope (not compulsory)
- Lead tracker / play-by-play deferred (decide later — biggest single ETL build, low immediate ROI for podcast)

## Theme + visual conventions

- **Theme:** Deep navy (#0E1525) + amber (#F4A742) + warm white text (#E5E9F0). Diverging color: green (#5FBE85) → amber → red (#E37070).
- **Charts:** Plotly, transparent backgrounds
- **Tables:** Native `st.dataframe` with `Styler`, hide index, full-width
- **Filters:** Floating popover top-right (`st.popover`)
- **Navigation:** Top horizontal nav bar (custom HTML)
- **Font hierarchy:** 15px body, 12px captions, 24px h2, 36px h1
- **Lower-is-better stats:** Tagged in `LOWER_IS_BETTER` set per page; coloring inverts

## Key shared helpers

- `lib/data.py` — DB queries, cached with `@st.cache_data`. Imports from submodule.
- `lib/theme.py` — `inject_theme(active_page)` injects CSS + horizontal nav
- `lib/coloring.py` — `style_dataframe_by_ranks`, `style_dataframe_by_percentiles`, `metric_card_html`
- `lib/charts.py` — `bar_chart`, `stat_picker`, `column_multiselect`
- `lib/filters.py` — season/window filter dropdowns
- `lib/format.py` — number/time formatters

## Open backlog (from prior sessions)

Deferred work with no scheduled commit:

- Lead tracker chart on Matchup (requires PBP ETL — heavy)
- Shot charts (heavy ETL, niche use case for podcast)
- Defensive matchups (table stubbed, ETL not built)
- Officials/refs (table stubbed)
- Schedule view (deprioritized)

## What you need from me first thing

When I open a new conversation, I'll either:

**A. Bring a specific request:** "Add X to Y page." Ask design questions before code.

**B. Bring a bug:** "Z is broken." Ask for screenshots/logs, diagnose, fix.

**C. Open exploratory:** "What should we work on next?" Propose 2-3 options based on backlog, prioritized for podcast prep value.

In all cases, your first response should:
1. Confirm you've read this kickoff doc
2. If A or B: ask clarifying questions before writing code
3. If C: propose options with effort estimates

## Working style during a session

- **One feature at a time.** Don't bundle.
- **Show design plan before code.**
- **Drop deliverables as zip files.**
- **Verify imports before packaging:** `python -c "import ast; ast.parse(open('file.py').read())"`
- **Tell me to commit + push at clean stopping points.**
- **No SQL schema changes here.** Schema lives in `nba-data`. Redirect to data ops thread.

## Session discipline

- **Cap at 3-4 hours.** No marathons.
- **Stop at first sign of fatigue or scope creep.**
- **Tag a commit at end of each meaningful change.**
- **Don't compromise integrity for speed.** If something's brittle, say so.

## Reference: Master roadmap

If broader context needed, reference `ROADMAP.md` in project root.
