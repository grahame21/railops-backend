#!/usr/bin/env python3
"""
TrainFinder login + collector — robust + ALWAYS write debug artifacts.
- Saves debug PNG/HTML to ./debug/
- Uses wide selectors and JS to open the modal
- 35s post-login pause per your ask
"""
import os, time, json, random
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://trainfinder.otenko.com"
NEXTLEVEL = f"{BASE}/Home/NextLevel"

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "trains.json"
DEBUG_DIR = ROOT / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

VIEWPORTS = [
    (144.9631, -37.8136, 12),  # Melbourne
    (151.2093, -33.8688, 12),  # Sydney
    (153.0260, -27.4705, 11),  # Brisbane
    (138.6007, -34.9285, 11),  # Adelaide
    (115.8605, -31.9505, 11),  # Perth
    (147.3240, -42.8821, 11),  # Hobart
    (149.1287, -35.2820, 12),  # Canberra
    (133.7751, -25.2744, 5),   # AU-wide
]

PAUSE_AFTER_LOGIN_SEC = 35

def log(msg: str): print(msg, flush=True)

def dump_debug(page, stem: str):
    """Always try to save a PNG and HTML snapshot."""
    png = DEBUG_DIR / f"{stem}.png"
    html = DEBUG_DIR / f"{stem}.html"
    try:
        page.screenshot(path=str(png), full_page=True)
        log(f"🖼  Saved {png}")
    except Exception as e:
        log(f"🖼  Screenshot failed: {e}")
    try:
        html.write_text(page.content(), encoding="utf-8")
        log(f"📝 Saved {html}")
    except Exception as e:
        log(f"📝 HTML dump failed: {e}")

def click_login_candidates(page):
    # Try a bunch of possibilities to show the modal
    cands = [
        "text=LOGIN", "text=Login", "button:has-text('Login')", "button:has-text('Log In')",
        "input[type='submit'][value='Login']", "input[type='submit'][value='Log In']",
        "#loginLink", "a[href*='Login']",
    ]
    for sel in cands:
        try:
            loc = page.locator(sel).first
            if loc and loc.is_visible():
                loc.click(timeout=1500)
                return True
        except Exception:
            pass
    # JS fallback: click the first element whose text contains "login"
    try:
        page.evaluate("""
            () => {
              const el = Array.from(document.querySelectorAll('a,button,input[type=submit]'))
                .find(e => /login/i.test((e.value||e.textContent||"").trim()));
              if (el) el.click();
            }
        """)
        return True
    except Exception:
        return False

def find_user_input(page):
    sels = ["input#UserName","input[name='UserName']","input[type='email']",
            "input[type='text']","input[placeholder*='User' i]","input[placeholder*='Email' i]"]
    for sel in sels:
        try:
            el = page.locator(sel).first
            if el and el.is_visible(): return sel
        except Exception: pass
    return None

def find_pass_input(page):
    sels = ["input#Password","input[name='Password']","input[type='password']"]
    for sel in sels:
        try:
            el = page.locator(sel).first
            if el and el.is_visible(): return sel
        except Exception: pass
    return None

def login(page, user: str, pwd: str):
    log("🌐 Opening NextLevel…")
    page.goto(NEXTLEVEL, wait_until="load", timeout=60000)
    time.sleep(2)
    # open modal repeatedly
    for _ in range(3):
        if find_user_input(page) and find_pass_input(page):
            break
        click_login_candidates(page)
        time.sleep(1.2)

    u_sel = find_user_input(page)
    p_sel = find_pass_input(page)
    if not u_sel or not p_sel:
        dump_debug(page, "debug_login_inputs_missing")
        raise SystemExit("❌ Could not find login inputs (see debug/debug_login_inputs_missing.*)")

    log("✏️ Filling credentials…")
    page.fill(u_sel, user)
    page.fill(p_sel, pwd)

    log("🚪 Submitting login…")
    if not click_login_candidates(page):
        page.keyboard.press("Enter")
    page.wait_for_timeout(1500)

    cookies = page.context.cookies(BASE)
    has_auth = any(c.get("name","").lower().startswith(".aspxauth") for c in cookies)
    if not has_auth:
        dump_debug(page, "debug_no_cookie_after_login")
        raise SystemExit("❌ Could not obtain auth cookie (see debug/debug_no_cookie_after_login.*)")

    log(f"⏳ Sleeping {PAUSE_AFTER_LOGIN_SEC}s to mimic normal use…")
    time.sleep(PAUSE_AFTER_LOGIN_SEC)

def sweep_viewport(page, lon: float, lat: float, zm: int):
    page.goto(f"{NEXTLEVEL}?lat={lat}&lng={lon}&zm={zm}", wait_until="load", timeout=45000)
    page.wait_for_timeout(800 + random.randint(0, 600))
    # in-page fetch so cookies are applied automatically
    js = """
      async () => {
        try {
          const res = await fetch('/Home/GetViewPortData', {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
          });
          const text = await res.text();
          try { return {ok: res.ok, status: res.status, kind:'json', payload: JSON.parse(text)}; }
          catch(e) { return {ok: res.ok, status: res.status, kind:'text', payload: text.slice(0,300)}; }
        } catch (e) {
          return {ok:false, status:0, kind:'error', payload: String(e)};
        }
      }
    """
    result = page.evaluate(js)
    if not result.get("ok") or result.get("kind") != "json":
        log(f"  ! viewport {lon},{lat} z{zm}: {result.get('payload')}")
        return []

    data = result["payload"]
    # loosened extraction
    for k in ["trains","Trains","markers","Markers","items","Items","features","Results","results"]:
        if isinstance(data.get(k), list):
            return data[k]
    # last resort: first list value
    for v in data.values():
        if isinstance(v, list): return v
    return []

def main():
    user = os.getenv("TRAINFINDER_USERNAME","").strip()
    pwd  = os.getenv("TRAINFINDER_PASSWORD","").strip()
    if not user or not pwd:
        raise SystemExit("❌ Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD.")

    from playwright.sync_api import Error as PWError
    all_items = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        try:
            log("🌐 Logging in to TrainFinder…")
            login(page, user, pwd)
        except SystemExit as e:
            # login already dumped debug
            browser.close()
            raise

        log("🚉 Sweeping AU viewports…")
        for (lon, lat, zm) in VIEWPORTS:
            try:
                rows = sweep_viewport(page, lon, lat, zm)
                if rows: all_items.extend(rows)
            except PWError as e:
                log(f"  ! viewport error {lon},{lat} z{zm}: {e}")
        dump_debug(page, "debug_last_viewport")
        browser.close()

    OUT_JSON.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ Wrote {OUT_JSON} with {len(all_items)} trains")
    if not all_items:
        log("⚠️ No trains collected (feed returned empty).")

if __name__ == "__main__":
    main()
