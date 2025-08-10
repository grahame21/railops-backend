import os, json, time, sys
from pathlib import Path
from urllib.parse import urlencode
import requests

# ---- Config you can tweak ----
VIEWPORTS = [
    # (lat, lng, zoom) – a few tiles to cover AU; add/remove if you like
    (-25.0, 134.0, 5),
    (-33.9, 151.2, 8),   # Sydney
    (-37.8, 144.9, 8),   # Melbourne
    (-27.5, 153.0, 8),   # Brisbane
    (-34.9, 138.6, 8),   # Adelaide
    (-31.9, 115.9, 8),   # Perth
    (-41.4, 147.1, 8),   # Tasmania
]
OUT_FILE = Path("static/trains.json")
LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
API_URL   = "https://trainfinder.otenko.com/Home/GetViewPortData"

def fetch_cookie_via_creds():
    """Call the login page with username/password already stored in session;
    Site sets auth after an AJAX call; easiest is to reuse an .ASPXAUTH cookie if present.
    If not present, we abort so the action can refresh it with Selenium step."""
    cookie = os.getenv("TF_AUTH_COOKIE", "").strip()
    if not cookie:
        raise RuntimeError("No TF_AUTH_COOKIE found in env for requests step.")
    return cookie

def call_viewport(session, lat, lng, zoom):
    # TrainFinder uses last visited viewport from Referer; we simulate that.
    params = {"lat": lat, "lng": lng, "zm": zoom}
    headers = {
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{LOGIN_URL}?{urlencode(params)}",
    }
    r = session.post(API_URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

def normalise(raw):
    trains = []
    for t in raw:
        try:
            trains.append({
                "id":      t.get("TrainId") or t.get("Id") or t.get("TrainID"),
                "loco":    t.get("Loco") or t.get("Headcode") or t.get("Name"),
                "lat":     t.get("Lat")  or t.get("Latitude"),
                "lng":     t.get("Lng")  or t.get("Longitude"),
                "operator":t.get("Operator"),
                "desc":    t.get("Description") or t.get("Service") or "",
                "updated": int(time.time()),
            })
        except Exception:
            continue
    # de-dupe by id, keep last
    by_id = {}
    for t in trains:
        if t["id"] is None: 
            continue
        by_id[t["id"]] = t
    return list(by_id.values())

def main():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Session with auth cookie provided by prior Selenium step
    cookie_value = fetch_cookie_via_creds()
    s = requests.Session()
    s.cookies.set(".ASPXAUTH", cookie_value, domain="trainfinder.otenko.com", path="/")

    merged = []
    for lat, lng, zm in VIEWPORTS:
        try:
            data = call_viewport(s, lat, lng, zm)
            merged.extend(normalise(data))
            time.sleep(0.5)
        except Exception as e:
            print(f"Viewport fetch failed ({lat},{lng},{zm}): {e}", file=sys.stderr)

    # Write only if changed
    new_json = json.dumps({"trains": merged}, ensure_ascii=False, separators=(",",":"))
    if OUT_FILE.exists() and OUT_FILE.read_text(encoding="utf-8") == new_json:
        print("No change to trains.json")
        return

    OUT_FILE.write_text(new_json, encoding="utf-8")
    print(f"Wrote {OUT_FILE} with {len(merged)} trains")

if __name__ == "__main__":
    main()