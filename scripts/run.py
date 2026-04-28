"""CLI entrypoint for the nba-dashboard scrapers.

Usage:
    python -m scripts.run init           # create DB + populate teams
    python -m scripts.run schedule       # refresh games table for current season
    python -m scripts.run backfill       # run all box-score scrapers for unprocessed Final games
    python -m scripts.run daily          # refresh schedule + ingest yesterday's & today's finished games
    python -m scripts.run status         # quick row counts / last-run summary

Run with `-v` for debug logging.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Sequence

from .db import connect, init_schema
from .etl import (
    ingest_advanced_box,
    ingest_schedule,
    ingest_traditional_box,
    list_unprocessed_games,
    seed_teams,
)
from .nba import current_season


def cmd_init(args: argparse.Namespace) -> int:
    init_schema()
    with connect() as conn:
        n = seed_teams(conn)
    print(f"Schema applied. Seeded {n} teams. Current season: {current_season()}")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    season = args.season or current_season()
    with connect() as conn:
        seed_teams(conn)
        n = ingest_schedule(conn, season=season)
    print(f"Schedule synced for {season}: {n} games upserted.")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
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
        success_t += int(ok_t)
        success_a += int(ok_a)
        fail += int(not (ok_t and ok_a))
        if i % 25 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] traditional={success_t}  advanced={success_a}  failed={fail}")
    print(f"Done. traditional={success_t}/{len(todo)}, advanced={success_a}/{len(todo)}, failures={fail}")
    return 0 if fail == 0 else 1


def cmd_daily(args: argparse.Namespace) -> int:
    """Designed for cron / GitHub Actions. Refreshes schedule then ingests anything new."""
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
    return 0 if fail == 0 else 1


def cmd_status(args: argparse.Namespace) -> int:
    with connect() as conn:
        for tbl in ("teams", "players", "games",
                     "team_box_traditional", "team_box_advanced",
                     "player_box_traditional", "player_box_advanced"):
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {tbl}").fetchone()["c"]
            print(f"  {tbl:30s} {n:>8d}")
        last = conn.execute("SELECT MAX(last_attempt_utc) AS t FROM etl_runs").fetchone()
        print(f"  last_etl_run                   {last['t']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nba-dashboard")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create DB and populate teams").set_defaults(func=cmd_init)

    p = sub.add_parser("schedule", help="refresh the games table")
    p.add_argument("--season", help="e.g. 2025-26 (default: current)")
    p.set_defaults(func=cmd_schedule)

    p = sub.add_parser("backfill", help="ingest box scores for unprocessed Final games")
    p.add_argument("--season", help="e.g. 2025-26 (default: current)")
    p.add_argument("--limit", type=int, help="cap number of games this run (useful for testing)")
    p.set_defaults(func=cmd_backfill)

    sub.add_parser("daily", help="schedule refresh + new-game ingest").set_defaults(func=cmd_daily)
    sub.add_parser("status", help="row counts + last run").set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
