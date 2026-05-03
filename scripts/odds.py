"""The Odds API integration — fetch NBA odds, store snapshots.

Configuration via env vars:
    THE_ODDS_API_KEY  — required
    ODDS_BOOKMAKERS   — optional, default 'draftkings,fanduel'
    ODDS_REGIONS      — optional, default 'us'

Schedule (HKT, runs via GitHub Actions):
    opening   22:00 HKT  (14:00 UTC)
    pre_game  07:30 HKT  (23:30 UTC prev day)
    late      12:00 HKT  (04:00 UTC)
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "basketball_nba"
DEFAULT_MARKETS = "h2h,spreads,totals"
DEFAULT_BOOKMAKERS = "draftkings,fanduel"
DEFAULT_REGIONS = "us"
DEFAULT_ODDS_FORMAT = "decimal"
VALID_PHASES = {"opening", "pre_game", "closing", "manual"}


def _api_key() -> str:
    key = os.environ.get("THE_ODDS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "THE_ODDS_API_KEY env var not set. "
            "Local: add to .env file. CI: add as GitHub Secret."
        )
    return key


def detect_phase_from_now() -> str:
    """Auto-detect snapshot phase from current UTC hour.

    UTC mapping (matches GitHub Actions cron times):
        13–17 UTC  -> opening      (~21–01 HKT)
        22–02 UTC  -> pre_game    (~06–10 HKT)
        03–06 UTC  -> late        (~11–14 HKT)
        else       -> manual
    """
    h = datetime.now(timezone.utc).hour
    if 13 <= h < 18:    return "opening"
    if 22 <= h or h < 3: return "pre_game"
    if 3 <= h < 7:      return "closing"
    return "manual"


def fetch_odds(api_key: str | None = None,
                bookmakers: str | None = None,
                regions: str | None = None,
                markets: str = DEFAULT_MARKETS,
                odds_format: str = DEFAULT_ODDS_FORMAT) -> tuple[list[dict], dict]:
    """Hit The Odds API. Returns (events, usage_info)."""
    api_key = api_key or _api_key()
    bookmakers = bookmakers or os.environ.get("ODDS_BOOKMAKERS") or DEFAULT_BOOKMAKERS
    regions = regions or os.environ.get("ODDS_REGIONS") or DEFAULT_REGIONS
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
        "bookmakers": bookmakers,
    }
    url = f"{API_BASE}/sports/{SPORT_KEY}/odds"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    usage = {
        "remaining": _safe_int(resp.headers.get("x-requests-remaining")),
        "used": _safe_int(resp.headers.get("x-requests-used")),
        "last_call_cost": _safe_int(resp.headers.get("x-requests-last")),
    }
    logger.info("Odds API: %d events. Credits: used=%s, remaining=%s, this_call=%s",
                 len(data), usage["used"], usage["remaining"], usage["last_call_cost"])
    return data, usage


def _safe_int(x: Any) -> int | None:
    try:
        return int(x) if x is not None else None
    except (ValueError, TypeError):
        return None


def _derive_phase_for_event(commence_iso: str | None,
                              snapshot_iso: str,
                              caller_phase: str) -> str | None:
    """Derive the correct phase for ONE event based on time-to-tip.

    Returns:
        - "opening"  if game is >12 hours away
        - "pre_game" if game is 0.5-12 hours away
        - "closing"    if game is <30 min away (or up to tip-time)
        - None      if game is already in progress / done — we should NOT store
                    the row (it would be live or stale post-game data).

    If caller_phase is "manual", we skip the time check entirely and just
    return "manual" so test runs always store data.
    """
    if caller_phase == "manual":
        return "manual"
    if not commence_iso:
        # Can't compute → fall back to whatever the slot was tagged as
        return caller_phase

    try:
        commence_dt = datetime.fromisoformat(commence_iso.replace("Z", "+00:00"))
        snapshot_dt = datetime.fromisoformat(snapshot_iso.replace("Z", "+00:00"))
    except Exception:
        return caller_phase

    hours_until = (commence_dt - snapshot_dt).total_seconds() / 3600.0
    if hours_until > 12:
        return "opening"
    if hours_until > 0.5:
        return "pre_game"
    if hours_until >= 0:
        return "closing"
    # Game has started or finished — don't store this snapshot
    return None


def parse_events(events: list[dict], snapshot_phase: str,
                  fetched_utc: str) -> tuple[list[dict], list[dict]]:
    """Returns (snapshot_rows, mapping_rows).

    snapshot_phase from the caller is treated as a fallback / hint — actual phase
    stored per event is derived from (commence_time - fetched_utc) so that:
      - A 16:00 HKT snapshot of a game tipping in 14h gets 'opening'
      - A 11:30 HKT snapshot of a game tipping in 20min gets 'closing'
      - A 09:30 HKT snapshot of a 09:00 HKT game (already started) is SKIPPED
    """
    snapshot_rows: list[dict] = []
    mapping_rows: list[dict] = []
    skipped_in_progress = 0

    for ev in events:
        event_id = str(ev.get("id", ""))
        if not event_id:
            continue
        commence = ev.get("commence_time")
        home = ev.get("home_team", "")
        away = ev.get("away_team", "")
        game_date = (commence[:10] if commence else None)

        # Per-event phase — None means game is already in progress or finished
        per_event_phase = _derive_phase_for_event(commence, fetched_utc, snapshot_phase)
        if per_event_phase is None:
            skipped_in_progress += 1
            continue

        mapping_rows.append({
            "event_id": event_id,
            "home_team_name": home,
            "away_team_name": away,
            "commence_utc": commence,
            "created_utc": fetched_utc,
        })

        for book in ev.get("bookmakers", []):
            book_key = book.get("key", "")
            for market in book.get("markets", []):
                m_key = market.get("key")
                outcomes = market.get("outcomes", [])
                row = _outcomes_to_row(m_key, outcomes, home, away)
                if row is None:
                    continue
                row.update({
                    "event_id": event_id,
                    "snapshot_phase": per_event_phase,
                    "fetched_utc": fetched_utc,
                    "commence_time_utc": commence,
                    "game_date": game_date,
                    "bookmaker": book_key,
                    "market": m_key,
                    "is_closing": 1 if per_event_phase == "closing" else 0,
                })
                snapshot_rows.append(row)

    if skipped_in_progress:
        logger.info("Skipped %d in-progress/finished events at this snapshot",
                     skipped_in_progress)

    return snapshot_rows, mapping_rows


def _outcomes_to_row(market: str, outcomes: list[dict],
                       home: str, away: str) -> dict | None:
    base = {
        "home_price": None, "away_price": None,
        "spread_home": None, "spread_away": None,
        "total_line": None, "over_price": None, "under_price": None,
    }
    if market == "h2h":
        for o in outcomes:
            if o.get("name") == home:
                base["home_price"] = o.get("price")
            elif o.get("name") == away:
                base["away_price"] = o.get("price")
        return base
    if market == "spreads":
        for o in outcomes:
            if o.get("name") == home:
                base["home_price"] = o.get("price")
                base["spread_home"] = o.get("point")
            elif o.get("name") == away:
                base["away_price"] = o.get("price")
                base["spread_away"] = o.get("point")
        return base
    if market == "totals":
        for o in outcomes:
            name = (o.get("name") or "").lower()
            if name == "over":
                base["over_price"] = o.get("price")
                base["total_line"] = o.get("point")
            elif name == "under":
                base["under_price"] = o.get("price")
                if base["total_line"] is None:
                    base["total_line"] = o.get("point")
        return base
    return None


_NEW_COLUMNS = [
    ("snapshot_phase", "TEXT"),
    ("event_id", "TEXT"),
    ("commence_time_utc", "TEXT"),
    ("game_date", "TEXT"),
]


def ensure_odds_schema(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(odds_snapshots)")}
    for col_name, col_type in _NEW_COLUMNS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE odds_snapshots ADD COLUMN {col_name} {col_type}")
            logger.info("Added odds_snapshots.%s", col_name)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_unique
            ON odds_snapshots (event_id, snapshot_phase, bookmaker, market)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_odds_game_phase
            ON odds_snapshots (game_id, snapshot_phase, bookmaker, market)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS odds_event_mapping (
            event_id        TEXT PRIMARY KEY,
            game_id         TEXT,
            home_team_name  TEXT NOT NULL,
            away_team_name  TEXT NOT NULL,
            commence_utc    TEXT NOT NULL,
            created_utc     TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_odds_mapping_game ON odds_event_mapping(game_id)")


def store_snapshots(conn: sqlite3.Connection, snapshot_rows: list[dict],
                     mapping_rows: list[dict]) -> tuple[int, int]:
    if not snapshot_rows:
        return 0, 0

    snap_cols = ["fetched_utc", "event_id", "snapshot_phase", "commence_time_utc",
                  "game_date", "game_id", "home_team_id", "away_team_id",
                  "bookmaker", "market",
                  "home_price", "away_price", "spread_home", "spread_away",
                  "total_line", "over_price", "under_price", "is_closing"]
    placeholders = ", ".join(f":{c}" for c in snap_cols)
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in snap_cols
                                if c not in ("event_id", "snapshot_phase", "bookmaker", "market"))
    sql = (
        f"INSERT INTO odds_snapshots ({', '.join(snap_cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(event_id, snapshot_phase, bookmaker, market) "
        f"DO UPDATE SET {update_clause}"
    )

    enriched = []
    for r in snapshot_rows:
        full = {c: None for c in snap_cols}
        full.update(r)
        full["game_id"] = full.get("game_id") or _lookup_game_id(conn, r.get("event_id"))
        # team ids derived from mapping during dashboard query, not here
        enriched.append(full)
    conn.executemany(sql, enriched)

    map_cols = ["event_id", "game_id", "home_team_name", "away_team_name",
                 "commence_utc", "created_utc"]
    map_sql = (
        f"INSERT INTO odds_event_mapping ({', '.join(map_cols)}) "
        f"VALUES ({', '.join(f':{c}' for c in map_cols)}) "
        f"ON CONFLICT(event_id) DO UPDATE SET "
        f"game_id=COALESCE(excluded.game_id, odds_event_mapping.game_id), "
        f"created_utc=excluded.created_utc"
    )
    enriched_maps = []
    for m in mapping_rows:
        full = {c: None for c in map_cols}
        full.update(m)
        full["game_id"] = _match_game_by_teams(
            conn, m.get("home_team_name", ""), m.get("away_team_name", ""),
            m.get("commence_utc"),
        )
        enriched_maps.append(full)
    conn.executemany(map_sql, enriched_maps)

    return len(snapshot_rows), len(mapping_rows)


def _lookup_game_id(conn: sqlite3.Connection, event_id: str | None) -> str | None:
    if not event_id:
        return None
    row = conn.execute(
        "SELECT game_id FROM odds_event_mapping WHERE event_id = ?", (event_id,),
    ).fetchone()
    if row:
        gid = row["game_id"] if hasattr(row, "keys") else row[0]
        return gid
    return None


def _match_game_by_teams(conn: sqlite3.Connection, home_name: str, away_name: str,
                          commence_utc: str | None) -> str | None:
    """Match Odds API event to nba_api game by team full_name + date."""
    if not (home_name and away_name and commence_utc):
        return None
    target_date = commence_utc[:10]
    home_row = conn.execute(
        "SELECT team_id FROM teams WHERE LOWER(full_name) = LOWER(?)", (home_name,),
    ).fetchone()
    away_row = conn.execute(
        "SELECT team_id FROM teams WHERE LOWER(full_name) = LOWER(?)", (away_name,),
    ).fetchone()
    if not (home_row and away_row):
        return None
    home_id = home_row[0] if not hasattr(home_row, "keys") else home_row["team_id"]
    away_id = away_row[0] if not hasattr(away_row, "keys") else away_row["team_id"]

    row = conn.execute(
        """
        SELECT game_id FROM games
        WHERE home_team_id = ? AND away_team_id = ?
          AND date(game_date) BETWEEN date(?, '-1 day') AND date(?, '+1 day')
        ORDER BY ABS(julianday(game_date) - julianday(?)) ASC
        LIMIT 1
        """,
        (home_id, away_id, target_date, target_date, target_date),
    ).fetchone()
    if not row:
        return None
    return row[0] if not hasattr(row, "keys") else row["game_id"]


def rematch_orphan_events(conn: sqlite3.Connection) -> dict:
    """Re-attempt to match orphan odds events to nba_api game_ids.

    Called from `daily` after schedule refresh — heals orphans that were
    captured before their corresponding games were in our schedule.

    Two passes:
      1. Try to find game_ids for events still in odds_event_mapping with NULL
         game_id (using the team-name+date matcher).
      2. Sync odds_snapshots.game_id from odds_event_mapping wherever they
         share an event_id but the snapshot row's game_id is NULL.

    Returns dict with counts.
    """
    orphans = conn.execute(
        """
        SELECT event_id, home_team_name, away_team_name, commence_utc
        FROM odds_event_mapping
        WHERE game_id IS NULL
          AND date(commence_utc) >= date('now', '-30 days')
        """
    ).fetchall()

    matched = 0
    still_orphan = 0
    for row in orphans:
        event_id = row[0] if not hasattr(row, "keys") else row["event_id"]
        home_name = row[1] if not hasattr(row, "keys") else row["home_team_name"]
        away_name = row[2] if not hasattr(row, "keys") else row["away_team_name"]
        commence = row[3] if not hasattr(row, "keys") else row["commence_utc"]

        gid = _match_game_by_teams(conn, home_name, away_name, commence)
        if gid:
            # Update both tables: mapping AND any existing snapshot rows
            conn.execute(
                "UPDATE odds_event_mapping SET game_id = ? WHERE event_id = ?",
                (gid, event_id),
            )
            conn.execute(
                "UPDATE odds_snapshots SET game_id = ? WHERE event_id = ?",
                (gid, event_id),
            )
            matched += 1
        else:
            still_orphan += 1

    conn.commit()

    # Pass 2: always sync odds_snapshots.game_id from the mapping table.
    # Even if pass 1 found no new orphans to match, mapping might already have
    # game_ids that snapshots don't reflect (e.g., from a previous run).
    sync_result = conn.execute(
        """
        UPDATE odds_snapshots
        SET game_id = (
            SELECT m.game_id FROM odds_event_mapping m
            WHERE m.event_id = odds_snapshots.event_id
        )
        WHERE game_id IS NULL AND event_id IS NOT NULL
        """
    )
    snapshots_synced = sync_result.rowcount
    conn.commit()

    return {
        "checked": len(orphans),
        "rematched": matched,
        "still_orphan": still_orphan,
        "snapshots_synced": snapshots_synced,
    }


def run_odds_fetch(conn: sqlite3.Connection, phase: str | None = None,
                    markets: str | None = None) -> dict:
    if phase in (None, "auto"):
        phase = detect_phase_from_now()
    if phase not in VALID_PHASES:
        raise ValueError(f"Invalid phase: {phase}. Valid: {VALID_PHASES}")

    fetched_utc = datetime.now(timezone.utc).isoformat()
    if markets:
        events, usage = fetch_odds(markets=markets)
    else:
        events, usage = fetch_odds()
    snap_rows, map_rows = parse_events(events, phase, fetched_utc)
    ensure_odds_schema(conn)
    n_snap, n_map = store_snapshots(conn, snap_rows, map_rows)
    conn.commit()

    return {
        "phase": phase,
        "events_fetched": len(events),
        "snapshots_stored": n_snap,
        "mappings_stored": n_map,
        "credits_remaining": usage["remaining"],
        "credits_used": usage["used"],
        "this_call_cost": usage["last_call_cost"],
    }
