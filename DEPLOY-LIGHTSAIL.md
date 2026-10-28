# Deploying the Monarch Sync to Amazon Lightsail

This guide moves **only the daily Monarch sync** (`monarch_download.py` + `refresh.sh`,
and the `build.py` + `git push` they trigger) from a Mac's launchd to an always-on
Lightsail instance. The `git push → GitHub Actions → GitHub Pages` deploy flow and the
static hosting are **unchanged** — only the cron job that pulls from Monarch relocates.

## Why move it

The sync currently depends on the Mac being awake, online, and on good WiFi at the
scheduled minute. An always-on Lightsail box removes that fragility and lets the sync
run more frequently (e.g. every few hours), so new transactions — like a freshly
deposited paycheck — appear on the dashboard within hours instead of the next day.

This pairs with the dashboard's freshness indicator ("Last synced: Nh ago • latest
transaction …"): reliable, frequent syncs make that a trustworthy signal that a
missing transaction is Monarch-side rather than a broken pipeline.

## Decision first: shared vs. separate instance

The sync adds, to whatever host runs it:
- Financial account credentials (`MONARCH_EMAIL`, `MONARCH_PASS`, MFA secret) and a
  saved browser session (`.monarch-auth.json`).
- A headless Chromium process that runs briefly (~30 s, 300–500 MB RAM) a few times a day.

- **Co-locate** with an existing instance if it has RAM headroom (1 GB comfortable) and
  you're fine with Monarch creds sharing the host.
- **Separate** small instance ($5–7/mo, 1 GB) if the host is resource-tight or you want
  financial creds isolated from other workloads (e.g. a live-trading system).

Both work with the steps below.

## Steps

### 1. Install dependencies (one time)
Ubuntu LTS:
```bash
sudo apt-get update
sudo apt-get install -y python3-pip git
pip3 install pandas playwright pyotp
python3 -m playwright install --with-deps chromium
```
`--with-deps` installs the system libraries headless Chromium needs on a bare VM — the
most common failure point when moving Playwright to a server.

### 2. Clone the repo and configure credentials
Clone over SSH with a deploy key that has **push** access (the sync pushes to `main`):
```bash
git clone git@github.com:davis-raj/spend-dashboard.git ~/spend-dashboard
```
Recreate `.env` on the box (it is gitignored, so the clone won't include it):
```
MONARCH_EMAIL=...
MONARCH_PASS=...
MONARCH_MFA_SECRET=...        # omit if 2FA is off
SPEND_NTFY_TOPIC=...          # so failure alerts still reach you
```
Attribute the auto-update commits:
```bash
git config user.email "you@example.com"
git config user.name  "Your Name"
```

### 3. Seed the Monarch session (the one manual step)
Monarch's login is SSO-first with email device-verification, which can't be automated.
`monarch_download.py --headful` captures a reusable session interactively.

- **Easiest — seed locally, copy up:**
  ```bash
  # on your Mac:
  python3 monarch_download.py --headful     # complete login in the browser window
  scp ~/spend-dashboard/.monarch-auth.json  USER@LIGHTSAIL_IP:~/spend-dashboard/
  ```
- **Alternative — seed on the box over a tunnel:** SSH with X-forwarding or a temporary
  VNC session, run `--headful` there once.

`.monarch-auth.json` is gitignored and stays on the box only.

### 4. Confirm a manual run works
```bash
cd ~/spend-dashboard && bash refresh.sh
tail -n 40 refresh.log
```
Expect a "Refresh finished" line, a commit landing on `main`, and GitHub Actions
redeploying Pages. `refresh.sh` already resolves `python3` from `PATH`, retries 3× with
0/60/180 s backoff, detects an expired session, and sends an ntfy alert on failure — no
edits needed for Linux.

### 5. Set the timezone and schedule with cron
```bash
sudo timedatectl set-timezone America/Denver   # so cron hours match local time
crontab -e
```
- **Daily (reliability parity with today):**
  ```cron
  30 10 * * *  /bin/bash /home/USER/spend-dashboard/refresh.sh
  ```
- **Every 3 hours, 7am–10pm (the real upgrade — fresher data):**
  ```cron
  0 7,10,13,16,19,22 * * *  /bin/bash /home/USER/spend-dashboard/refresh.sh
  ```
`monarch_download.py` is idempotent and the push no-ops when nothing changed, so frequent
runs are safe and cheap.

### 6. Retire the Mac job
After a day or two of clean cloud runs (to avoid double-pushes):
```bash
launchctl unload ~/Library/LaunchAgents/com.user.spend-refresh.plist
```
Keep the plist until you're confident; re-loading is trivial.

## Operating notes

- **Session expiry:** Monarch sessions eventually expire. `refresh.sh` detects this and
  sends a specific ntfy alert. To recover, re-run `--headful` on the Mac and `scp` the
  refreshed `.monarch-auth.json` back up (Step 3).
- **Logs:** everything appends to `~/spend-dashboard/refresh.log` (gitignored).
- **Resource use:** headless Chromium is memory-hungry for the few seconds it runs;
  prefer a 1 GB instance over 512 MB.
- **Nothing else changes:** `build.py`, `docs/`, the GitHub Actions workflow, and Pages
  hosting are untouched by this migration.
