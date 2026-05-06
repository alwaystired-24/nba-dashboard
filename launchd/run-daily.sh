#!/bin/bash
# Daily NBA dashboard ETL — invoked by launchd
# Logs to ~/Library/Logs/nba-dashboard-daily.log

set -e

REPO="/Users/edwardlam/Documents/thefifthquarter/nba-project/nba-dashboard"
LOG="$HOME/Library/Logs/nba-dashboard-daily.log"

# Append timestamped header
echo "" >> "$LOG"
echo "==== $(date) — daily run start ====" >> "$LOG"

cd "$REPO"
source /Users/edwardlam/.venvs/nba-dashboard/bin/activate

# Load .env if present (THE_ODDS_API_KEY etc.)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Run daily ETL — captures both stdout and stderr
/Users/edwardlam/.venvs/nba-dashboard/bin/python -m scripts.run daily >> "$LOG" 2>&1 || echo "daily exited non-zero: $?" >> "$LOG"
