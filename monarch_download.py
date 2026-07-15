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

# Load .env (local runs). CI passes real env vars, which take precedence.
_env_path = os.path.join(BASE, ".env")
if os.path.exists(_env_path):
    for _line in open(_env_path):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

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


def login(page, interactive=False):
    """Reuse a saved session, or (interactive) let the user log in by hand and capture it.

    Monarch's login is SSO-first and triggers email device-verification on new
    logins, which can't be automated. So for the first run we open a real browser,
    let the human complete login, then save the session for all future headless runs.
    """
    page.goto("https://app.monarch.com/accounts", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    if "login" not in page.url.lower():
        print("✓ Already authenticated (reused saved session)")
        return

    if interactive:
        print("\n" + "=" * 62)
        print(">>> Log in MANUALLY in the browser window that just opened.")
        print(">>> Enter email, password, and any emailed verification code.")
        print(">>> Waiting up to 5 minutes for you to reach the app...")
        print("=" * 62 + "\n")
        # Wait until the URL no longer contains 'login' (successful auth + redirect)
        page.wait_for_url(lambda url: "login" not in url.lower(), timeout=300000)
        page.wait_for_timeout(4000)  # let cookies/tokens settle
        page.context.storage_state(path=AUTH_FILE)
        print("✓ Login captured — session saved to .monarch-auth.json")
        return

    # Headless with no valid session — can't pass device verification unattended.
    raise RuntimeError(
        "Not authenticated and no saved session. Seed it once interactively:\n"
        "    python3 monarch_download.py --headful"
    )


def download_csv(page):
    """Navigate to transactions and click the summary-card 'Download CSV' button.

    The transactions view defaults to the 'This year' filter, so the export is
    already YTD — no date-range UI needed (opening it just covers the button).
    On failure, save a screenshot + HTML to diagnose selector changes.
    """
    page.goto(MONARCH_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)  # let the transactions list + summary card render

    try:
        # The summary card has a "Download CSV" button, but the transaction list
        # overlaps it in the layout — a normal click gets intercepted. Dispatch the
        # click event directly to the element to bypass the pointer hit-test.
        btn = page.locator('button:has-text("Download CSV")').first
        btn.wait_for(state="attached", timeout=15000)
        with page.expect_download(timeout=60000) as download_info:
            btn.dispatch_event("click")
        download = download_info.value

        dest = os.path.join(DOWNLOAD_DIR, "transactions.csv")
        download.save_as(dest)
        print(f"✓ Downloaded CSV to {dest} ({os.path.getsize(dest)} bytes)")
        return dest

    except Exception as e:
        shot = os.path.join(BASE, "monarch-debug.png")
        html = os.path.join(BASE, "monarch-debug.html")
        try:
            page.screenshot(path=shot, full_page=True)
            with open(html, "w") as f:
                f.write(page.content())
            print(f"✗ Export failed: {e}")
            print(f"  Saved diagnostics: {shot} and {html}")
        except Exception:
            print(f"✗ Export failed: {e} (and could not save diagnostics)")
        raise


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


def run(download_only=False, headful=False):
    if not MONARCH_EMAIL or not MONARCH_PASS:
        print("Set MONARCH_EMAIL and MONARCH_PASS (in .env or environment)")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context_opts = {}
        if os.path.exists(AUTH_FILE):
            context_opts["storage_state"] = AUTH_FILE
        context = browser.new_context(**context_opts)
        page = context.new_page()
        try:
            login(page, interactive=headful)
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
    ap.add_argument("--headful", action="store_true",
                    help="Show the browser — use for the FIRST login to complete any "
                         "2FA / device verification; the session is saved for later runs")
    args = ap.parse_args()
    run(download_only=args.download_only, headful=args.headful)
