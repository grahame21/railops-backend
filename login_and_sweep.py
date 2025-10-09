#!/usr/bin/env python3
"""
login_and_sweep.py
- Logs into TrainFinder with Playwright using repo secrets (username/password)
- Extracts the auth cookie
- Sweeps Australia in tiles via GetViewPortData
- Writes trains.json (one pass)

GitHub Actions can run this every 5 minutes. For 30–90s continuous updates,
run the sweep variant on a VPS/Raspberry Pi instead.
"""

import os, json, time, random
from math import ceil
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://trainfinder.otenko.com"
OUT_FILE = Path("trains.json")

# AU bounding box (lon/lat)
AUS_W, AUS_N, AUS_E, AUS_S = 112.0, -9.0, 154.0, -44.0

# Tile size (deg). Smaller = more calls but finer coverage.
TILE_DEG = 2.5
DEFAULT_ZOOM = 7

# polite delay between tile calls
TILE_DELAY_MIN = 0.8
TILE_DELAY_MAX = 2.0

HEADERS_BASE = {
    "Accept": "*/*",
    "Accept-Language": "en-GB,en;q=0.8",
    "Origin": BASE,
    "Referer": f"{BASE}/Home/NextLevel",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
}

def robust_login_and_get_cookie(user: str, pwd: str) -> str:
    """
    Use Playwright (Chromium) to load the NextLevel page, click LOGIN tab,
    fill creds, submit, then return the .ASPXAUTH (or equivalent) cookie value.
    """
    print("🌐 Opening TrainFinder…")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f"{BASE}/Home/NextLevel", timeout=60000)

        # If the login modal isn't open, click the LOGIN button in the top bar.
        try:
            # the top-left bar usually contains text 'LOGIN'
            login_btn = page.locator("text=LOGIN").first
            if login_btn.is_visible():
                login_btn.click()
                time.sleep(0.5)
        except Exception:
            pass

        print("✏️ Filling credentials…")
        # Try robust selectors for username/password boxes
        # 1) First text input, then password input inside the auth modal
        auth = page.locator("div:has-text('Authentication')").first
        if not auth.is_visible():
            # fall back to whole page scan
            auth = page

        # Username
        try:
            auth.locator("input[type='text']").first.fill(user, timeout=15000)
        except PWTimeout:
            # some builds may have id=UserName
            auth.locator("input#UserName").fill(user, timeout=5000)

        # Password
        try:
            auth.locator("input[type='password']").first.fill(pwd, timeout=15000)
        except PWTimeout:
            auth.locator("input#Password").fill(pwd, timeout=5000)

        # Click Log In button (text match)
        print("🚪 Submitting…")
        page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first.click()
        # wait for any map activity or cookie to appear
        page.wait_for_timeout(2000)

        # Grab auth cookie
        cookies = ctx.cookies()
        token = None
        # try common cookie names
        for c in cookies:
            name = c.get("name", "")
            if name.upper().startswith(".ASPXAUTH") or "AUTH" in name.upper():
                token = c.get("value")
                break

        if not token:
            # try to detect login by absence of login button
            try:
                if not page.locator("text=LOGIN").first.is_visible():
                    # still accept if no explicit cookie name matched
                    # dump any cookie as last resort
                    if cookies:
                        token = cookies[0].get("value")
            except Exception:
                pass

        if not token:
            raise RuntimeError("Could not obtain auth cookie after login")

        print("✅ Logged in & cookie captured")
        browser.close()
        return token

def session_with_cookie(token: str) -> requests.Session:
    s = requests.Session()
    # most deployments use .ASPXAUTH, but accept any name via header cookie if needed
    s.cookies.set(".ASPXAUTH", token, domain="trainfinder.otenko.com", path="/")
    return s

def tiles(w, n, e, s, step):
    lon_n = ceil((e - w) / step)
    lat_n = ceil((n - s) / step)
    for i in range(lon_n):
        lon0 = w + i * step
        lon1 = min(e, lon0 + step)
        for j in range(lat_n):
            lat1 = n - j * step   # top
            lat0 = max(s, lat1 - step)
            yield (lat1, lon0, lat0, lon1)

def fetch_viewport(session, nwLat, nwLng, seLat, seLng, zm=DEFAULT_ZOOM):
    payload = {
        "nwLat": float(nwLat), "nwLng": float(nwLng),
        "seLat": float(seLat), "seLng": float(seLng),
        "zm": int(zm)
    }
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
            if k not in master or master[k] is None:
                master[k] = []
            seen = { (x.get("id") or x.get("vehicleId") or json.dumps(x, sort_keys=True)): True
                     for x in master[k] }
            for item in v:
                key = item.get("id") or item.get("vehicleId") or json.dumps(item, sort_keys=True)
                if key not in seen:
                    master[k].append(item)
                    seen[key] = True
        elif isinstance(v, dict):
            if k not in master or master[k] is None:
                master[k] = {}
            master[k].update(v)
        else:
            if k not in master or master[k] is None:
                master[k] = v

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
        raise SystemExit("Set TRAINFINDER_USERNAME and TRAINFINDER_PASSWORD env vars / repo secrets.")

    token = robust_login_and_get_cookie(user, pwd)
    sess = session_with_cookie(token)
    sweep_once(sess)

if __name__ == "__main__":
    main()
