# V2 UI Redesign Spec

**Owner:** Eddy
**Status:** Design locked. Ready for build thread.
**Decision date:** 2026-05-16
**Last updated:** 2026-05-16

---

## The shift in one sentence

Move from a **stats viewer** (renders numbers) to an **insight generator** (renders conclusions).

basketball-reference.com is a stats viewer. The Athletic / Cleaning the Glass is an insight generator. v1 of `nba-dashboard` skews stats-viewer. v2 is the deliberate rebuild toward insight generator, without losing the underlying data.

---

## Why this rebuild exists

Four real complaints from daily use:

1. **UI not decent** — fonts too small (Streamlit default 13px), filters hidden in popovers, no visual hierarchy
2. **Slow page travel** — `league_team_table` recomputes from raw SQL every page nav, ~2-4s per page
3. **Data too generic** — raw stats shown in isolation, no narrative layer, no deltas, no editorial voice
4. **Lack of professionalism** — looks like a Streamlit demo, not a syndicate tool

The root cause behind all four: we built a working data layer but never built the **analytical surface** that turns numbers into stories.

---

## The hybrid design decision

Three design philosophies were evaluated. Final decision is a hybrid mapping each philosophy to the use case it best serves:

| Surface | Philosophy | Why |
|---|---|---|
| **Landing page** (Today / morning routine) | **Briefing** | Newsletter-structured, scannable, 3-min read. Section-divided like a morning briefing. Best for the daily-open use case. |
| **Matchup / Team Profile / Player Profile** (deep dives) | **Cockpit** | Trader-grade density, working surface, sparklines everywhere. Best for podcast prep and live podcast reference. |
| **Insights blocks** (inside every page) | **Editorial** | Narrative-first auto-generated bullet points: "Story angle", "Key edge", "Watch for". Same voice across both surfaces. |

Mockup files for reference:

- `docs/mockups/cockpit.html` — Trader-grade density. Open in browser.
- `docs/mockups/editorial.html` — Narrative-first.
- `docs/mockups/briefing.html` — Newsletter-structured.

---

## Five universal commitments

These apply to every page regardless of which philosophy it uses:

1. **Sparklines next to every number.** Inline SVG, ~60px × 16px, last 10 games or last 15 games depending on context. Universal in pro tools, absent in v1.
2. **Auto-generated narrative bullets** as a first-class element. Powered by a new rule-based `insights` engine that produces phrases like "OFF Rating +5.1 over L10 — top 10% movers this week".
3. **Cmd+K quick-search palette.** Fuzzy match teams + players, jumps to their profile. Critical for live podcast use.
4. **Real typography hierarchy.** 16px body (up from 13px), 22px h1, 18px h2. Inter or SF Pro. Sentence case throughout. Two weights only: 400 / 500.
5. **Color-coded percentile chips** instead of raw ranks. Green→amber→red diverging, consistent with existing `coloring.py`.

---

## New components to build

| Component | Lives at | Purpose |
|---|---|---|
| **`lib/insights.py`** | New file | Rule-based engine. Takes a team/player/window and returns a list of bullet-point insights with severity (story angle vs edge vs watch). |
| **`lib/sparkline.py`** | New file | SVG sparkline generator. Takes a list of values, returns inline SVG. Color by trend direction. |
| **`lib/commandbar.py`** | New file | Cmd+K palette component. Custom HTML/JS injected via `st.components.v1.html`. Fuzzy match teams + players. |
| **`lib/typography.py`** | Reorganize `theme.py` | CSS injection for the new type system. Bigger fonts, hierarchy, Inter font load. |
| **`lib/percentile_chip.py`** | New file or in coloring | Helper that renders a colored chip given a percentile. |

---

## Page-by-page mapping

| Page | Status today | v2 design |
|---|---|---|
| **Landing** (currently `app.py`) | Generic home with sidebar nav notes | **Briefing structure.** Three numbered sections: Tonight's slate, What's trending, Injury watch. Each section auto-generated. |
| **Matchup** (`2_Matchup.py`) | Mixed — Edge Finder is cockpit-ish, rest is detail dump | **Cockpit.** Top: matchup header card (current is fine). Below: 2-col layout with Insights block (Editorial voice) on the left, dense stat tables on the right. Existing Edge Finder Phase A stays as a section. |
| **Team Stats** (`3_Team_Stats.py`) | Dense table | **Cockpit.** Add sparklines to every numeric column. Add row-level Insights expander. |
| **Player Stats** (`4_Player_Stats.py`) | Dense table | **Cockpit.** Same — sparklines + insights. |
| **Team Profile** (new) | Doesn't exist | **Cockpit.** Hero + Insights block + 4-quadrant stat layout + 10-game trend strip. + Compare button surfaces a second team beside the first. |
| **Player Profile** (new) | Doesn't exist | **Cockpit.** Same structure as Team Profile. + Compare button for injury-replacement use case. |
| **Today** (currently `1_Today.py`) | Generic upcoming-games view | **Merge into Landing.** Drop the separate page. The Briefing IS Today. |

---

## What lives where after v2

```
nba-dashboard/
├── dashboard/
│   ├── app.py                          → Landing (Briefing)
│   ├── pages/
│   │   ├── 1_Matchup.py                → was 2_Matchup
│   │   ├── 2_Team_Stats.py             → was 3_Team_Stats
│   │   ├── 3_Player_Stats.py           → was 4_Player_Stats
│   │   ├── 4_Team_Profile.py           → NEW
│   │   └── 5_Player_Profile.py         → NEW
│   └── lib/
│       ├── data.py                     → existing
│       ├── theme.py                    → refactored (new typography)
│       ├── coloring.py                 → existing
│       ├── insights.py                 → NEW (rule-based engine)
│       ├── sparkline.py                → NEW
│       ├── commandbar.py               → NEW (Cmd+K)
│       └── ...                         → existing helpers
```

The old `1_Today.py` gets folded into `app.py`. Net page count drops from 5 to 6 but the entry point is much sharper.

---

## Recommended build sequence

Foundation first, then content. This is the key sequencing decision — don't add new pages on top of the old framework, fix the framework first so every new page inherits the upgrade.

| Phase | Effort | What ships |
|---|---|---|
| **1. Foundation pass** | ~4h | New typography, filter UX rework, sparkline component, percentile chip component. Visible polish win across existing pages immediately. |
| **2. Performance pass** | ~3h *(data ops thread)* | Materialized view for `league_team_table`. Smarter caching. Sub-second page navigation. |
| **3. Insights engine v1** | ~5h | `lib/insights.py` with ~20 rules. Drop `<Insights />` block at top of Matchup, then Team Stats, then Player Stats. Most expensive single feature, unlocks everything else. |
| **4. Edge Finder Phase B** | ~2h | "What Changed" delta view. Becomes one input source for the insights engine. |
| **5. Briefing landing** | ~4h | Rebuild `app.py` as the Briefing. Replace the generic home. Wire in: today's slate cards, league trending list, injury watch. |
| **6. Team Profile page** | ~5h | New page. Hero + Insights + 4-quadrant + 10-game trend. + Compare button. |
| **7. Player Profile page** | ~5h | New page. Same structure as Team Profile. |
| **8. Cmd+K palette** | ~2h | Cross-page quick search. |
| **9. News categorization** | ~3h | 8 categories. Lowest leverage per kickoff doc, do last. |

Total: ~33h, vs original kickoff plan of ~25h. Extra 8h is the foundation + insights + Cmd+K work — buys you a dashboard that's professional from page 1, instead of more pages on weak ground.

---

## Insights engine design

Keep it rule-based, not LLM-based, for v1. Each rule is a Python function that returns either `None` or an `Insight` object.

Example rule:

```python
def pace_shift(team_id: int, window: str, mtime) -> Insight | None:
    current = team_aggregate(team_id, "L10", "both", _mtime=mtime).get("pace")
    prior = team_aggregate_prior(team_id, "L10", "both", _mtime=mtime).get("pace")
    if current is None or prior is None:
        return None
    delta = current - prior
    if abs(delta) < 3.0:
        return None
    return Insight(
        category="trend",
        severity="medium" if abs(delta) < 5 else "high",
        text=f"Pace {'+' if delta > 0 else ''}{delta:.1f} possessions vs prior L10",
        stat="pace",
        team_id=team_id,
    )
```

Run all rules, collect all `Insight` objects, render top-N by severity at the top of each relevant page. ~20 rules covers the main signal: pace shifts, OFF/DEF Rating deltas, eFG% changes, 3P% (with noise filter), OPP eFG% (defense), injury impact, B2B, rest advantage, recent W-L streaks.

LLM augmentation can come later — *polish* the bullet wording with a small model, but never let it invent claims.

---

## What's deliberately NOT in scope

- **WOWY metrics** — Eddy explicitly declined ("too complicated, just use other websites")
- **Shot charts** — heavy ETL, niche podcast value
- **Live in-game odds / line move alerts** — that's Win territory
- **Player props** — Win territory, Phase 4+
- **Mobile-specific layouts** — desktop-only for v2
- **User accounts / multi-user** — single-user app

---

## Out of scope ⇒ data ops thread

These pre-conditions need to ship in the data ops thread before v2 dashboard work hits its full potential:

1. **Materialized view** for `league_team_table` (performance)
2. **`team_misc_stats` table** (paint, transition, second-chance, off-TO) — see `V2-DATA-OPS-HANDOFF.md`
3. **`team_shot_locations` table** — optional Tier 2

Without #2 and #3, the Cockpit views and Edge Finder feel undernourished. But the dashboard rebuild can ship a complete v2 using only the current data layer — the new tables just unlock richer insights when they arrive.

---

## How this maps to ROADMAP.md

ROADMAP.md tracks the Win betting build (Phase 3) + infrastructure phases. This v2 redesign is **not a ROADMAP phase** — it's basketball-dashboard ongoing thread work, runs parallel to Phase 3 Win MVP.

Phase 3 happens in Claude Code. v2 dashboard rebuild happens in Cowork (this same tool family). Different contexts, no overlap in code, no conflict.

---

## Tag plan

- `v2.0-foundation` — after steps 1-2 (typography + perf)
- `v2.1-insights` — after step 3 (insights engine)
- `v2.2-edge-finder` — after step 4 (Phase B delta)
- `v2.3-landing` — after step 5 (Briefing landing)
- `v2.4-profiles` — after steps 6-7 (Team + Player Profile)
- `v2.5-search` — after step 8 (Cmd+K)
- `v2.6-news` — after step 9 (news cat)

---

## For the new build thread

Bring this doc + the three mockup HTML files as opening context. State the thread is the v2 redesign and reference this spec for any design question. Start with **step 1, Foundation pass** — it's the highest-leverage first move and visible polish gets the morale flywheel going.

Decisions that should NOT be relitigated in the build thread:

- Stay on Streamlit (don't propose Dash / NiceGUI / React rewrite)
- Hybrid Briefing+Cockpit+Editorial (don't propose pure-one-philosophy)
- Rule-based insights v1 (don't propose LLM-first)
- Foundation before pages (don't propose adding pages before fixing framework)

If a decision needs to change, bring it back to a planning thread, not the build thread. Build threads execute; planning threads decide.
