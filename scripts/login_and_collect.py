#!/usr/bin/env python3
import json, time, sys, random
from pathlib import Path
import requests

BASE = "https://trainfinder.otenko.com"
DATA_URL = f"{BASE}/Home/GetViewPortData"
COOKIE_FILE = Path("cookie.txt")
OUT = Path("trains.json")
DEBUG_DIR = Path("debug"); DEBUG_DIR.mkdir(exist_ok=True)

# Major cities + a wide AU sweep
VIEWPORTS = [
    (-37.8136, 144.9631, 12),   # Melbourne
    (-33.8688, 151.2093, 12),   # Sydney
    (-27.4705, 153.0260, 11),   # Brisbane
    (-34.9285, 138.6007, 11),   # Adelaide
    (-31.9505, 115.8605, 11),   # Perth
    (-42.8821, 147.3240, 11),   # Hobart
    (-35.2820, 149.1287, 12),   # Canberra
    (-25.2744, 133.7751, 5)     # AU wide
]

def log(m): print(m, flush=True)

def read_cookie_header() -> str:
    if not COOKIE_FILE.exists():
        raise SystemExit("❌ cookie.txt missing. Run trainfinder_login.py first.")
    raw = COOKIE_FILE.read_text().strip()
    # Accept either full "Cookie: ..." or just ".ASPXAUTH=..."
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":",1)[1].strip()
    # Only keep the ASPX cookie pair
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    aspx = next((p for p in parts if p.lower().startswith(".aspxauth=")), None)
    if not aspx:
        raise SystemExit("❌ cookie.txt found but no .ASPXAUTH= value inside.")
    return aspx

def fetch_viewport(session, cookie, lat, lng, zm):
    headers = {
        "accept": "*/*",
        "origin": BASE,
        "referer": f"{BASE}/home/nextlevel?lat={lat}&lng={lng}&zm={zm}",
        "x-requested-with": "XMLHttpRequest",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    }
    resp = session.post(DATA_URL, headers=headers, data={})
    # Some deployments require empty POST body; others may accept lat/lng/zm too.
    # If needed, uncomment:
    # resp = session.post(DATA_URL, headers=headers, data={"lat": str(lat), "lng": str(lng), "zm": str(zm)})

    txt = resp.text
    # Quick guard: JSON or not?
    try:
        data = resp.json()
    except Exception:
        # Save a short debug
        (DEBUG_DIR / "last_non_json.txt").write_text(txt[:2000])
        log(f"⚠️ Non-JSON response ({resp.status_code}). Saved debug/last_non_json.txt")
        return []

    tts = data.get("tts") or []
    return tts

def main():
    log("🚉 Sweeping AU viewports…")
    cookie = read_cookie_header()
    s = requests.Session()

    all_trains = []
    seen_ids = set()

    for lat, lng, zm in VIEWPORTS:
        log(f"🌍 Requesting viewport {lat},{lng} z{zm}")
        try:
            tts = fetch_viewport(s, cookie, lat, lng, zm)
            log(f"✅ {len(tts)} trains found in viewport")
            for t in tts:
                tid = str(t.get("id") or t.get("ID") or t.get("Name") or t.get("Service") or len(all_trains))
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)
                all_trains.append(t)
        except Exception as e:
            log(f"⚠️ Viewport error {lat},{lng}: {e}")
        # Be gentle
        time.sleep(random.uniform(0.5, 1.2))

    if not all_trains:
        log("⚠️ No trains collected (feed returned empty).")
    else:
        log(f"✅ Collected {len(all_trains)} trains total.")

    OUT.write_text(json.dumps(all_trains, indent=2))
    log(f"💾 Wrote {OUT}")

if __name__ == "__main__":
    main()
