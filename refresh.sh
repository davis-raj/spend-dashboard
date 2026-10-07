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

# Retry with backoff. The 09:00 run often lands in a flaky connectivity window on
# this machine (seen as goto timeouts / ERR_INTERNET_DISCONNECTED), and a single
# miss used to forfeit the whole day's refresh. monarch_download.py is idempotent
# — it reuses the saved session, re-downloads the CSV, and the git push no-ops if
# nothing changed — so re-running is safe. Delays: 0s, 60s, 180s.
ATTEMPTS=3
DELAYS=(0 60 180)
ok=0
for i in $(seq 1 "$ATTEMPTS"); do
    delay="${DELAYS[$((i-1))]}"
    [ "$delay" -gt 0 ] && { echo "----- retry $i/$ATTEMPTS after ${delay}s -----" >> "$LOG"; sleep "$delay"; }
    if "$PYTHON" monarch_download.py >> "$LOG" 2>&1; then
        ok=1
        break
    fi
    echo "----- attempt $i/$ATTEMPTS failed: $(date) -----" >> "$LOG"
done

if [ "$ok" -eq 1 ]; then
    echo "===== Refresh finished: $(date) =====" >> "$LOG"
else
    echo "===== FAILED after $ATTEMPTS attempts: $(date) =====" >> "$LOG"
    # Distinguish an expired session (needs manual re-seed) from a transient
    # network failure (will likely clear on its own), so the alert says the right
    # thing. The session-expiry case prints a specific line in the log.
    if grep -q "no saved session" "$LOG" 2>/dev/null && \
       [ -n "$(tail -40 "$LOG" | grep 'no saved session')" ]; then
        BODY="Monarch session expired. Run: cd ~/spend-dashboard && python3 monarch_download.py --headful"
    else
        BODY="Monarch refresh failed $ATTEMPTS times (likely a transient network issue at run time). Data is unchanged; it should self-heal tomorrow. Check refresh.log if it persists."
    fi
    if [ -n "$NTFY_TOPIC" ]; then
        curl -s -o /dev/null \
            -H "Title: Spend dashboard refresh FAILED" \
            -H "Priority: high" \
            -H "Tags: warning" \
            -d "$BODY" \
            "https://ntfy.sh/$NTFY_TOPIC"
    else
        echo "  (no SPEND_NTFY_TOPIC in .env — failure alert not sent)" >> "$LOG"
    fi
fi
