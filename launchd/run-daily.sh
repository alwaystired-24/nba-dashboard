#!/bin/bash
# Daily NBA dashboard ETL — invoked by launchd
# Logs to ~/Library/Logs/nba-dashboard-daily.log

set -e

REPO="/Users/edwardlam/Documents/nba-dashboard"
LOG="$HOME/Library/Logs/nba-dashboard-daily.log"

# Append timestamped header
echo "" >> "$LOG"
echo "==== $(date) — daily run start ====" >> "$LOG"

cd "$REPO"
source .venv/bin/activate

# Load .env if present (THE_ODDS_API_KEY etc.)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Run daily ETL — captures both stdout and stderr
python -m scripts.run daily >> "$LOG" 2>&1 || echo "daily exited non-zero: $?" >> "$LOG"

echo "==== $(date) — done ====" >> "$LOG"
