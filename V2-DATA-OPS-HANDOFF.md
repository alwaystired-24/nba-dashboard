# V2 Stat Universe — Data Ops Handoff

**From:** Basketball dashboard thread (03)
**To:** Data ops thread (05)
**Status:** Spec ready. Ship in data ops thread, then return to basketball thread for v2 UI work.
**Last updated:** 2026-05-09

---

## Context

Edge Finder Phase A v1 shipped on **2026-05-09** (tag `v1.2.0-edge-finder-phase-a`). v1 uses the ~35 stats already in `team_aggregate` / `team_opponent_aggregate`. Per the kickoff doc Phase A spec, the eventual stat universe should also include **points in paint, transition, second-chance, fast break, points off TOs**, etc. — none of which are currently ETL'd.

This doc specifies what the data ops thread needs to deliver to unblock Edge Finder Phase A v2 (and any future feature that wants these stats — Team Profile, podcast narrative views, Win Compiler, etc.).

---

## Stats to add — priority tiers

### Tier 1 — Misc team stats (HIGH priority, easy)

NBA stats API: `LeagueDashTeamStats?MeasureType=Misc` for season totals, `BoxScoreMiscV2` for per-game. Per-game is preferred so we can window with L5/L10/L20 like the rest of the data layer.

| New stat key | Direction | NBA API field | Description |
|---|---|---|---|
| `pts_paint` | higher = better off | `PTS_PAINT` | Points in paint scored |
| `pts_paint_allowed` | lower = better def | `OPP_PTS_PAINT` | Points in paint allowed |
| `pts_fast_break` | higher = better off | `PTS_FB` | Fast-break points scored |
| `pts_fast_break_allowed` | lower = better def | `OPP_PTS_FB` | Fast-break points allowed |
| `pts_off_tov` | higher = better off | `PTS_OFF_TOV` | Points off opponent TOs |
| `pts_off_tov_allowed` | lower = better def | `OPP_PTS_OFF_TOV` | Points opponent scored off our TOs |
| `pts_2nd_chance` | higher = better off | `PTS_2ND_CHANCE` | Second-chance points |
| `pts_2nd_chance_allowed` | lower = better def | `OPP_PTS_2ND_CHANCE` | Second-chance points allowed |
| `pts_bench` | informational | — | Bench points (compute from player box) |

These are the highest-leverage stats for the basketball dashboard because they map directly to podcast narratives (*"Knicks won the second-chance battle 18-7"*, *"Sixers gave up 28 in transition"*).

### Tier 2 — Shot locations (MEDIUM priority)

NBA stats API: `LeagueDashTeamShotLocations` or `ShotChartDetail` aggregated by zone.

| New stat key | Description |
|---|---|
| `ra_fg_pct` | FG% in restricted area |
| `paint_non_ra_fg_pct` | FG% in paint (excl. RA) |
| `mid_range_fg_pct` | FG% mid-range |
| `corner_3_fg_pct` | FG% corner 3 |
| `above_break_3_fg_pct` | FG% above-the-break 3 |
| `*_allowed` | Opponent equivalents for defense |

Useful but not as podcast-immediate as Tier 1. OK to defer if Tier 1 is non-trivial.

### Tier 3 — Synergy play types (DEFER)

Pick-and-roll, isolation, post-up, transition, etc. Endpoint: `synergyplaytypes`. Issues:

- Heavy rate limits / occasional auth challenges
- More marginal podcast value
- Better fit for Win Compiler than Edge Finder

Not blocking Edge Finder Phase A v2. Defer to V3 unless a specific use case emerges.

---

## Schema proposal

Append-only migrations per locked rule. New tables, no modification of existing.

### `team_misc_stats` (Tier 1)

```sql
CREATE TABLE IF NOT EXISTS team_misc_stats (
    game_id TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    pts_paint REAL,
    pts_paint_allowed REAL,
    pts_fast_break REAL,
    pts_fast_break_allowed REAL,
    pts_off_tov REAL,
    pts_off_tov_allowed REAL,
    pts_2nd_chance REAL,
    pts_2nd_chance_allowed REAL,
    pts_bench REAL,
    last_attempt_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (game_id, team_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE INDEX IF NOT EXISTS idx_team_misc_team ON team_misc_stats (team_id);
CREATE INDEX IF NOT EXISTS idx_team_misc_game ON team_misc_stats (game_id);
```

### `team_shot_locations` (Tier 2, optional)

```sql
CREATE TABLE IF NOT EXISTS team_shot_locations (
    game_id TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    zone TEXT NOT NULL,  -- 'restricted_area' | 'paint_non_ra' | 'mid_range' | 'corner_3' | 'above_break_3'
    fgm INTEGER,
    fga INTEGER,
    fg_pct REAL,
    last_attempt_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (game_id, team_id, zone),
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE INDEX IF NOT EXISTS idx_team_shot_loc_team ON team_shot_locations (team_id);
```

---

## ETL changes (in `nba-data` repo)

### `scripts/nba.py` additions

1. **`fetch_team_misc(game_id)`** — calls `BoxScoreMiscV2(game_id=game_id)`, returns 2-row DataFrame (one per team). Maps NBA API columns to schema fields. `pts_bench` is computed from `player_box_traditional` where `is_starter = 0`.

2. **`fetch_team_shot_locations(game_id)`** *(Tier 2)* — calls `ShotChartDetail` filtered to the game, groups by `SHOT_ZONE_BASIC`, aggregates FGM/FGA/FG%.

3. Wire into `scripts/run.py daily` after the existing per-game advanced fetch.

### Rate limiting

NBA stats API allows ~30 req/min with the standard headers we already use. Tier 1 backfill of one season ≈ 1300 games × 1 endpoint = 1300 requests = ~45 min at safe rate. Tier 1 + Tier 2 = ~90 min. Acceptable for one-time backfill; daily incremental load is ~10 games × 2 endpoints = trivial.

### Backfill order

1. Apply migration
2. Backfill `team_misc_stats` from start of current season
3. (Optional) Backfill `team_shot_locations`
4. Verify row counts match `SELECT COUNT(*) FROM games WHERE status = 'Final' AND season_type IN ('Regular', 'Playoffs', 'PlayIn')` × 2 teams per game

---

## Then in nba-dashboard (after data ops ships)

1. Submodule update:
   ```bash
   cd ~/Documents/thefifthquarter/nba-project/nba-dashboard/external/nba-data
   git pull origin main
   cd ../..
   git add external/nba-data
   # commit via GitHub Desktop
   ```

2. Extend `dashboard/lib/data.py`:
   - `team_aggregate` SQL — `LEFT JOIN team_misc_stats` and `AVG(...)` the new columns
   - `team_opponent_aggregate` SQL — same
   - Add new keys to `STAT_LABELS` dict
   - Add `_allowed` variants to `LOWER_IS_BETTER` set

3. **`compute_team_percentiles` and the Edge Finder UI need NO code change** — they auto-pick up any new numeric column in `league_team_table`.

That's the magic of how v1 was built. v2 is essentially a data layer expansion + label additions.

---

## Acceptance criteria

Migration is "done" when:

- [ ] `team_misc_stats` table exists in Supabase Direct Connection
- [ ] Backfill complete: `SELECT COUNT(*) FROM team_misc_stats ≈ 2 * (Final games in current season)`
- [ ] Daily ETL writes new rows after each Final game
- [ ] Sanity check: pick a recent game, compare `pts_paint` to the box score at stats.nba.com — should match exactly (these are NBA-tracked, not derived)
- [ ] Submodule on nba-dashboard updated and committed
- [ ] *(Tier 2 only)* same for `team_shot_locations`

---

## Out of scope (deliberate)

- Synergy play types — Tier 3, defer to V3
- Player-level misc / shot location stats — Phase A is team-level, player-level is a future scope
- Drive / touch / passing tracking (`PlayerTrackingTeamPlayer`) — separate effort
- BBRef advanced metrics (TOV%, eFG% variants we don't already have) — already covered or not worth duplicating

---

## Risks

| Risk | Mitigation |
|---|---|
| `BoxScoreMiscV2` deprecation (NBA killed `BoxScoreSummaryV2` in April 2025) | Verify endpoint health before backfill. Fall back to `LeagueDashTeamStats?MeasureType=Misc` (season aggregate) if per-game fails. |
| Rate limit ban during backfill | Run backfill overnight, batch with delays. Local-only ETL (no GitHub Actions) for the initial pull. |
| Supabase free tier row count near limit | Tier 1 adds ≈ 2600 rows/season × 2 = 5200/season. Negligible. |
| Edge Finder Phase A v1 already deployed | No conflict. v1 ignores any column not in its current `team_aggregate` SQL. Adding columns is additive. |

---

## Reference

- ROADMAP `Phase 3.5` mentions ETL stability audit — coordinate with that.
- Edge Finder Phase A v1 implementation: `dashboard/lib/data.py` (`STAT_LABELS`, `compute_team_percentiles`) + `dashboard/pages/2_Matchup.py` (Edge Finder section).
- Tag `v1.2.0-edge-finder-phase-a` in nba-dashboard.
