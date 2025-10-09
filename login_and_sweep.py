#!/usr/bin/env python3
"""
login_and_sweep.py
- Logs into TrainFinder with Playwright using repo secrets (username/password)
- Extracts the auth cookie
- Sweeps Australia in tiles via GetViewPortData
- Writes trains.json (one pass)
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
    fill creds, submit, then return the auth cookie value.
    """
    print("🌐 Opening TrainFinder…")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f"{BASE}/Home/NextLevel", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        # If the login modal isn't open, click the LOGIN item in the top bar.
        try:
            login_btn = page.locator("text=/^\\s*LOGIN\\s*$/i").first
            if login_btn.is_visible():
                print("🔘 Clicking LOGIN tab…")
                login_btn.click(timeout=10000)
                page.wait_for_timeout(600)
        except Exception:
            pass

        print("✏️ Filling credentials…")
        # Try robust selectors for username/password boxes inside the dialog
        auth = page.locator("div:has-text('Authentication')").first
        if not auth or not auth.is_visible():
            auth = page

        # Username
        filled_user = False
        for sel in ["input#UserName", "input[name='UserName']", "input[type='text']"]:
            try:
                auth.locator(sel).first.fill(user, timeout=8000)
                filled_user = True
                break
            except PWTimeout:
                continue
        if not filled_user:
            raise RuntimeError("Username input not found")

        # Password
        filled_pass = False
        for sel in ["input#Password", "input[name='Password']", "input[type='password']"]:
            try:
                auth.locator(sel).first.fill(pwd, timeout=8000)
                pass_locator = auth.locator(sel).first
                filled_pass = True
                break
            except PWTimeout:
                continue
        if not filled_pass:
            raise RuntimeError("Password input not found")

        print("🚪 Submitting…")
        # Submit chain (several fallbacks)
        submitted = False
        submit_selectors = [
            "button:has-text('Log In')",
            "input[type='submit'][value='Log In']",
            "text=/^\\s*Log\\s*In\\s*$/i",
            "button:has-text('Login')",
            "text=/^\\s*Login\\s*$/i",
        ]
        for sel in submit_selectors:
            try:
                page.locator(sel).first.click(timeout=5000)
                submitted = True
                break
            except Exception:
                continue

        if not submitted:
            # Last resort: focus password and press Enter
            try:
                pass_locator.press("Enter", timeout=2000)
                submitted = True
            except Exception:
                pass

        page.wait_for_timeout(1800)

        # Grab auth cookie
        cookies = ctx.cookies()
        token = None
        for c in cookies:
            name = c.get("name", "")
            if name.upper().startswith(".ASPXAUTH") or "AUTH" in name.upper():
                token = c.get("value")
                break

        if not token:
            # Secondary signal: LOGIN button disappears after success
            try:
                still_login = page.locator("text=/^\\s*LOGIN\\s*$/i").first.is_visible()
                if not still_login:
                    if cookies:
                        token = cookies[0].get("value")
            except Exception:
                pass

        if not token:
            # Capture a quick screenshot for debugging (stored in runner workspace)
            try:
                page.screenshot(path="debug_after_submit.png", full_page=True)
                print("⚠️ Saved debug screenshot: debug_after_submit.png")
            except Exception:
                pass
            raise RuntimeError("Could not obtain auth cookie after login")

        print("✅ Logged in & cookie captured")
        browser.close()
        return token

def session_with_cookie(token: str) -> requests.Session:
    s = requests.Session()
    # Most deployments use .ASPXAUTH; set to domain path root.
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
        raise SystemExit("Set TRAINFINDER_USERNAME and TRAINFINDER_PASSWORD repo secrets.")

    token = robust_login_and_get_cookie(user, pwd)
    sess  = session_with_cookie(token)
    sweep_once(sess)

if __name__ == "__main__":
    main()
