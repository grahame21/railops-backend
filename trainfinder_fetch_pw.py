# trainfinder_fetch_pw.py
# Headless login to TrainFinder and fetch /Home/GetViewPortData -> trains.json
# Uses Playwright (sync). Saves debug screenshots & HTML under debug_artifacts/.

import os, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

USERNAME = os.getenv("TRAINFINDER_USERNAME", "")
PASSWORD = os.getenv("TRAINFINDER_PASSWORD", "")

BASE = "https://trainfinder.otenko.com"
LOGIN_URL = f"{BASE}/Home/NextLevel"
FETCH_URL = f"{BASE}/Home/GetViewPortData"

OUT_JSON = Path("trains.json")
DBG_DIR = Path("debug_artifacts")
DBG_DIR.mkdir(parents=True, exist_ok=True)

def snap(page, name: str):
    # Save PNG and HTML for debugging
    png = DBG_DIR / f"{name}.png"
    html = DBG_DIR / f"{name}.html"
    try:
        page.screenshot(path=str(png), full_page=True)
    except Exception:
        pass
    try:
        html.write_text(page.content())
    except Exception:
        pass

def main():
    if not USERNAME or not PASSWORD:
        print("❌ Missing TRAINFINDER_USERNAME or TRAINFINDER_PASSWORD env vars.")
        raise SystemExit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage"
        ])
        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0 Safari/537.36",
        )

        # Log console to a file for extra clues
        console_log = DBG_DIR / "console.log"
        def on_console(msg):
            console_log.write_text(
                (console_log.read_text() if console_log.exists() else "")
                + f"[{msg.type()}] {msg.text()}\n"
            )
        context.on("console", on_console)

        page = context.new_page()

        print("🌐 Opening TrainFinder…")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        snap(page, "1_loaded")

        # ---- IMPORTANT: Click the top "LOGIN" tab so inputs appear ----
        try:
            print("🔘 Clicking LOGIN tab…")
            # The button is in .topnav as <div class="nav_btn">LOGIN</div>
            page.locator("div.nav_btn", has_text="LOGIN").first.click(timeout=5000)
            time.sleep(1.5)
            snap(page, "2_login_clicked")
        except Exception as e:
            print(f"⚠️ LOGIN tab not clickable (may already be open): {e}")

        # Now wait for the form fields to exist
        try:
            user_input = page.locator("input#UserName")
            pass_input = page.locator("input#Password")
            user_input.wait_for(state="visible", timeout=20000)
            pass_input.wait_for(state="visible", timeout=20000)
        except PWTimeout:
            snap(page, "err_no_inputs")
            print("❌ Headless fetch failed: username/password inputs not found.")
            raise SystemExit(1)

        print("🔑 Filling credentials…")
        user_input.fill(USERNAME)
        pass_input.fill(PASSWORD)

        # Click Remember Me if present (optional)
        try:
            page.locator("input[type=checkbox]", has_text=None).first.check(timeout=3000)
        except Exception:
            pass

        # Log In button (green)
        try:
            # The UI uses a green 'Log In' button; try a few selectors
            login_btn = (
                page.get_by_role("button", name="Log In")
                .or_(page.locator("button:has-text('Log In')"))
                .or_(page.locator("input[type=submit][value='Log In']"))
            )
            login_btn.first.click(timeout=5000)
        except Exception:
            # Fallback: press Enter on password field
            pass_input.press("Enter")
        time.sleep(2)
        snap(page, "3_after_login_click")

        # Verify login by checking the presence/absence of the modal
        # If still visible after a short wait, treat as failure.
        try:
            page.wait_for_selector("div#loginModal, .auth-window, .ui-dialog", state="detached", timeout=8000)
        except PWTimeout:
            snap(page, "err_modal_still_visible")
            print("❌ Login may have failed (modal still visible).")
            raise SystemExit(1)

        print("✅ Logged in (modal closed). Fetching live data…")

        # Use Playwright’s request context with existing cookies
        # /Home/GetViewPortData expects an AJAX POST
        res = page.request.post(
            FETCH_URL,
            headers={"x-requested-with": "XMLHttpRequest"},
            data={}
        )
        if res.ok:
            data = res.json()
            OUT_JSON.write_text(json.dumps(data, indent=2))
            print(f"✅ trains.json updated ({OUT_JSON.resolve()})")
            snap(page, "4_fetch_done")
        else:
            snap(page, "err_fetch_failed")
            print(f"❌ Fetch failed: {res.status} {res.status_text()}")
            # Save response text for debugging
            (DBG_DIR / "fetch_error.txt").write_text(res.text())
            raise SystemExit(1)

        context.close()
        browser.close()

if __name__ == "__main__":
    main()
