#!/usr/bin/env python3
# login_and_sweep.py  (tolerant cookie capture + AU sweep)

import os, json, time, random
from math import ceil
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://trainfinder.otenko.com"
OUT_FILE = Path("trains.json")

AUS_W, AUS_N, AUS_E, AUS_S = 112.0, -9.0, 154.0, -44.0
TILE_DEG = 2.5
DEFAULT_ZOOM = 7
TILE_DELAY_MIN, TILE_DELAY_MAX = 0.8, 2.0

HEADERS_BASE = {
    "Accept": "*/*",
    "Accept-Language": "en-GB,en;q=0.8",
    "Origin": BASE,
    "Referer": f"{BASE}/Home/NextLevel",
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
}

def _pick_auth_token(cookies_list, doc_cookie_str):
    """
    Try multiple likely cookie names. Fallback to the longest-looking token.
    """
    names_by_priority = [
        ".ASPXAUTH",
        ".AspNet.ApplicationCookie",
        "AUTH",
        "AUTHCOOKIE",
        "TrainFinderAuth",
    ]
    # Try document.cookie first
    for key in names_by_priority:
        key_eq = key + "="
        if key_eq in doc_cookie_str:
            return doc_cookie_str.split(key_eq, 1)[1].split(";", 1)[0]

    # Try Playwright cookies
    for c in cookies_list:
        n = (c.get("name") or "").upper()
        if any(n.startswith(p.upper()) or p.upper() in n for p in names_by_priority):
            return c.get("value")

    # Fallback: choose longest cookie value (often the auth one)
    if cookies_list:
        best = max(cookies_list, key=lambda x: len(str(x.get("value", ""))))
        if best.get("value"):
            return best["value"]

    return None

def robust_login_and_get_cookie(user: str, pwd: str) -> str:
    print("🌐 Opening TrainFinder…")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f"{BASE}/Home/NextLevel", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        # Ensure login modal visible
        try:
            login_btn = page.locator("text=/^\\s*LOGIN\\s*$/i").first
            if login_btn.is_visible():
                print("🔘 Clicking LOGIN tab…")
                login_btn.click(timeout=10000)
                page.wait_for_timeout(700)
        except Exception:
            pass

        print("✏️ Filling credentials…")
        auth = page.locator("div:has-text('Authentication')").first
        if not auth or not auth.is_visible():
            auth = page

        # Username
        for sel in ["input#UserName", "input[name='UserName']", "input[type='text']"]:
            try:
                auth.locator(sel).first.fill(user, timeout=8000)
                break
            except PWTimeout:
                continue
        else:
            raise RuntimeError("Username input not found")

        # Password
        pw_locator = None
        for sel in ["input#Password", "input[name='Password']", "input[type='password']"]:
            try:
                pw_locator = auth.locator(sel).first
                pw_locator.fill(pwd, timeout=8000)
                break
            except PWTimeout:
                continue
        if pw_locator is None:
            raise RuntimeError("Password input not found")

        print("🚪 Submitting…")
        submitted = False
        for sel in [
            "button:has-text('Log In')",
            "input[type='submit'][value='Log In']",
            "text=/^\\s*Log\\s*In\\s*$/i",
            "button:has-text('Login')",
            "text=/^\\s*Login\\s*$/i",
        ]:
            try:
                page.locator(sel).first.click(timeout=5000)
                submitted = True
                break
            except Exception:
                continue
        if not submitted:
            try:
                pw_locator.press("Enter", timeout=2000)
                submitted = True
            except Exception:
                pass

        # After submit, poll for up to ~12s for the cookie to appear
        token = None
        for _ in range(24):
            doc_cookie = page.evaluate("document.cookie") or ""
            cookies = ctx.cookies()
            token = _pick_auth_token(cookies, doc_cookie)
            if token:
                break
            page.wait_for_timeout(500)

        if not token:
            # Save screenshot + HTML snapshot to help debugging
            try:
                page.screenshot(path="debug_after_submit.png", full_page=True)
                Path("debug_after_submit.html").write_text(page.content())
                print("⚠️ Saved debug screenshots (debug_after_submit.png/.html)")
            except Exception:
                pass
            raise RuntimeError("Could not obtain auth cookie after login")

        print("✅ Logged in & cookie captured")
        browser.close()
        return token

def session_with_cookie(token: str) -> requests.Session:
    s = requests.Session()
    s.cookies.set(".ASPXAUTH", token, domain="trainfinder.otenko.com", path="/")
    return s

def tiles(w, n, e, s, step):
    from math import ceil
    lon_n = ceil((e - w) / step)
    lat_n = ceil((n - s) / step)
    for i in range(lon_n):
        lon0 = w + i * step
        lon1 = min(e, lon0 + step)
        for j in range(lat_n):
            lat1 = n - j * step
            lat0 = max(s, lat1 - step)
            yield (lat1, lon0, lat0, lon1)

def fetch_viewport(session, nwLat, nwLng, seLat, seLng, zm=DEFAULT_ZOOM):
    payload = {"nwLat": nwLat, "nwLng": nwLng, "seLat": seLat, "seLng": seLng, "zm": zm}
    r = session.post(f"{BASE}/Home/GetViewPortData", headers=HEADERS_BASE, data=payload, timeout=30)
    if not r.ok:
        return {"error": f"HTTP {r.status_code}", "text": r.text[:300]}
    try:
        return r.json()
    except Exception as e:
        return {"error": f"JSON parse: {e}", "text": r.text[:300]}

def merge(master, part):
    if not isinstance(part, dict):
        return
    for k, v in part.items():
        if v is None: 
            continue
        if isinstance(v, list):
            master.setdefault(k, [])
            seen = { json.dumps(x, sort_keys=True) for x in master[k] }
            for item in v:
                key = json.dumps(item, sort_keys=True)
                if key not in seen:
                    master[k].append(item); seen.add(key)
        elif isinstance(v, dict):
            master.setdefault(k, {}).update(v)
        else:
            master.setdefault(k, v)

def sweep_once(session):
    master = {}
    all_tiles = list(tiles(AUS_W, AUS_N, AUS_E, AUS_S, TILE_DEG))
    print(f"📦 Tiles to request: {len(all_tiles)}")
    for idx, (nwLat, nwLng, seLat, seLng) in enumerate(all_tiles, 1):
        print(f"  • [{idx}/{len(all_tiles)}] {nwLat:.2f},{nwLng:.2f} → {seLat:.2f},{seLng:.2f}")
        part = fetch_viewport(session, nwLat, nwLng, seLat, seLng)
        if isinstance(part, dict) and part.get("error"):
            print("    ↳ tile error:", part["error"])
        else:
            merge(master, part)
        time.sleep(random.uniform(TILE_DELAY_MIN, TILE_DELAY_MAX))
    OUT_FILE.write_text(json.dumps(master, indent=2))
    print(f"💾 Wrote {OUT_FILE} ({OUT_FILE.stat().st_size} bytes)")

def main():
    user = os.environ.get("TRAINFINDER_USERNAME")
    pwd  = os.environ.get("TRAINFINDER_PASSWORD")
    if not user or not pwd:
        raise SystemExit("Set TRAINFINDER_USERNAME and TRAINFINDER_PASSWORD secrets.")
    token = robust_login_and_get_cookie(user, pwd)
    sess  = session_with_cookie(token)
    sweep_once(sess)

if __name__ == "__main__":
    main()
