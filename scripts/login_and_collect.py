# scripts/login_and_collect.py
# TrainFinder → trains.json collector (Playwright, “in-page fetch” so cookies are correct)
import json, os, random, time
from pathlib import Path
from typing import Any, Dict, List

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "trains.json"

BASE = "https://trainfinder.otenko.com"
START_URL = f"{BASE}/Home/NextLevel"

USERNAME = os.getenv("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.getenv("TRAINFINDER_PASSWORD", "").strip()

# A few AU viewports (city + a wide AU sweep). Tweak or add more as you like.
VIEWPORTS = [
    # (lon, lat, zoom)
    (144.9631, -37.8136, 12),  # Melbourne
    (151.2093, -33.8688, 12),  # Sydney
    (153.0260, -27.4705, 11),  # Brisbane
    (138.6007, -34.9285, 11),  # Adelaide
    (115.8605, -31.9505, 11),  # Perth
    (147.3240, -42.8821, 11),  # Hobart
    (149.1287, -35.2820, 12),  # Canberra
    (133.7751, -25.2744, 5),   # Australia (wide)
]

def log(msg: str) -> None:
    print(msg, flush=True)

def extract_any(data: Any) -> List[Dict[str, Any]]:
    """
    Accept whatever the endpoint returns and try to find an array of objects
    that look like trains/markers.
    """
    if not data:
        return []
    if isinstance(data, list):
        return data
    # common container keys
    for k in ["trains", "Trains", "markers", "Markers", "items", "Items", "results", "Results", "features"]:
        v = data.get(k) if isinstance(data, dict) else None
        if isinstance(v, list):
            return v
    # GeoJSON FeatureCollection
    if isinstance(data, dict) and data.get("type") == "FeatureCollection" and isinstance(data.get("features"), list):
        return data["features"]
    # known containers
    if isinstance(data, dict):
        for k in ["data", "payload"]:
            v = data.get(k)
            if isinstance(v, (dict, list)):
                inner = extract_any(v)
                if inner:
                    return inner
        # last resort: first array-of-objects value
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []

def norm_row(r: Dict[str, Any], i: int) -> Dict[str, Any]:
    """Normalise many possible shapes to a minimal common schema."""
    def pf(v):
        try:
            f = float(v)
            return f
        except Exception:
            return None

    # GeoJSON Feature → Point
    if r and r.get("type") == "Feature" and r.get("geometry", {}).get("type") == "Point":
        coords = r.get("geometry", {}).get("coordinates") or []
        lo = pf(coords[0] if len(coords) > 0 else None)
        la = pf(coords[1] if len(coords) > 1 else None)
        p = r.get("properties") or {}
        return {
            "id": p.get("id") or p.get("ID") or p.get("Name") or f"train_{i}",
            "lon": lo, "lat": la,
            "heading": pf(p.get("heading") or p.get("Heading") or p.get("bearing") or p.get("Bearing") or p.get("course") or p.get("Course")),
            "speed": pf(p.get("speed") or p.get("Speed") or p.get("velocity") or p.get("Velocity")),
            "label": p.get("label") or p.get("Label") or p.get("title") or p.get("Title") or p.get("Service") or p.get("Operator") or "",
            "operator": p.get("operator") or p.get("Operator") or p.get("company") or p.get("Company") or "",
            "raw": r,
        }

    def g(*keys):
        for k in keys:
            if k in r:
                return r[k]
        return None

    lo = pf(g("lon", "Lon", "longitude", "Longitude", "x", "X"))
    la = pf(g("lat", "Lat", "latitude", "Latitude", "y", "Y"))
    return {
        "id": g("id", "ID", "Id", "locoId", "LocoId", "Unit", "Name") or f"train_{i}",
        "lon": lo, "lat": la,
        "heading": pf(g("heading", "Heading", "bearing", "Bearing", "course", "Course")),
        "speed": pf(g("speed", "Speed", "velocity", "Velocity")),
        "label": g("label", "Label", "title", "Title", "loco", "Loco", "Service", "ServiceNumber", "Operator", "operator") or "",
        "operator": g("operator", "Operator", "company", "Company") or "",
        "raw": r,
    }

def login(page) -> None:
    """Log into TrainFinder UI (works with the modal form on NextLevel)."""
    log("🌐 Opening TrainFinder login…")
    page.goto(START_URL, wait_until="load")
    # If the modal isn't open yet, click the LOGIN link in top-left
    try:
        page.locator("text=LOGIN").first.click(timeout=3000)
    except PWTimeout:
        pass

    # The inputs in your screenshots are #UserName and #Password
    log("✏️ Filling credentials…")
    page.wait_for_selector("input#UserName", timeout=15000)
    page.fill("input#UserName", USERNAME)
    page.fill("input#Password", PASSWORD)

    log("🚪 Submitting login…")
    # The button can be <button>Log In</button> or <input type=submit value='Log In'>
    page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first.click()
    # Give the app time to set auth and settle
    page.wait_for_timeout(1500)

def sweep_viewport(page, lon: float, lat: float, zm: int) -> List[Dict[str, Any]]:
    """
    Move map to a viewport then call /Home/GetViewPortData *from inside the page*
    so the browser's cookies and headers are used automatically.
    """
    url = f"{START_URL}?lat={lat}&lng={lon}&zm={zm}"
    page.goto(url, wait_until="load")
    # A tiny, human-ish pause
    page.wait_for_timeout(600 + random.randint(0, 600))

    # In-page fetch (no manual Cookie header!)
    js = """
      async () => {
        try {
          const res = await fetch('/Home/GetViewPortData', {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            body: null,
          });
          const text = await res.text();
          try { return { ok: res.ok, status: res.status, kind: 'json', payload: JSON.parse(text) }; }
          catch { return { ok: res.ok, status: res.status, kind: 'text', payload: text.slice(0, 400) }; }
        } catch (e) {
          return { ok: false, status: 0, kind: 'error', payload: String(e) };
        }
      }
    """
    result = page.evaluate(js)
    if not result.get("ok"):
        log(f"  ! viewport error at {lon},{lat} z{zm}: {result.get('payload')}")
        return []

    if result.get("kind") == "text":
        # Sometimes the endpoint can return HTML if auth expired
        log(f"  ! non-JSON response at {lon},{lat} z{zm}: {result.get('payload')!r}")
        return []

    rows = extract_any(result["payload"])
    return [norm_row(r, i) for i, r in enumerate(rows)]

def main() -> None:
    if not USERNAME or not PASSWORD:
        raise SystemExit("Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD")

    all_rows: List[Dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        login(page)

        log("🚉 Sweeping AU viewports…")
        for (lon, lat, zm) in VIEWPORTS:
            try:
                rows = sweep_viewport(page, lon, lat, zm)
                if rows:
                    all_rows.extend(rows)
                # Small randomized delay between requests (looks less botty)
                page.wait_for_timeout(500 + random.randint(0, 400))
            except Exception as e:
                log(f"  ! viewport error at {lon},{lat} z{zm}: {e}")

        browser.close()

    # De-dup trains by id, keep last seen record
    dedup: Dict[str, Dict[str, Any]] = {}
    for r in all_rows:
        tid = str(r.get("id") or "")
        if not tid:
            continue
        dedup[tid] = r

    trains = list(dedup.values())
    out = {
        "generated_at": int(time.time()),
        "trains": trains
    }

    if not trains:
        log("⚠️ No trains collected (feed returned empty).")

    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"✅ Wrote {OUT} with {len(trains)} trains")

    # Make the runner step pass visibly if file exists and is non-empty
    if OUT.stat().st_size > 0:
        print("✅ trains.json generated")

if __name__ == "__main__":
    main()
