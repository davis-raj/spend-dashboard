#!/bin/bash
# Weekly Monarch refresh — run by launchd (com.user.spend-refresh).
# Downloads latest transactions (reusing saved session), rebuilds the
# dashboard, and pushes to GitHub which triggers the Pages deploy.
set -euo pipefail

cd "$HOME/spend-dashboard"

PYTHON="/usr/bin/python3"
LOG="$HOME/spend-dashboard/refresh.log"

echo "===== Refresh started: $(date) =====" >> "$LOG"
# monarch_download.py loads .env, downloads, rebuilds (build.py), commits & pushes
"$PYTHON" monarch_download.py >> "$LOG" 2>&1
echo "===== Refresh finished: $(date) =====" >> "$LOG"
