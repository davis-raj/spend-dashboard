#!/usr/bin/env python3
"""
Monarch Transactions CSV Download + Dashboard Rebuild
Downloads YTD transactions from Monarch, rebuilds spend-dashboard, pushes to GitHub.
Schedule: daily via cron
"""
import os
import sys
import glob
import shutil
import subprocess
from playwright.sync_api import sync_playwright

MONARCH_URL = "https://app.monarch.com/transactions"
MONARCH_EMAIL = os.environ.get("MONARCH_EMAIL", "")
MONARCH_PASS = os.environ.get("MONARCH_PASS", "")
DOWNLOAD_DIR = os.path.expanduser("~/spend-dashboard/data")
DASHBOARD_DIR = os.path.expanduser("~/spend-dashboard")
AUTH_FILE = os.path.expanduser("~/spend-dashboard/.monarch-auth.json")

START_DATE = "01/01/2026"
END_DATE = "12/31/2026"


def login(page):
    """Login to Monarch or reuse saved auth."""
    page.goto("https://app.monarchmoney.com/login", wait_until="networkidle")
    # Check if already logged in
    if "transactions" in page.url or "dashboard" in page.url:
        print("✓ Already authenticated")
        return
    # Fill login
    page.locator('input[type="email"], input[name="email"]').fill(MONARCH_EMAIL)
    page.locator('input[type="password"], input[name="password"]').fill(MONARCH_PASS)
    page.locator('button[type="submit"]').click()
    page.wait_for_url("**/dashboard**", timeout=30000)
    print("✓ Logged in")
    # Save auth state
    page.context.storage_state(path=AUTH_FILE)


def download_csv(page):
    """Navigate to transactions, set date range, download CSV."""
    page.goto(MONARCH_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)

    # Click the date filter (top right)
    date_btn = page.locator('button:has-text("Date"), [data-testid*="date"]').first()
    date_btn.click()
    page.wait_for_timeout(1000)

    # Set start date
    start_input = page.locator('input[placeholder*="Start"], input[name*="start"]').first()
    start_input.clear()
    start_input.fill(START_DATE)

    # Set end date
    end_input = page.locator('input[placeholder*="End"], input[name*="end"]').first()
    end_input.clear()
    end_input.fill(END_DATE)

    # Apply/confirm date range
    apply_btn = page.locator('button:has-text("Apply"), button:has-text("Done"), button:has-text("Update")').first()
    if apply_btn.is_visible(timeout=2000):
        apply_btn.click()
    page.wait_for_timeout(2000)

    # Click Download CSV
    with page.expect_download() as download_info:
        page.locator('button:has-text("Download"), a:has-text("Download CSV"), [aria-label*="download"]').first().click()
    download = download_info.value

    # Save to data directory, overwriting previous
    dest = os.path.join(DOWNLOAD_DIR, "transactions.csv")
    download.save_as(dest)
    print(f"✓ Downloaded CSV to {dest} ({os.path.getsize(dest)} bytes)")
    return dest


def rebuild_dashboard():
    """Run build.py to regenerate dashboard."""
    result = subprocess.run(
        [sys.executable, "build.py"],
        cwd=DASHBOARD_DIR,
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("✓ Dashboard rebuilt")
    else:
        print(f"✗ Build failed: {result.stderr}")
        sys.exit(1)


def push_to_github():
    """Commit and push if there are changes."""
    os.chdir(DASHBOARD_DIR)
    # Check for changes
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if not status.stdout.strip():
        print("✓ No changes to push")
        return
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "commit", "-m", "Auto-update: daily transaction refresh"], check=True)
    subprocess.run(["git", "push", "origin", "main"], check=True)
    print("✓ Pushed to GitHub")


def run():
    if not MONARCH_EMAIL or not MONARCH_PASS:
        print("Set MONARCH_EMAIL and MONARCH_PASS environment variables")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Reuse auth if available
        context_opts = {}
        if os.path.exists(AUTH_FILE):
            context_opts["storage_state"] = AUTH_FILE
        context = browser.new_context(**context_opts)
        page = context.new_page()

        try:
            login(page)
            download_csv(page)
            context.storage_state(path=AUTH_FILE)
        finally:
            browser.close()

    rebuild_dashboard()
    push_to_github()
    print("\n✅ Done — dashboard updated!")


if __name__ == "__main__":
    run()
