#!/bin/bash
# Daily Monarch refresh — run by launchd (com.user.spend-refresh).
# Downloads latest transactions (reusing saved session), rebuilds the
# dashboard, and pushes to GitHub which triggers the Pages deploy.
set -uo pipefail

cd "$HOME/spend-dashboard"

PYTHON="/usr/bin/python3"
LOG="$HOME/spend-dashboard/refresh.log"

# Private ntfy topic, read from the gitignored .env (never hardcoded here —
# refresh.sh is tracked and pushed to GitHub, so a literal topic would be public
# and spoofable). Falls back to empty, in which case the alert is skipped.
NTFY_TOPIC=""
if [ -f "$HOME/spend-dashboard/.env" ]; then
    NTFY_TOPIC="$(grep -E '^SPEND_NTFY_TOPIC=' "$HOME/spend-dashboard/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"'[:space:]')"
fi

echo "===== Refresh started: $(date) =====" >> "$LOG"

if "$PYTHON" monarch_download.py >> "$LOG" 2>&1; then
    echo "===== Refresh finished: $(date) =====" >> "$LOG"
else
    echo "===== FAILED: $(date) =====" >> "$LOG"
    if [ -n "$NTFY_TOPIC" ]; then
        curl -s -o /dev/null \
            -H "Title: Spend dashboard refresh FAILED" \
            -H "Priority: high" \
            -H "Tags: warning" \
            -d "Monarch session likely expired. Run: cd ~/spend-dashboard && python3 monarch_download.py --headful" \
            "https://ntfy.sh/$NTFY_TOPIC"
    else
        echo "  (no SPEND_NTFY_TOPIC in .env — failure alert not sent)" >> "$LOG"
    fi
fi
