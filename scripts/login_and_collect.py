#!/usr/bin/env python3
import json, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

# ==== CONFIG ====
BASE = "https://trainfinder.otenko.com"
NEXTLEVEL = f"{BASE}/home/nextlevel"
DATA_URL = f"{BASE}/Home/GetViewPortData"
COOKIES_PATH = Path("cookie.txt")
OUTPUT_PATH = Path("trains.json")

VIEWPORTS = [
    (-37.8136, 144.9631, 12),   # Melbourne
    (-33.8688, 151.2093, 12),   # Sydney
    (-27.4705, 153.0260, 11),   # Brisbane
    (-34.9285, 138.6007, 11),   # Adelaide
    (-31.9505, 115.8605, 11),   # Perth
    (-42.8821, 147.3240, 11),   # Hobart
    (-35.2820, 149.1287, 12),   # Canberra
    (-25.2744, 133.7751, 5)     # Central Australia
]

PAUSE_AFTER_LOGIN_SEC = 5
DEBUG_DIR = Path("debug"); DEBUG_DIR.mkdir(exist_ok=True)

# ==== UTIL ====
def log(msg): print(msg, flush=True)
def dump_debug(page, name):
    (DEBUG_DIR / f"{name}.html").write_text(page.content())
    page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)

# ==== LOGIN ====
def login(page, user, pwd):
    log("🌐 Opening NextLevel…")
    page.goto(NEXTLEVEL, wait_until="load", timeout=60000)
    page.wait_for_timeout(2000)

    try:
        page.click("div.nav_btn:has-text('Login')", timeout=3000)
        log("🪟 Login modal opened")
    except Exception:
        log("⚠️ Could not click Login nav_btn — continuing")

    try:
        page.wait_for_selector("input#useR_name", timeout=8000)
        page.wait_for_selector("input#pasS_word", timeout=8000)
        log("🧾 Found username & password inputs")
    except Exception as e:
        dump_debug(page, "err_no_inputs")
        raise SystemExit("❌ Login fields not found (see debug/err_no_inputs.html)")

    page.fill("input#useR_name", user)
    page.fill("input#pasS_word", pwd)
    log("✏️ Credentials entered")

    try:
        page.click("div.button.button-green:has-text('Log In')", timeout=5000)
    except Exception:
        page.evaluate("attemptAuthentication();")
    log("🚪 Submitted login form")

    # Wait for .ASPXAUTH cookie
    for _ in range(10):
        cookies = page.context.cookies(BASE)
        if any(c.get("name", "").lower().startswith(".aspxauth") for c in cookies):
            log("✅ Auth cookie detected")
            break
        time.sleep(1)
    else:
        dump_debug(page, "debug_no_cookie_after_login")
        raise SystemExit("❌ No auth cookie created after login")

    log(f"⏳ Sleeping {PAUSE_AFTER_LOGIN_SEC}s after login…")
    time.sleep(PAUSE_AFTER_LOGIN_SEC)
    page.context.storage_state(path=str(COOKIES_PATH))
    log(f"💾 Cookie saved to {COOKIES_PATH}")

# ==== FETCH DATA ====
def fetch_trains(context):
    page = context.new_page()
    trains = []
    for lat, lng, zm in VIEWPORTS:
        try:
            log(f"🌍 Requesting viewport {lat},{lng} z{zm}")
            response = page.request.post(DATA_URL, headers={
                "accept": "*/*",
                "x-requested-with": "XMLHttpRequest"
            }, data={
                "lat": str(lat),
                "lng": str(lng),
                "zm": str(zm)
            })
            data = response.json()
            if data and data.get("tts"):
                trains.extend(data["tts"])
                log(f"✅ {len(data['tts'])} trains found in viewport")
        except Exception as e:
            log(f"⚠️ Viewport error {lat},{lng}: {e}")
    return trains

# ==== MAIN ====
def main():
    user = sys.argv[1] if len(sys.argv) > 1 else "USERNAME"
    pwd = sys.argv[2] if len(sys.argv) > 2 else "PASSWORD"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        login(page, user, pwd)

        log("🚉 Sweeping AU viewports…")
        trains = fetch_trains(context)
        browser.close()

        if not trains:
            log("⚠️ No trains collected (feed empty).")
        else:
            log(f"✅ Collected {len(trains)} trains total.")

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(trains, f, indent=2)
        log(f"💾 Wrote {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
