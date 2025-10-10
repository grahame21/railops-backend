#!/usr/bin/env python3
"""
login_and_collect.py — Log into TrainFinder, sweep AU viewports,
normalize markers into a flat array, and write trains.json (array).

Requirements (same as before):
  pip install playwright requests_html
  playwright install --with-deps chromium
Environment:
  TRAINFINDER_USERNAME, TRAINFINDER_PASSWORD
"""

import json, os, random, time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent.parent
OUT  = BASE / "trains.json"
COOKIE_TXT = BASE / "cookie.txt"

LOGIN_URL = "https://trainfinder.otenko.com/Home/NextLevel"
VIEW_URL  = "https://trainfinder.otenko.com/Home/GetViewPortData"

# Viewport sweep: (lon, lat, zoom)
SWEEP = [
    (144.9631, -37.8136, 12),   # Melbourne
    (151.2093, -33.8688, 12),   # Sydney
    (153.0260, -27.4705, 11),   # Brisbane
    (138.6007, -34.9285, 11),   # Adelaide
    (115.8605, -31.9505, 11),   # Perth
    (147.3240, -42.8821, 11),   # Hobart
    (149.1287, -35.2820, 12),   # Canberra
    (133.7751, -25.2744, 5),    # AU wide
]

def norm_float(v):
    try:
        if v is None: return None
        return float(v)
    except Exception:
        return None

def first(obj, *keys):
    for k in keys:
        if isinstance(obj, dict) and k in obj:
            return obj[k]
    return None

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def normalize_item(r, i):
    # Accept both raw objects and GeoJSON Feature
    if isinstance(r, dict) and r.get("type") == "Feature" and isinstance(r.get("geometry"), dict):
        g = r["geometry"]
        props = r.get("properties") or {}
        if g.get("type") == "Point" and isinstance(g.get("coordinates"), (list, tuple)) and len(g["coordinates"]) >= 2:
            lo, la = g["coordinates"][:2]
            return {
                "id": first(props, "id","ID","Id","Name","Unit","Service","ServiceNumber") or f"train_{i}",
                "lat": norm_float(la),
                "lon": norm_float(lo),
                "heading": norm_float(first(props,"heading","Heading","bearing","Bearing","course","Course")) or 0.0,
                "speed": norm_float(first(props,"speed","Speed","velocity","Velocity")),
                "label": first(props,"label","Label","title","Title","loco","Loco","Locomotive","Service","ServiceNumber","Operator") or "",
                "operator": first(props,"operator","Operator","company","Company") or "",
                "updatedAt": first(props,"timestamp","Timestamp","updated","Updated","LastSeen","lastSeen") or now_iso(),
            }

    # Plain object with lat/lon
    lat = norm_float(first(r,"lat","Lat","latitude","Latitude","y","Y"))
    lon = norm_float(first(r,"lon","Lon","longitude","Longitude","x","X"))
    if lat is None or lon is None:
        return None

    return {
        "id": first(r,"id","ID","Id","Name","Unit","Service","ServiceNumber","locoId","LocoId","LocomotiveId") or f"train_{i}",
        "lat": lat,
        "lon": lon,
        "heading": norm_float(first(r,"heading","Heading","bearing","Bearing","course","Course")) or 0.0,
        "speed": norm_float(first(r,"speed","Speed","velocity","Velocity")),
        "label": first(r,"label","Label","title","Title","loco","Loco","Locomotive","Service","ServiceNumber","Operator") or "",
        "operator": first(r,"operator","Operator","company","Company") or "",
        "updatedAt": first(r,"timestamp","Timestamp","updated","Updated","LastSeen","lastSeen") or now_iso(),
    }

def extract_any_list(payload):
    """Return the first list of dict-like items we can find."""
    if not payload:
        return []
    if isinstance(payload, list):
        return payload
    # Common wrappers
    for k in ("trains","Trains","markers","Markers","items","Items","results","Results","features","data","payload"):
        v = payload.get(k) if isinstance(payload, dict) else None
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            sub = extract_any_list(v)
            if sub:
                return sub
    # Fallback: scan any list in values
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []

def login_and_get_cookie(p, user, pwd):
    print("🌐 Opening TrainFinder login…")
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(LOGIN_URL, wait_until="load", timeout=60_000)

    # Fill form (selectors observed in your screenshots)
    page.wait_for_selector("input#UserName", timeout=30_000)
    page.fill("input#UserName", user)
    page.fill("input#Password", pwd)
    # Submit (button or input[type=submit])
    page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first.click()

    # Wait for auth cookie to appear
    ctx.wait_for_event("requestfinished", timeout=30_000)
    cookies = ctx.cookies()
    aspx = next((c for c in cookies if c["name"]==".ASPXAUTH"), None)
    if not aspx:
        raise RuntimeError("Login failed: no .ASPXAUTH cookie")
    cookie_str = f".ASPXAUTH={aspx['value']}"
    COOKIE_TXT.write_text(cookie_str)
    print("✅ Cookie saved")
    return browser, ctx, page, cookie_str

def post_viewport(ctx, cookie, lon, lat, zm):
    headers = {
        "x-requested-with": "XMLHttpRequest",
        "origin": "https://trainfinder.otenko.com",
        "referer": f"https://trainfinder.otenko.com/home/nextlevel?lat={lat}&lng={lon}&zm={zm}",
        "cookie": cookie,
    }
    # Use Playwright request context for simplicity
    resp = ctx.request.post(VIEW_URL, headers=headers, data={})
    return resp

def main():
    user = os.getenv("TRAINFINDER_USERNAME")
    pwd  = os.getenv("TRAINFINDER_PASSWORD")
    if not user or not pwd:
        raise SystemExit("Set TRAINFINDER_USERNAME and TRAINFINDER_PASSWORD")

    with sync_playwright() as p:
        # Try cookie reuse
        cookie = COOKIE_TXT.read_text().strip() if COOKIE_TXT.exists() else None
        browser = ctx = page = None
        if not cookie:
            browser, ctx, page, cookie = login_and_get_cookie(p, user, pwd)
            time.sleep(random.randint(40, 70))  # human-ish pause

        collected = []
        seen_ids = set()

        # Ensure we have a context to make requests
        if not ctx:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(extra_http_headers={"cookie": cookie})

        print("🚉 Sweeping AU viewports…")
        for (lo, la, zm) in SWEEP:
            try:
                r = post_viewport(ctx, cookie, lo, la, zm)
                status = r.status
                if status != 200:
                    print(f"  • HTTP {status} at {lo},{la} z{zm}")
                    continue
                # Page sometimes returns JSON; sometimes text that *is* JSON
                try:
                    payload = r.json()
                except Exception:
                    payload = json.loads(r.text())

                items = extract_any_list(payload)
                for i, raw in enumerate(items):
                    n = normalize_item(raw, i)
                    if not n or n["lat"] is None or n["lon"] is None:
                        continue
                    # de-dup by id+coords
                    key = (n["id"], round(n["lat"], 5), round(n["lon"], 5))
                    if key in seen_ids: 
                        continue
                    seen_ids.add(key)
                    collected.append(n)
                # polite delay
                time.sleep(random.uniform(1.0, 2.2))
            except Exception as e:
                print(f"  ! viewport error at {lo},{la} z{zm}: {e}")

        # Write flat array (what the frontend expects)
        if not collected:
            print("⚠️ No trains collected (feed returned empty).")
        OUT.write_text(json.dumps(collected, ensure_ascii=False, indent=2) + "\n")
        print(f"✅ Wrote {OUT} with {len(collected)} trains")

        # Close
        if browser:
            browser.close()

if __name__ == "__main__":
    main()
