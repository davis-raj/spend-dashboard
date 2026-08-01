#!/bin/bash
# Daily Monarch refresh — run by launchd (com.user.spend-refresh).
# Downloads latest transactions (reusing saved session), rebuilds the
# dashboard, and pushes to GitHub which triggers the Pages deploy.
set -uo pipefail

cd "$HOME/spend-dashboard"

PYTHON="/usr/bin/python3"
LOG="$HOME/spend-dashboard/refresh.log"
NTFY_TOPIC="trading-signals-raj"

echo "===== Refresh started: $(date) =====" >> "$LOG"

if "$PYTHON" monarch_download.py >> "$LOG" 2>&1; then
    echo "===== Refresh finished: $(date) =====" >> "$LOG"
else
    echo "===== FAILED: $(date) =====" >> "$LOG"
    curl -s -o /dev/null \
        -H "Title: Spend dashboard refresh FAILED" \
        -H "Priority: high" \
        -H "Tags: warning" \
        -d "Monarch session likely expired. Run: cd ~/spend-dashboard && python3 monarch_download.py --headful" \
        "https://ntfy.sh/$NTFY_TOPIC"
fi
