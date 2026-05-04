"""
Migrate SQLite data to Supabase Postgres.

Usage:
    python -m scripts.migrate_sqlite_to_pg

Requirements:
    - DATABASE_URL set in .env (Postgres connection string)
    - data/nba.db exists (SQLite source)
    - Postgres schema already applied (sql/postgres/schema.sql)

What it does:
    - Reads each table from SQLite
    - Inserts into Postgres via psycopg2 executemany (batched, fast)
    - Preserves dependency order: teams, players, games, then dependents
    - Uses ON CONFLICT DO NOTHING — safe to re-run if interrupted
    - Reports row counts before and after for verification

Notes:
    - Skips `lost_and_found` (orphan diagnostic table, not in schema)
    - Skips `sqlite_sequence` (SQLite metadata)
    - For tables with auto-increment PKs in Postgres (shots, odds_snapshots),
      we let Postgres assign new IDs — original SQLite rowids are not preserved.
"""

from __future__ import annotations
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = REPO_ROOT / "data" / "nba.db"
BATCH_SIZE = 1000  # rows per Postgres insert batch

load_dotenv(REPO_ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not set in .env")
if not SQLITE_PATH.exists():
    sys.exit(f"ERROR: SQLite source not found at {SQLITE_PATH}")

# ---------------------------------------------------------------------------
# Migration plan — order matters for foreign keys
# ---------------------------------------------------------------------------
# Each entry: (table_name, columns_to_copy, conflict_target_for_on_conflict)
#   - columns_to_copy: explicit columns we read+write (avoids schema drift surprises)
#   - conflict_target: PK columns for ON CONFLICT DO NOTHING; None = no PK conflict
#                      handling (used for auto-increment tables)
#
# Tables with BIGSERIAL PKs in Postgres (shots, odds_snapshots): we drop the
# SQLite rowid PK column and let Postgres assign new IDs.

MIGRATION_PLAN = [
    # ---- core entities (no FKs) ----
    ("teams",
     ["team_id", "abbreviation", "full_name", "nickname", "city",
      "conference", "division"],
     ["team_id"]),

    ("players",
     ["player_id", "full_name", "first_name", "last_name", "is_active",
      "last_seen_date"],
     ["player_id"]),

    # ---- games (depends on teams) ----
    ("games",
     ["game_id", "season", "season_type", "game_date", "game_datetime_et",
      "home_team_id", "away_team_id", "home_score", "away_score", "status",
      "arena", "attendance"],
     ["game_id"]),

    # ---- box scores (depend on games + teams + players) ----
    ("team_box_traditional",
     ["game_id", "team_id", "is_home", "minutes",
      "fgm", "fga", "fg_pct", "fg3m", "fg3a", "fg3_pct",
      "ftm", "fta", "ft_pct", "oreb", "dreb", "reb",
      "ast", "stl", "blk", "tov", "pf", "pts", "plus_minus"],
     ["game_id", "team_id"]),

    ("team_box_advanced",
     ["game_id", "team_id", "minutes", "off_rating", "def_rating", "net_rating",
      "pace", "pie", "ast_pct", "ast_to_tov", "ast_ratio",
      "oreb_pct", "dreb_pct", "reb_pct", "tov_pct",
      "efg_pct", "ts_pct", "poss"],
     ["game_id", "team_id"]),

    ("player_box_traditional",
     ["game_id", "player_id", "team_id", "is_starter", "minutes",
      "fgm", "fga", "fg_pct", "fg3m", "fg3a", "fg3_pct",
      "ftm", "fta", "ft_pct", "oreb", "dreb", "reb",
      "ast", "stl", "blk", "tov", "pf", "pts", "plus_minus"],
     ["game_id", "player_id"]),

    ("player_box_advanced",
     ["game_id", "player_id", "team_id", "minutes",
      "off_rating", "def_rating", "net_rating", "usg_pct", "pie",
      "ast_pct", "ast_to_tov", "ast_ratio",
      "oreb_pct", "dreb_pct", "reb_pct", "tov_pct",
      "efg_pct", "ts_pct", "pace", "poss"],
     ["game_id", "player_id"]),

    # ---- quarter scores ----
    ("team_quarter_scores",
     ["game_id", "team_id", "pts_q1", "pts_q2", "pts_q3", "pts_q4",
      "pts_ot1", "pts_ot2", "pts_ot3", "pts_ot4", "pts_total", "fetched_utc"],
     ["game_id", "team_id"]),

    # ---- ETL bookkeeping ----
    ("etl_runs",
     ["game_id", "endpoint", "status", "last_attempt_utc", "error"],
     ["game_id", "endpoint"]),

    # ---- odds (auto-increment PK in Postgres — drop snapshot_id) ----
    ("odds_snapshots",
     ["fetched_utc", "game_id", "home_team_id", "away_team_id",
      "bookmaker", "market", "home_price", "away_price",
      "spread_home", "spread_away", "total_line", "over_price", "under_price",
      "is_closing", "snapshot_phase", "event_id", "commence_time_utc",
      "game_date"],
     None),  # let Postgres generate snapshot_id

    ("odds_event_mapping",
     ["event_id", "game_id", "home_team_name", "away_team_name",
      "commence_utc", "created_utc"],
     ["event_id"]),

    # ---- ESPN content ----
    ("injuries",
     ["team_id", "player_id", "player_name", "status", "detail",
      "return_date", "fetched_utc"],
     ["team_id", "player_name"]),

    ("team_news",
     ["article_id", "team_id", "headline", "summary", "category",
      "published_utc", "url", "fetched_utc"],
     ["article_id", "team_id"]),
]


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------

def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    table: str,
    columns: list[str],
    conflict_target: list[str] | None,
) -> tuple[int, int]:
    """
    Migrate one table. Returns (source_count, inserted_count).

    Uses ON CONFLICT DO NOTHING when conflict_target is provided so reruns
    are idempotent. For auto-increment tables, no conflict target is used.
    """
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()

    # Source row count
    sqlite_cur.execute(f"SELECT COUNT(*) FROM {table};")
    src_count = sqlite_cur.fetchone()[0]
    if src_count == 0:
        print(f"  {table}: 0 rows in SQLite, skipping")
        return (0, 0)

    # Read all rows
    cols_csv = ", ".join(columns)
    sqlite_cur.execute(f"SELECT {cols_csv} FROM {table};")
    rows = sqlite_cur.fetchall()

    # Build INSERT
    placeholders = ", ".join(["%s"] * len(columns))
    if conflict_target:
        on_conflict = f"ON CONFLICT ({', '.join(conflict_target)}) DO NOTHING"
    else:
        on_conflict = ""
    sql = f"INSERT INTO {table} ({cols_csv}) VALUES ({placeholders}) {on_conflict};"

    # Batch insert
    execute_batch(pg_cur, sql, rows, page_size=BATCH_SIZE)
    pg_conn.commit()

    # Verify destination count
    pg_cur.execute(f"SELECT COUNT(*) FROM {table};")
    dst_count = pg_cur.fetchone()[0]

    sqlite_cur.close()
    pg_cur.close()
    return (src_count, dst_count)


def main() -> int:
    print(f"Source:      {SQLITE_PATH}")
    print(f"Destination: Postgres via DATABASE_URL")
    print()

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = psycopg2.connect(DATABASE_URL)

    print(f"{'Table':<28} {'SQLite':>8} {'Postgres':>10} {'Status':>8}")
    print("-" * 60)

    failures = []
    for table, columns, conflict_target in MIGRATION_PLAN:
        try:
            src, dst = migrate_table(
                sqlite_conn, pg_conn, table, columns, conflict_target
            )
            status = "OK" if dst >= src else "MISMATCH"
            print(f"{table:<28} {src:>8} {dst:>10} {status:>8}")
            if dst < src:
                failures.append((table, src, dst))
        except Exception as e:
            print(f"{table:<28} ERROR: {e}")
            failures.append((table, None, str(e)))
            pg_conn.rollback()

    sqlite_conn.close()
    pg_conn.close()

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("Migration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
