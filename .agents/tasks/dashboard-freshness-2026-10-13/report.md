# Spending Dashboard Freshness Investigation

**Date of investigation:** reference "today" = 2026-10-13 (per brief)
**Mode:** read-only diagnosis — no files modified, no scripts run, no downloads triggered
**Target:** `/Users/P2704972/spend-dashboard`

> **Clock note:** The filesystem and logs on this machine report dates in **October 2026**, and the newest log entry is **Thu Oct 22 2026**, which is *after* the brief's reference date of 2026-10-13. I report the real timestamps verbatim and judge staleness against the newest evidence actually present (Oct 22), noting where that differs from the brief's stated "today."

---

## Summary answer

**The dashboard data file (`docs/data.json`) is NOT stale relative to the raw CSV — they are perfectly in sync.** Both top out at the same newest transaction, **2026-10-19**. The build/deploy pipeline is healthy.

**What IS broken is the data *source*: the Monarch download step has stopped bringing in new transactions.** The newest transaction has been frozen at **2026-10-19** across the Oct 20 and Oct 21 runs (both reported success but produced *no new data* — the Oct 21 run explicitly logged "No changes to push"), and the most recent run on **Thu Oct 22 10:37:20 MDT 2026 FAILED after 3 attempts** with `net::ERR_INTERNET_DISCONNECTED` / `Page.goto: Timeout`.

**Verdict:** The dashboard is only as fresh as **2026-10-19**. If "today" is 2026-10-13, nothing is actually stale (future data cannot exist yet). Measured against the newest log evidence (Oct 22), the data is **~3 days stale**, and the break is unambiguously in the **download step (`monarch_download.py`), not the build, deploy, or scheduler** — the scheduler is firing on time every day.

---

## Evidence

### Q1 — Most recent transaction date in `data/transactions.csv`

- Header: `Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner,Reviewed,Id`
- Total rows: 5,873 lines (5,872 data rows); date range spans **2021-04-28 → 2026-10-19**.
- **Max transaction date = `2026-10-19`.** Newest rows:
  - `2026-10-19,Apple,Credit Card Payment,...,-2000.00`
  - `2026-10-19,Walmart,Shopping,...,-27.42`
  - `2026-10-19,Konark Grocers,Groceries,...,-95.38`

### Q2 — What `docs/data.json` reflects, and is it stale vs. the CSV?

`build.py` writes **no** `generated_at`/`meta` timestamp (top-level keys are `monthly, categories, catByMonth, incomeCategories, incByMonth, transactions, incomeTransactions`), so freshness is judged by the transactions embedded in it:

- `transactions` (expenses): 2,097 entries, **max date = `2026-10-19`**, min = `2025-01-01`.
- `incomeTransactions`: 181 entries, max date = `2026-10-14`.
- Last monthly bucket: `{"month": "2026-10", "expenses": 15106.79, "income": 6753.66, "transfers": 2500.0}`.

**Conclusion:** `docs/data.json` max date (**2026-10-19**) == CSV max date (**2026-10-19**). **`data.json` is in sync with the CSV — it is NOT stale relative to the CSV.** The build step is faithfully reflecting the latest raw data it was given. (Config `INCLUDE_YEARS = [2025, 2026]` explains why only 2,097 of 5,872 rows appear — this is expected filtering, not a bug.)

### Q3 — Filesystem modification times (`stat`), vs. reference date

| File | Modified (local) |
|------|------------------|
| `data/transactions.csv` | **2026-10-21 10:30:17** |
| `docs/data.json` | **2026-10-21 10:30:19** |
| `docs/index.html` | 2026-08-02 12:10:49 (static shell; unchanged, expected) |
| `refresh.log` | **2026-10-22 10:37:20** (last write = the failed run) |
| `launchd.log` | 2026-07-21 09:00:04, **size 0 bytes** (empty; stdout/stderr go to `refresh.log` instead) |

Interpretation: the CSV and data.json were both *touched* on 2026-10-21 (the download re-wrote the CSV byte-for-byte and the build re-ran), but their **content** did not advance past 2026-10-19. `refresh.log` was last written 2026-10-22 by the failed run. `launchd.log` is empty, which is normal here — `refresh.sh` appends everything to `refresh.log`, not launchd.log.

### Q4 — Log tails: last run timing and outcome

Run markers from `refresh.log` (the scheduler fires daily at 10:30):

```
===== Refresh started:  Tue Oct 20 10:30:02 MDT 2026 =====   -> Pushed to GitHub (new data)
===== Refresh finished: Tue Oct 20 10:30:22 MDT 2026 =====
===== Refresh started:  Wed Oct 21 10:30:02 MDT 2026 =====   -> "No changes to push"
===== Refresh finished: Wed Oct 21 10:30:19 MDT 2026 =====
===== Refresh started:  Thu Oct 22 10:30:27 MDT 2026 =====
----- attempt 1/3 failed: Thu Oct 22 10:30:34 MDT 2026 -----
----- attempt 2/3 failed: Thu Oct 22 10:32:08 MDT 2026 -----
----- attempt 3/3 failed: Thu Oct 22 10:37:20 MDT 2026 -----
===== FAILED after 3 attempts: Thu Oct 22 10:37:20 MDT 2026 =====
```

- **Last fully successful run that changed data:** Tue **Oct 20 10:30** — log shows `a095949..f8ddefa main -> main`, `✓ Pushed to GitHub`, `✅ Done — dashboard updated!`.
- **Oct 21 10:30:** ran successfully but logged `✓ No changes to push` — Monarch returned the same CSV (still ending 2026-10-19), so nothing advanced.
- **Oct 22 10:30 (most recent):** **FAILED.** All three attempts died in `monarch_download.py:64` at `page.goto("https://app.monarch.com/accounts")`:
  - attempt 1: `playwright._impl._errors.Error: Page.goto: net::ERR_INTERNET_DISCONNECTED`
  - attempts 2 & 3: `playwright._impl._errors.TimeoutError: Page.goto: Timeout 30000ms exceeded.`
- `launchd.log` is empty (0 bytes) — no separate content to quote.
- Note: this is **not** a session-expiry failure. Earlier in the log (Oct 1 and Oct 4) there were `RuntimeError: Not authenticated and no saved session` failures, but since Oct 5 the saved session works (`✓ Already authenticated (reused saved session)`). The Oct 22 failure is purely a **network connectivity** failure at run time.

### Q5 — How updates are supposed to happen, and is automation running?

- **Scheduler (launchd):** `~/Library/LaunchAgents/com.user.spend-refresh.plist`, label `com.user.spend-refresh`, runs `/bin/bash /Users/P2704972/spend-dashboard/refresh.sh` on `StartCalendarInterval` **Hour 10 / Minute 30** (daily 10:30 local). **The scheduler is firing reliably** — the log shows a 10:30 run essentially every day from Oct 8 through Oct 22. **Automation is running.**
- **`refresh.sh`:** `cd ~/spend-dashboard`, then up to **3 attempts** (delays 0/60/180s) of `python3 monarch_download.py`. On success writes "Refresh finished"; on failure writes "FAILED after N attempts" and (if `SPEND_NTFY_TOPIC` is set in `.env`) sends an ntfy push alert. The script's own comments acknowledge the 10:30-ish window is "a flaky connectivity window on this machine."
- **`monarch_download.py`:** downloads the CSV via a Playwright browser session to `app.monarch.com`, rebuilds via `build.py`, then git-commits/pushes (idempotent; no-ops if unchanged).
- **`Makefile`:** `make refresh` = `monarch_download.py`; `make build` = `build.py`; `make serve` = local http server. Consistent with the above.
- **`.github/workflows/deploy.yml`:** on `push` to `main` (or manual `workflow_dispatch`): checkout → setup Python 3.11 → `pip install pandas` → `python build.py` → upload `docs/` → deploy to GitHub Pages. So **GitHub Pages redeploys only when a commit is pushed to `main`**; the last such push was **Oct 20 (commit f8ddefa)**. `git status` is clean and `git log` confirms the last auto-update commit is `f8ddefa 2026-10-20 ... Auto-update: daily transaction refresh`.

### Chain-of-custody of the "freeze"

- Oct 20 10:30 — downloaded CSV, data advanced, **pushed `f8ddefa`** (last commit). Data through 2026-10-19.
- Oct 21 10:30 — downloaded same CSV (677,130 bytes, 5,809 dedup rows), rebuilt identically (2,097 tx), **"No changes to push."** Still 2026-10-19.
- Oct 22 10:30 — **network failure**, no download, no change.

The newest transaction being 2026-10-19 even though successful runs happened on Oct 20 and Oct 21 means Monarch itself was not returning transactions dated Oct 20/21 at download time (weekend/pending-posting lag is a plausible benign explanation), and then Oct 22 could not connect at all.

---

## Conclusions

1. **Build step: healthy.** `build.py` + `pipeline/*` correctly transform the CSV into `data.json`; the two are byte-consistent on content (both end 2026-10-19).
2. **Deploy step: healthy.** GitHub Actions deploys on push; the last push (f8ddefa, Oct 20) succeeded. Working tree is clean.
3. **Scheduler: healthy.** launchd fires daily at 10:30 and has done so consistently.
4. **Download step: this is the failure point.** The most recent scheduled run (Thu Oct 22 10:37:20 MDT 2026) **failed all 3 attempts** with `ERR_INTERNET_DISCONNECTED` / `goto` timeouts — a transient **network connectivity** problem during the 10:30 window, not a session/auth problem and not a code bug.
5. **Net freshness:** data is current **as of 2026-10-19**. Against the brief's reference of 2026-10-13 nothing is overdue; against the newest log evidence (Oct 22) the data is ~3 days behind, driven by one benign "no new data" day (Oct 21) and one network-failed day (Oct 22).

## Recommendations (nothing implemented)

- **Primarily, wait one cycle.** `refresh.sh` is idempotent and self-healing; the script's own failure message says "Data is unchanged; it should self-heal tomorrow." The Oct 22 failure looks transient.
- **If it does not self-heal,** manually run the refresh when connectivity is good: `cd ~/spend-dashboard && python3 monarch_download.py` (or `make refresh`). This re-downloads, rebuilds, and pushes — triggering the Pages deploy.
- **To reduce repeated 10:30 network flakiness,** consider moving the launchd `StartCalendarInterval` off the known-flaky window, or adding more retry attempts / longer backoff in `refresh.sh`.
- **Confirm failure alerts are actually reaching you:** verify `SPEND_NTFY_TOPIC` is set in `.env` — if empty, `refresh.sh` silently skips the ntfy alert (logs "no SPEND_NTFY_TOPIC in .env — failure alert not sent"), so a persistent outage would go unnoticed.
- **Optional hardening:** have `build.py` emit a `generated_at`/`latest_transaction_date` field into `data.json` and surface it in `docs/index.html`, so staleness is visible on the dashboard itself instead of requiring log forensics.
- **No action needed** on build, deploy, scheduler, auth/session, or the GitHub workflow — all verified working.
