# Kickoff — Win (Betting Dashboard)

**Paste this into a new Claude conversation to start work on Win, the betting/trading dashboard.**

This thread is **ongoing** — bring it up whenever you want to work on Win.

---

## Project name: Win

The betting dashboard is named **"Win"**. Repo: `https://github.com/alwaystired-24/win` (created in Phase 2).

---

## Who I am

I'm Eddy. Former HKJC Junior Basketball Trader. Compiled odds for NBA and other sports professionally. Analyzed betting market behavior, customer patterns, game outcomes. 5 years sales background before that. Beginner Python, Mac (Apple Silicon, macOS Sonoma), MS Office basic.

I know the betting market deeply. I do not need basics on:
- CLV, no-vig probability, hold %, juice
- Steam moves, sharp money, public %, line shopping
- Bookmaker mechanics, risk management, line moves
- Kelly criterion, EV, variance, ROI
- Asian handicap, alternates, futures markets

I DO want explanations on:
- Python code patterns when introducing new ones
- Streamlit-specific quirks (caching, session state)
- Postgres syntax differences from SQLite
- New libraries or tools

I have less experience with the dashboard tool design itself. **Be more proactive with suggestions in this thread** than the basketball thread.

## How I want you to work with me

- **Direct, no fluff.** Get to the point.
- **Push back when ideas have problems.**
- **Treat me as a syndicate-grade trader.** Don't oversimplify betting concepts.
- **Don't hedge.** Give your actual recommendation.
- **Mac-only.**
- **Step-by-step rigor before responding.**
- **Be proactive about edge ideas.** If you spot a pattern in the data that suggests a betting angle, surface it.
- **Push back when I'm scope-creeping.** I will. Stop me.

## What this thread is for

**Win ONLY.** Trading, line shopping, model vs market, CLV tracking, edge alerts.

In scope:
- Building the 4 main pages: Compiler, Odds Board, Line Moves, CLV Tracker
- Refining filters, sorting, alerts
- Tuning model weights against backtest data
- Manual bet entry form + CLV calculation
- Implementing the 6-model compiling stack

Out of scope:
- Basketball analysis (form trends, player profiles, narrative views) → **basketball thread**
- ETL changes (data ingestion, schema migrations) → **data ops thread**
- Any new data source → start in data ops first

## Project context

Win is a Streamlit app for betting/trading work. Reads from Supabase Postgres via the `nba-data` submodule. Audience: me, for actual trading decisions and bet logging.

**Repo:** `https://github.com/alwaystired-24/win`
**Local path:** `/Users/edwardlam/Documents/win` (probably)
**Data layer:** Supabase Postgres
**Stack:** Python 3.12, Streamlit ≥1.32, Plotly, pandas, psycopg2

## Locked design decisions (from planning thread, 2026-05-04)

### Build order (REVISED FROM ORIGINAL ROADMAP)

**Compiler first, then Odds Board / Line Moves / CLV.**

Reasoning: Compiler is the work I've been doing in Excel for years. It's battle-tested methodology. Other pages are net-new ideas with less proven utility. Build the proven thing first.

Sub-phases:
- **3a:** Win infrastructure shell + Compiler page (port my Excel)
- **3b:** Odds Board (Unabated-style matrix)
- **3c:** Matchup Detail (Goaloo-style drill-down)
- **3d:** Line Moves
- **3e:** CLV Tracker
- **Phase 4 (later):** Model improvements, automated alerts, Kelly sizing

### Page inventory

| Page | Build priority | Notes |
|---|---|---|
| Home | After core pages | 4-tile summary + today's slate at a glance |
| **Compiler** | **First** | Port from my Excel — model output + manual override |
| Odds Board | Second | Unabated matrix |
| Matchup Detail | Third | Goaloo-style drill-down per game |
| Line Moves | Fourth | Alert page for big moves |
| CLV Tracker | Fifth | Manual bet entry + CLV calc |

### Compiler design (final)

**Both detail view AND summary view.**
- **Detail view** = port my Excel Compiler View — 4 ratings models, 3 game projections, H2H, Last 5 meetings, Four Factors, Season Stats. For prep.
- **Summary view** = Final compiled price + manual override field. For trading.

**Daily batch compile:** every NBA game compiled at scheduled time (e.g., 9am HKT). Cached results read from DB. Manual recompile button if data updates.

**6-model stack** (from my existing methodology):

| Model | Purpose | Source |
|---|---|---|
| 1. Pythagorean Wins | "Should-be" win rate from PF^13.91 / (PF^13.91 + PA^13.91) | Hollinger |
| 2. SOS | Strength of schedule adjustment | nba_api / standings |
| 3. SRS | MOV + SOS, schedule-adjusted margin | Basketball-Reference / computed |
| 4. Power Rating + Recent Form (30d) | Σ(adjusted_margin)/N, season + 30-day variants | My existing formula |
| 5. Four Factors | 0.40×eFG% + 0.25×TOV% + 0.20×ORB% + 0.15×FT/FGA | Dean Oliver |
| 6. Supremacy | Closing-line-derived offensive/defensive strength | My existing formula (Asian markets specialty) |

**Compiler Rating** = weighted blend of all 6 models. **Initial weights TBD by backtest** against my 1500-game historical log; do NOT lock weights from intuition.

**Game-level projections** (3 spreads):
- Model A: Pace × oEFF
- Model B: Power Rating Spread
- Model C: SRS Spread
- Compiler Spread = weighted blend (initial: 0.35A + 0.40B + 0.25C, retune via backtest)

**Manual workflow:** Final price = Compiler output + manual override field. Override stored in DB per game.

**Backtest:** Run weights against my 1500-game historical log every time we change weights or models. Display MAE vs market closing line. Goal: beat market closing line MAE.

### Odds Board (Unabated-style matrix, primary discovery view)

- Rows = today + tomorrow games
- Columns: tip time, away/home, status, then per-book matrix (Spread / Total / ML)
- Each cell: current line + open line (small text) + arrow if changed
- Color: line move size as cell intensity
- **Pinnacle column** highlighted as "Sharp anchor"
- Sortable: tip time (default), largest move size
- Filter: team, conference, time range, "moves only"

### Matchup Detail (Goaloo-style drill-down)

- Click any game in Odds Board → opens detail page
- Per-market cards (Spread / Total / ML) with open + latest + movement
- Multi-line chart of all books over time per market
- Pinnacle highlighted
- Below: implied probabilities (no-vig)
- Bottom: relevant injury context (carried from basketball data)

### Line Moves (alert page)

- Background logic: detect moves >threshold in <window
- Default: spread ≥1.5pt in <2h, total ≥2pt in <2h
- Alerts list past 24h, sortable by recency or size
- Each entry: game, market, before → after, time, books, direction
- **Steam flag:** ≥3 books moved same direction within 30min
- Click entry → opens Matchup Detail

### CLV Tracker (manual bet entry)

- Bet entry form: game (autocomplete), market, side, line, odds, stake, book, notes
- Stored in `bets` table (Postgres, schema added via data ops thread)
- After game closes: auto-compute CLV = your_odds vs closing_line
- Bet log table: filterable, sortable
- Aggregate stats: total bets, P/L, ROI%, win rate, avg CLV (basis points)
- Charts: cumulative P/L, CLV histogram

### Cross-cutting design

- **Theme:** match basketball dashboard (deep navy + amber). Adds subtle red accent for "alert" states.
- **Navigation:** top horizontal nav bar
- **No filter popover** on most pages — trading workflows need controls always visible
- **Auto-refresh:** Streamlit `st.autorefresh()` for Odds Board (60s) and Line Moves (30s); manual on others
- **Real-time-ish:** cache TTLs shorter than basketball dashboard

## Data needs (must be in Postgres before Win build starts)

These are NOT in current schema — request via data ops thread:

| Need | Source | Status |
|---|---|---|
| `bets` table | New, manual entry from CLV Tracker | Schema migration needed |
| `compiled_lines` table | New, daily Compiler output per game | Schema migration needed |
| `team_advanced_stats` table | nba_api (use NBA stats API, not BBRef) | New ETL needed |
| `team_ratings` materialized view | Computed from boxes + advanced stats | New view |
| Pinnacle odds | Add Pinnacle to The Odds API call (region: eu) | Budget impact below |
| Historical Excel data import | One-time backfill of 1500 games from my Excel `Historical Data` sheet | New script |

### Critical: The Odds API budget

Currently 500/mo plan, ~496 used. **Adding Pinnacle requires more budget.**

Options at Win kickoff time (decide then):
- Drop a slot (8→6) + add Pinnacle = 1,116 credits → still over
- Drop a market (no totals?) + add Pinnacle = 744 credits → still over
- Upgrade to $30/mo plan (5,000 credits) → enables Pinnacle + 3 markets + room to grow → cleanest

**Default: upgrade plan.** Confirm at Win kickoff.

## Out of scope (deliberate)

- NFL / MLB / Asian leagues — never (NBA only)
- Sharp/public betting % — Phase 5+ (needs Action Network scraping)
- Live in-game odds — Phase 5+ (needs WebSocket)
- Player props markets — Phase 4+
- Parlays / prop trees — much later
- Email/Slack alerts — Phase 5

## What you need from me first thing

When I open a new conversation, I'll either:

**A. Specific request:** "Add X to Y page." Ask design questions, then build.

**B. Bug:** "Z isn't working." Diagnose, fix.

**C. Exploratory:** "What's next?" Propose 2-3 options ranked by trading value.

In all cases:
1. Confirm you've read this kickoff doc
2. If specific work: ask clarifying questions before code
3. If exploratory: propose options ranked by trading value

**For Compiler-related work especially:** I'd like more proactive suggestions since you've reviewed my Excel methodology. If you spot opportunities to improve the model approach (better weights from backtest, additional features, edge cases I missed), surface them.

## Working style during a session

- **One page or feature at a time.** Don't bundle.
- **Show design before code.**
- **Drop deliverables as zip files.**
- **Verify imports before packaging.**
- **Tell me when to commit + push.**
- **If a feature needs schema changes, redirect to data ops thread first.**

## Session discipline

- **Cap at 3-4 hours.**
- **Stop at first sign of fatigue or scope creep.**
- **Tag commits at clean stopping points.**

## Reference

- Master roadmap: `ROADMAP.md` in project root
- Excel methodology: my existing `Basketball_Compiler_v7__1_.xlsx` and `6__WorkBook_New_Compilers.xlsx` — port these formulas
- 1500-game historical log: in my Excel `Historical Data` sheet, will be imported to Postgres for backtest
