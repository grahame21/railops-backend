# trainfinder_fetch_pw.py – retry-aware Playwright login
import os, json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

USERNAME = os.getenv("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.getenv("TRAINFINDER_PASSWORD", "").strip()
NEXTLEVEL = "https://trainfinder.otenko.com/Home/NextLevel"
VIEWPORT  = "https://trainfinder.otenko.com/Home/GetViewPortData"

if not USERNAME or not PASSWORD:
    print("❌ Missing credentials"); sys.exit(1)

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()
        try:
            print("🌐 Opening TrainFinder login...")
            page.goto(NEXTLEVEL, wait_until="domcontentloaded", timeout=90000)
            time.sleep(5)  # allow splash / modal fade-in

            # Try multiple selector possibilities
            selectors = ["input#UserName", "input[name='UserName']", "input[placeholder*='User']"]
            for sel in selectors:
                try:
                    page.wait_for_selector(sel, timeout=10000)
                    username_sel = sel
                    break
                except TimeoutError:
                    username_sel = None
            if not username_sel:
                raise TimeoutError("No username field found")

            page.fill(username_sel, USERNAME)
            page.fill("input#Password", PASSWORD)
            page.click("input[type='submit'], button:has-text('Log In')")
            print("🔑 Submitted login form; waiting for response...")

            try:
                page.wait_for_selector("text=LOGOUT", timeout=20000)
                print("✅ Logged in successfully")
            except TimeoutError:
                print("⚠️ Login confirmation not visible, continuing anyway")

            print("📡 Fetching train data…")
            resp = page.request.post(VIEWPORT, headers={"x-requested-with": "XMLHttpRequest"})
            if resp.status != 200:
                print(f"Retrying GET ({resp.status})")
                resp = page.request.get(VIEWPORT, headers={"x-requested-with": "XMLHttpRequest"})
            Path("trains.json").write_text(json.dumps(resp.json(), indent=2), encoding="utf-8")
            print("✅ trains.json updated")

        except Exception as e:
            print(f"❌ Headless fetch failed: {e}")
            page.screenshot(path="debug.png", full_page=True)
            Path("debug.html").write_text(page.content(), encoding="utf-8")
        finally:
            ctx.close(); browser.close()

if __name__ == "__main__":
    main()
