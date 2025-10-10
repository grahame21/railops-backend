#!/usr/bin/env python3
"""
TrainFinder login + collector — fully robust version with JS modal trigger + screenshots.
"""
import os, time, json, random
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://trainfinder.otenko.com"
NEXTLEVEL = f"{BASE}/Home/NextLevel"
OUT = Path(__file__).resolve().parents[1] / "trains.json"

VIEWPORTS = [
    (144.9631, -37.8136, 12),
    (151.2093, -33.8688, 12),
    (153.026, -27.4705, 11),
    (138.6007, -34.9285, 11),
    (115.8605, -31.9505, 11),
    (147.324, -42.8821, 11),
    (149.1287, -35.282, 12),
    (133.7751, -25.2744, 5),
]

PAUSE_AFTER_LOGIN_SEC = 35  # requested delay

def log(msg):
    print(msg, flush=True)

def find_any_input(page):
    """Find visible username/password fields by scanning all inputs."""
    sels = [
        "input#UserName",
        "input[name='UserName']",
        "input[type='email']",
        "input[type='text']",
        "input[placeholder*='User']",
        "input[placeholder*='Email']",
    ]
    for sel in sels:
        try:
            el = page.locator(sel).first
            if el.is_visible():
                return sel
        except Exception:
            pass
    return None

def find_password_input(page):
    sels = [
        "input#Password",
        "input[name='Password']",
        "input[type='password']",
    ]
    for sel in sels:
        try:
            el = page.locator(sel).first
            if el.is_visible():
                return sel
        except Exception:
            pass
    return None

def open_login_modal(page):
    """Trigger the login modal using clicks and JS."""
    log("🪟 Ensuring login modal is open...")
    # Click visible buttons
    try:
        page.click("text=Login", timeout=2000)
    except Exception:
        pass
    # JS fallback
    page.evaluate("""
        () => {
            const el = Array.from(document.querySelectorAll('a,button'))
                .find(e => /login/i.test(e.textContent||''));
            if (el) el.click();
        }
    """)
    time.sleep(1.5)

def login(page, user, pwd):
    log("🌐 Opening NextLevel…")
    page.goto(NEXTLEVEL, wait_until="load", timeout=60000)
    time.sleep(3)

    open_login_modal(page)
    username_sel = find_any_input(page)
    password_sel = find_password_input(page)

    if not username_sel or not password_sel:
        log("⚠️ Login inputs not visible yet, retrying JS modal open...")
        open_login_modal(page)
        username_sel = find_any_input(page)
        password_sel = find_password_input(page)

    if not username_sel or not password_sel:
        screenshot = OUT.parent / "debug_login_failed.png"
        page.screenshot(path=str(screenshot))
        raise RuntimeError(f"Could not find login inputs — saved {screenshot}")

    log("✏️ Filling credentials…")
    page.fill(username_sel, user)
    page.fill(password_sel, pwd)

    log("🚪 Submitting login…")
    try:
        page.click("button:has-text('Login')", timeout=2000)
    except Exception:
        page.keyboard.press("Enter")
    time.sleep(2)

    cookies = page.context.cookies(BASE)
    has_auth = any(c.get("name","").lower().startswith(".aspxauth") for c in cookies)
    if not has_auth:
        screenshot = OUT.parent / "debug_no_cookie.png"
        page.screenshot(path=str(screenshot))
        raise RuntimeError(f"Could not obtain auth cookie — saved {screenshot}")

    log(f"⏳ Sleeping {PAUSE_AFTER_LOGIN_SEC}s to mimic normal use…")
    time.sleep(PAUSE_AFTER_LOGIN_SEC)

def sweep(page, lon, lat, zm):
    log(f"🔍 Viewport {lon},{lat} z{zm}")
    page.goto(f"{NEXTLEVEL}?lat={lat}&lng={lon}&zm={zm}", wait_until="load", timeout=45000)
    page.wait_for_timeout(1000)
    js = """
        async () => {
          const res = await fetch('/Home/GetViewPortData', {
            method: 'POST', headers:{'X-Requested-With':'XMLHttpRequest'}
          });
          const text = await res.text();
          try { return JSON.parse(text); } catch { return text; }
        }
    """
    data = page.evaluate(js)
    if isinstance(data, str):
        log("⚠️ Response not JSON, skipping.")
        return []
    items = []
    for k in ["trains","Trains","markers","Markers","items","Items","features"]:
        if isinstance(data.get(k), list):
            items = data[k]
            break
    return items

def main():
    user = os.getenv("TRAINFINDER_USERNAME","").strip()
    pwd = os.getenv("TRAINFINDER_PASSWORD","").strip()
    if not user or not pwd:
        raise SystemExit("❌ Missing TrainFinder credentials.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        page = browser.new_page()
        login(page, user, pwd)

        log("🚉 Sweeping AU viewports…")
        all_items = []
        for (lon, lat, zm) in VIEWPORTS:
            try:
                rows = sweep(page, lon, lat, zm)
                if rows: all_items.extend(rows)
            except Exception as e:
                log(f"  ! viewport error {lon},{lat}: {e}")
        browser.close()

    OUT.write_text(json.dumps(all_items, indent=2), encoding="utf-8")
    log(f"✅ Wrote {OUT} with {len(all_items)} trains")

if __name__ == "__main__":
    main()
