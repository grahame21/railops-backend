#!/usr/bin/env python3
"""
login_and_collect.py — TrainFinder backend collector
Logs in with Playwright, sweeps multiple AU viewports,
and writes a flat JSON array of trains to trains.json.

Fully compatible with frontend dashboard.js / trains.js
"""

import json, os, random, time
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

# --- Paths ---
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "trains.json"
COOKIE_TXT = BASE / "cookie.txt"

LOGIN_URL = "https://trainfinder.otenko.com/Home/NextLevel"
VIEW_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

# --- Viewports across Australia ---
SWEEP = [
    (144.9631, -37.8136, 12),  # Melbourne
    (151.2093, -33.8688, 12),  # Sydney
    (153.0260, -27.4705, 11),  # Brisbane
    (138.6007, -34.9285, 11),  # Adelaide
    (115.8605, -31.9505, 11),  # Perth
    (147.3240, -42.8821, 11),  # Hobart
    (149.1287, -35.2820, 12),  # Canberra
    (133.7751, -25.2744, 5),   # AU-wide
]

# --- Helpers ---
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def pf(v):
    try:
        return float(v)
    except Exception:
        return None

def first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return None

def normalize(r, i):
    if isinstance(r, dict) and r.get("type") == "Feature":
        g = r.get("geometry", {})
        p = r.get("properties", {})
        if g.get("type") == "Point" and isinstance(g.get("coordinates"), list):
            lo, la = g["coordinates"][:2]
            return {
                "id": first(p, "id","ID","Name","Unit","Service","ServiceNumber") or f"train_{i}",
                "lat": pf(la),
                "lon": pf(lo),
                "heading": pf(first(p, "heading","Heading","bearing")) or 0,
                "speed": pf(first(p, "speed","Speed","velocity")),
                "label": first(p, "label","Label","loco","Loco","Service") or "",
                "operator": first(p, "operator","Operator","company","Company") or "",
                "updatedAt": first(p, "updated","Updated","Timestamp") or now_iso()
            }
    lat = pf(first(r,"lat","Lat","latitude"))
    lon = pf(first(r,"lon","Lon","longitude"))
    if lat is None or lon is None:
        return None
    return {
        "id": first(r, "id","ID","Name","Service") or f"train_{i}",
        "lat": lat,
        "lon": lon,
        "heading": pf(first(r, "heading","Heading","bearing")) or 0,
        "speed": pf(first(r, "speed","Speed","velocity")),
        "label": first(r, "label","Label","loco","Loco","Service") or "",
        "operator": first(r, "operator","Operator","company") or "",
        "updatedAt": first(r, "updated","Updated","Timestamp") or now_iso()
    }

def extract(payload):
    if not payload:
        return []
    if isinstance(payload, list):
        return payload
    for k in ["trains","Trains","markers","Markers","items","Items","results","Results","features","data","payload"]:
        v = payload.get(k) if isinstance(payload, dict) else None
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            sub = extract(v)
            if sub:
                return sub
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []

# --- Main ---
def main():
    user = os.getenv("TRAINFINDER_USERNAME")
    pwd = os.getenv("TRAINFINDER_PASSWORD")
    if not user or not pwd:
        raise SystemExit("❌ Missing credentials: set TRAINFINDER_USERNAME and TRAINFINDER_PASSWORD")

    with sync_playwright() as p:
        print("🌐 Logging into TrainFinder...")
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context()
        page = ctx.new_page()

        page.goto(LOGIN_URL, wait_until="load", timeout=60_000)
        page.wait_for_selector("input#UserName", timeout=30_000)
        page.fill("input#UserName", user)
        page.fill("input#Password", pwd)
        page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first.click()

        ctx.wait_for_event("requestfinished", timeout=30_000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        if ".ASPXAUTH" not in cookies:
            raise RuntimeError("Login failed: .ASPXAUTH cookie not found")
        print("✅ Login OK, sweeping viewports...")

        collected, seen = [], set()

        for lo, la, zm in SWEEP:
            try:
                ref_url = f"{LOGIN_URL}?lat={la}&lng={lo}&zm={zm}"
                page.goto(ref_url, wait_until="load", timeout=45_000)
                time.sleep(1.2)

                headers = {
                    "x-requested-with": "XMLHttpRequest",
                    "origin": "https://trainfinder.otenko.com",
                    "referer": ref_url
                }

                res = ctx.request.post(VIEW_URL, headers=headers, data={})
                if res.status != 200:
                    print(f"⚠️ HTTP {res.status} at {lo},{la}")
                    continue

                text = res.text().strip()
                if text.startswith("<") or text.startswith("[\"cookie\"]"):
                    print(f"⚠️ HTML or cookie reply at {lo},{la}")
                    continue

                data = res.json()
                arr = extract(data)
                for i, raw in enumerate(arr):
                    n = normalize(raw, i)
                    if not n or n["lat"] is None or n["lon"] is None:
                        continue
                    key = (n["id"], round(n["lat"], 5), round(n["lon"], 5))
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(n)
                print(f"🛰️ {len(arr)} objects from {lo},{la}")
                time.sleep(random.uniform(1.0, 2.0))
            except Exception as e:
                print(f"❌ viewport {lo},{la} z{zm}: {e}")

        OUT.write_text(json.dumps(collected, ensure_ascii=False, indent=2))
        print(f"✅ Wrote {OUT} with {len(collected)} trains")

        browser.close()

if __name__ == "__main__":
    main()
