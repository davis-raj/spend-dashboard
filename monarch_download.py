#!/usr/bin/env python3
"""
Monarch Transactions CSV Download + Dashboard Rebuild.

Local use:   python monarch_download.py            (download -> build -> commit/push)
CI use:      python monarch_download.py --download-only   (download only; workflow builds/deploys)

Env vars:
  MONARCH_EMAIL, MONARCH_PASS   (required)
  MONARCH_MFA_SECRET            (optional TOTP secret, if 2FA is enabled)
"""
import os
import sys
import argparse
import subprocess
from playwright.sync_api import sync_playwright

# Paths relative to this file so it works locally AND in CI checkout
BASE = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE, "data")
AUTH_FILE = os.path.join(BASE, ".monarch-auth.json")

MONARCH_URL = "https://app.monarch.com/transactions"
MONARCH_EMAIL = os.environ.get("MONARCH_EMAIL", "")
MONARCH_PASS = os.environ.get("MONARCH_PASS", "")
MONARCH_MFA_SECRET = os.environ.get("MONARCH_MFA_SECRET", "")

START_DATE = "01/01/2026"
END_DATE = "12/31/2026"


def _maybe_handle_mfa(page):
    """If a TOTP field appears and a secret is configured, fill the current code."""
    if not MONARCH_MFA_SECRET:
        return
    try:
        otp = page.locator('input[autocomplete="one-time-code"], input[name*="otp"], input[name*="code"], input[inputmode="numeric"]').first
        if otp.is_visible(timeout=5000):
            import pyotp
            code = pyotp.TOTP(MONARCH_MFA_SECRET.replace(" ", "")).now()
            otp.fill(code)
            page.locator('button[type="submit"]').first.click()
            print("✓ Submitted MFA code")
    except Exception:
        pass  # No MFA prompt — normal


def login(page):
    """Login to Monarch or reuse saved auth."""
    page.goto("https://app.monarchmoney.com/login", wait_until="networkidle")
    if "transactions" in page.url or "dashboard" in page.url:
        print("✓ Already authenticated (reused session)")
        return
    page.locator('input[type="email"], input[name="email"]').fill(MONARCH_EMAIL)
    page.locator('input[type="password"], input[name="password"]').fill(MONARCH_PASS)
    page.locator('button[type="submit"]').click()
    _maybe_handle_mfa(page)
    page.wait_for_url("**/dashboard**", timeout=30000)
    print("✓ Logged in")
    page.context.storage_state(path=AUTH_FILE)


def download_csv(page):
    """Navigate to transactions, set date range, download CSV."""
    page.goto(MONARCH_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)

    date_btn = page.locator('button:has-text("Date"), [data-testid*="date"]').first
    date_btn.click()
    page.wait_for_timeout(1000)

    start_input = page.locator('input[placeholder*="Start"], input[name*="start"]').first
    start_input.clear()
    start_input.fill(START_DATE)

    end_input = page.locator('input[placeholder*="End"], input[name*="end"]').first
    end_input.clear()
    end_input.fill(END_DATE)

    apply_btn = page.locator('button:has-text("Apply"), button:has-text("Done"), button:has-text("Update")').first
    if apply_btn.is_visible(timeout=2000):
        apply_btn.click()
    page.wait_for_timeout(2000)

    with page.expect_download() as download_info:
        page.locator('button:has-text("Download"), a:has-text("Download CSV"), [aria-label*="download"]').first.click()
    download = download_info.value

    # Canonical filename (lowercase) — build.py matches case-insensitively by mtime
    dest = os.path.join(DOWNLOAD_DIR, "transactions.csv")
    download.save_as(dest)
    print(f"✓ Downloaded CSV to {dest} ({os.path.getsize(dest)} bytes)")
    return dest


def rebuild_dashboard():
    result = subprocess.run([sys.executable, "build.py"], cwd=BASE, capture_output=True, text=True)
    if result.returncode == 0:
        print("✓ Dashboard rebuilt")
        print(result.stdout.strip())
    else:
        print(f"✗ Build failed: {result.stderr}")
        sys.exit(1)


def push_to_github():
    status = subprocess.run(["git", "status", "--porcelain"], cwd=BASE, capture_output=True, text=True)
    if not status.stdout.strip():
        print("✓ No changes to push")
        return
    subprocess.run(["git", "add", "-A"], cwd=BASE, check=True)
    subprocess.run(["git", "commit", "-m", "Auto-update: daily transaction refresh"], cwd=BASE, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=BASE, check=True)
    print("✓ Pushed to GitHub")


def run(download_only=False):
    if not MONARCH_EMAIL or not MONARCH_PASS:
        print("Set MONARCH_EMAIL and MONARCH_PASS environment variables")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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

    if download_only:
        print("\n✅ Download complete (build/deploy handled by workflow)")
        return

    rebuild_dashboard()
    push_to_github()
    print("\n✅ Done — dashboard updated!")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-only", action="store_true",
                    help="Only download the CSV; skip build and git push (for CI)")
    args = ap.parse_args()
    run(download_only=args.download_only)
