# trainfinder_fetch_pw.py
# Simplified login + fetch for https://trainfinder.otenko.com/Home/NextLevel

import os, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

USERNAME = os.getenv("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.getenv("TRAINFINDER_PASSWORD", "").strip()

if not USERNAME or not PASSWORD:
    print("❌ Missing TRAINFINDER_USERNAME or TRAINFINDER_PASSWORD")
    sys.exit(1)

NEXTLEVEL = "https://trainfinder.otenko.com/Home/NextLevel"
VIEWPORT = "https://trainfinder.otenko.com/Home/GetViewPortData"

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()

        try:
            print("🌐 Opening TrainFinder...")
            page.goto(NEXTLEVEL, wait_until="domcontentloaded", timeout=60000)

            # Wait for username + password inputs
            page.wait_for_selector("input#UserName", timeout=15000)
            page.wait_for_selector("input#Password", timeout=15000)

            print("📝 Filling login form...")
            page.fill("input#UserName", USERNAME)
            page.fill("input#Password", PASSWORD)

            # Click Log In button
            page.click("input[type='submit'][value='Log In']")

            # Wait for login to finish (either the modal closes or LOGOUT appears)
            try:
                page.wait_for_selector("text=LOGOUT", timeout=15000)
                print("✅ Logged in successfully")
            except TimeoutError:
                print("⚠️ Could not confirm login visually, continuing...")

            # Fetch JSON data
            print("📡 Fetching train data...")
            resp = page.request.post(VIEWPORT, headers={"x-requested-with": "XMLHttpRequest"})
            if resp.status != 200:
                print(f"❌ Fetch failed (HTTP {resp.status}) — retrying with GET")
                resp = page.request.get(VIEWPORT, headers={"x-requested-with": "XMLHttpRequest"})

            data = resp.json()
            Path("trains.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            print("✅ trains.json updated")

        except Exception as e:
            print(f"❌ Headless fetch failed: {e}")
            page.screenshot(path="debug.png", full_page=True)
            Path("debug.html").write_text(page.content(), encoding="utf-8")

        finally:
            ctx.close()
            browser.close()

if __name__ == "__main__":
    main()
