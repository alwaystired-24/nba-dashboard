"""CLI entrypoint for the nba-dashboard scrapers.

Usage:
    python -m scripts.run init           # create DB + populate teams
    python -m scripts.run schedule       # refresh games table for current season
    python -m scripts.run backfill       # run all box-score scrapers for unprocessed Final games
    python -m scripts.run daily          # refresh schedule + ingest yesterday's & today's finished games
    python -m scripts.run demographics   # pull position, age, height etc for active players
    python -m scripts.run status         # quick row counts / last-run summary
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Sequence

from .db import connect, init_schema
from .demographics import (
    backfill_demographics,
    ensure_demographic_columns,
    players_missing_demographics,
)
from .odds import run_odds_fetch, ensure_odds_schema
from .espn import run_espn_fetch, ensure_espn_schema
from .etl import (
    ingest_advanced_box,
    ingest_schedule,
    ingest_traditional_box,
    list_unprocessed_games,
    seed_teams,
)
from .nba import current_season


def cmd_init(args):
    init_schema()
    with connect() as conn:
        n = seed_teams(conn)
        ensure_demographic_columns(conn)
    print(f"Schema applied. Seeded {n} teams. Current season: {current_season()}")
    return 0


def cmd_schedule(args):
    season = args.season or current_season()
    with connect() as conn:
        seed_teams(conn)
        n = ingest_schedule(conn, season=season)
    print(f"Schedule synced for {season}: {n} games upserted.")
    return 0


def cmd_backfill(args):
    with connect() as conn:
        seed_teams(conn)
        ingest_schedule(conn, season=args.season or current_season())
        todo = list_unprocessed_games(conn)
        if args.limit:
            todo = todo[: args.limit]
    print(f"Box-score backfill: {len(todo)} games queued.")
    success_t = success_a = fail = 0
    for i, gid in enumerate(todo, 1):
        with connect() as conn:
            ok_t = ingest_traditional_box(conn, gid)
            ok_a = ingest_advanced_box(conn, gid)
        success_t += int(ok_t); success_a += int(ok_a)
        fail += int(not (ok_t and ok_a))
        if i % 25 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] traditional={success_t}  advanced={success_a}  failed={fail}")
    print(f"Done. traditional={success_t}/{len(todo)}, advanced={success_a}/{len(todo)}, failures={fail}")
    return 0 if fail == 0 else 1


def cmd_daily(args):
    with connect() as conn:
        ingest_schedule(conn, season=current_season())
        todo = list_unprocessed_games(conn)
    print(f"Daily update: {len(todo)} games to process.")
    success_t = success_a = fail = 0
    for gid in todo:
        with connect() as conn:
            ok_t = ingest_traditional_box(conn, gid)
            ok_a = ingest_advanced_box(conn, gid)
        success_t += int(ok_t); success_a += int(ok_a)
        fail += int(not (ok_t and ok_a))
    print(f"Daily update complete. traditional={success_t}, advanced={success_a}, failures={fail}")
    with connect() as conn:
        ensure_demographic_columns(conn)
        new_players = players_missing_demographics(conn)
    if new_players:
        print(f"Fetching demographics for {len(new_players)} new player(s)...")
        with connect() as conn:
            backfill_demographics(conn)

    # Auto-rematch any orphan odds events to newly-available games
    try:
        from .odds import rematch_orphan_events, ensure_odds_schema
        with connect() as conn:
            ensure_odds_schema(conn)
            res = rematch_orphan_events(conn)
        if res["checked"] > 0:
            print(f"Orphan odds rematch: checked {res['checked']}, "
                   f"matched {res['rematched']}, still orphan {res['still_orphan']}")
    except Exception as exc:
        print(f"(Skipped orphan odds rematch: {exc})")

    # Fetch ESPN injuries + news (best-effort, non-fatal)
    try:
        with connect() as conn:
            ensure_espn_schema(conn)
            espn_res = run_espn_fetch(conn)
        inj = espn_res["injuries"]
        news = espn_res["news"]
        print(f"ESPN: {inj['total_injuries']} injuries, {news['total_articles']} articles")
    except Exception as exc:
        print(f"(Skipped ESPN fetch: {exc})")

    return 0 if fail == 0 else 1


def cmd_demographics(args):
    with connect() as conn:
        ensure_demographic_columns(conn)
        s, f = backfill_demographics(conn, limit=args.limit, refresh=args.refresh)
    print(f"Done. success={s}, failures={f}")
    return 0 if f == 0 else 1


def cmd_odds(args):
    with connect() as conn:
        ensure_odds_schema(conn)
        try:
            summary = run_odds_fetch(conn, phase=args.phase,
                                       markets=getattr(args, "markets", None))
        except Exception as exc:
            print(f"Odds fetch failed: {exc}")
            return 1
    print(f"Odds fetch complete:")
    print(f"  phase:              {summary['phase']}")
    print(f"  events fetched:     {summary['events_fetched']}")
    print(f"  snapshots stored:   {summary['snapshots_stored']}")
    print(f"  mappings stored:    {summary['mappings_stored']}")
    print(f"  this call cost:     {summary['this_call_cost']} credits")
    print(f"  credits remaining:  {summary['credits_remaining']}")
    return 0


def cmd_odds_init(args):
    """One-time: apply migration 002, no API call."""
    with connect() as conn:
        ensure_odds_schema(conn)
    print("Odds schema applied. You can now run `python -m scripts.run odds --phase manual` to test.")
    return 0


def cmd_espn(args):
    """Fetch injuries + team news from ESPN."""
    with connect() as conn:
        ensure_espn_schema(conn)
        try:
            res = run_espn_fetch(conn)
        except Exception as exc:
            print(f"ESPN fetch failed: {exc}")
            return 1
    inj = res["injuries"]
    news = res["news"]
    print("ESPN fetch complete:")
    print(f"  Injuries:  {inj['teams_fetched']}/30 teams ok, "
           f"{inj['total_injuries']} injuries, {inj['teams_failed']} failed")
    print(f"  News:      {news['teams_fetched']}/30 teams ok, "
           f"{news['total_articles']} articles, {news['teams_failed']} failed")
    return 0


def cmd_espn_init(args):
    """One-time: apply migration 003 only."""
    with connect() as conn:
        ensure_espn_schema(conn)
    print("ESPN schema applied. Run `python -m scripts.run espn` to populate.")
    return 0


def cmd_status(args):
    with connect() as conn:
        for tbl in ("teams", "players", "games",
                     "team_box_traditional", "team_box_advanced",
                     "player_box_traditional", "player_box_advanced",
                     "odds_snapshots"):
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {tbl}").fetchone()["c"]
            print(f"  {tbl:30s} {n:>8d}")
        try:
            info_n = conn.execute(
                "SELECT COUNT(*) AS c FROM players WHERE info_fetched IS NOT NULL"
            ).fetchone()["c"]
            print(f"  players w/ demographics        {info_n:>8d}")
        except Exception:
            print(f"  players w/ demographics        (run init or demographics first)")
        last = conn.execute("SELECT MAX(last_attempt_utc) AS t FROM etl_runs").fetchone()
        print(f"  last_etl_run                   {last['t']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="nba-dashboard")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create DB and populate teams").set_defaults(func=cmd_init)

    p = sub.add_parser("schedule", help="refresh the games table")
    p.add_argument("--season")
    p.set_defaults(func=cmd_schedule)

    p = sub.add_parser("backfill", help="ingest box scores for unprocessed Final games")
    p.add_argument("--season")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_backfill)

    sub.add_parser("daily", help="schedule refresh + new-game ingest").set_defaults(func=cmd_daily)

    p = sub.add_parser("demographics", help="pull position, age, height etc")
    p.add_argument("--limit", type=int)
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(func=cmd_demographics)

    p = sub.add_parser("odds", help="fetch current NBA odds from The Odds API")
    p.add_argument("--phase", default="manual",
                    choices=["opening", "pre_game", "closing", "manual"],
                    help="snapshot phase tag for the rows we insert")
    p.add_argument("--markets", default=None,
                    help="comma-separated markets, default 'h2h,spreads,totals'. "
                         "Use 'spreads,totals' to skip moneyline (cheaper).")
    p.set_defaults(func=cmd_odds)

    sub.add_parser("odds_init", help="apply odds schema migration (one-time)").set_defaults(func=cmd_odds_init)

    sub.add_parser("espn", help="fetch injuries + team news from ESPN").set_defaults(func=cmd_espn)
    sub.add_parser("espn_init", help="apply ESPN schema migration (one-time)").set_defaults(func=cmd_espn_init)

    sub.add_parser("status", help="row counts + last run").set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
