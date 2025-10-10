#!/usr/bin/env python3
"""
TrainFinder login and collector — FINAL FIXED VERSION
✅ Logs in automatically
✅ Fetches /Home/GetViewPortData via in-page fetch (no bad cookie header)
✅ Writes trains.json with all trains found
"""

import os, json, time, random
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://trainfinder.otenko.com"
LOGIN_URL = f"{BASE}/Home/NextLevel"
DATA_URL = f"{BASE}/Home/GetViewPortData"

OUT = Path(__file__).resolve().parents[1] / "trains.json"

# Major cities + national view
VIEWPORTS = [
    (144.9631, -37.8136, 12),  # Melbourne
    (151.2093, -33.8688, 12),  # Sydney
    (153.026, -27.4705, 11),   # Brisbane
    (138.6007, -34.9285, 11),  # Adelaide
    (115.8605, -31.9505, 11),  # Perth
    (147.324, -42.8821, 11),   # Hobart
    (149.1287, -35.282, 12),   # Canberra
    (133.7751, -25.2744, 5)    # Australia-wide
]

def login(page, username, password):
    print("🌐 Logging in to TrainFinder…")
    page.goto(LOGIN_URL, wait_until="load", timeout=60000)
    page.wait_for_selector("input#UserName", timeout=30000)
    page.fill("input#UserName", username)
    page.fill("input#Password", password)
    page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first.click()
    time.sleep(2)

def sweep(page):
    trains = []
    seen = set()

    print("🚉 Sweeping Australian viewports…")
    for lon, lat, zm in VIEWPORTS:
        try:
            page.goto(f"{LOGIN_URL}?lat={lat}&lng={lon}&zm={zm}", wait_until="load", timeout=45000)
            time.sleep(1.5)
            js = """
            async () => {
                const res = await fetch('/Home/GetViewPortData', {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                return await res.text();
            }
            """
            raw = page.evaluate(js)
            if not raw or raw.startswith("<"):
                print(f"⚠️ Empty/HTML response for {lat},{lon}")
                continue
            data = json.loads(raw)
            items = data.get("trains") or data.get("Trains") or []
            for i, t in enumerate(items):
                if not isinstance(t, dict): continue
                lat_ = t.get("lat") or t.get("Lat") or t.get("latitude")
                lon_ = t.get("lon") or t.get("Lon") or t.get("longitude")
                if not lat_ or not lon_: continue
                uid = str(t.get("id") or t.get("Name") or f"{lat_},{lon_}")
                if uid in seen: continue
                seen.add(uid)
                trains.append({
                    "id": uid,
                    "lat": float(lat_),
                    "lon": float(lon_),
                    "label": t.get("label") or t.get("Loco") or "",
                    "operator": t.get("operator") or t.get("Operator") or "",
                })
            print(f"🛰️ {len(items)} trains at {lat},{lon}")
            time.sleep(random.uniform(1.2, 2.0))
        except Exception as e:
            print(f"❌ viewport {lat},{lon}: {e}")
    return trains

def main():
    username = os.getenv("TRAINFINDER_USERNAME")
    password = os.getenv("TRAINFINDER_PASSWORD")
    if not username or not password:
        raise SystemExit("❌ Missing credentials (GitHub Secrets)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context()
        page = ctx.new_page()
        login(page, username, password)
        trains = sweep(page)
        browser.close()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(trains, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote {OUT} with {len(trains)} trains")
    if not trains:
        print("⚠️ No trains collected (feed returned empty).")

if __name__ == "__main__":
    main()
