#!/usr/bin/env python3
"""
TrainFinder login + collector (robust) — with 35s human pause
- Opens NextLevel
- Reliably opens the LOGIN modal (multiple fallbacks)
- Finds username/password via several selectors
- Submits, verifies auth cookie
- Fetches /Home/GetViewPortData from inside the page (so cookies apply)
- Writes trains.json at repo root
"""

import os, json, time, random
from pathlib import Path
from typing import Any, Dict, List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://trainfinder.otenko.com"
NEXTLEVEL = f"{BASE}/Home/NextLevel"
OUT = Path(__file__).resolve().parents[1] / "trains.json"

# Viewports (lon, lat, zoom)
VIEWPORTS = [
    (144.9631, -37.8136, 12),  # Melbourne
    (151.2093, -33.8688, 12),  # Sydney
    (153.0260, -27.4705, 11),  # Brisbane
    (138.6007, -34.9285, 11),  # Adelaide
    (115.8605, -31.9505, 11),  # Perth
    (147.3240, -42.8821, 11),  # Hobart
    (149.1287, -35.2820, 12),  # Canberra
    (133.7751, -25.2744, 5),   # Australia-wide
]

PAUSE_AFTER_LOGIN_SEC = 35  # 👈 your requested human-like delay

def log(msg: str) -> None:
    print(msg, flush=True)

def wait_first_selector(page, selectors, per_timeout=3000, total_timeout=15000):
    """Wait for the first selector that appears; return it or None."""
    start = time.time()
    last_err = None
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=per_timeout, state="visible")
            return sel
        except Exception as e:
            last_err = e
        if (time.time() - start) * 1000 > total_timeout:
            break
    # final wide try with combined
    try:
        page.wait_for_selector(", ".join(selectors), timeout=per_timeout, state="visible")
        return selectors[0]
    except Exception:
        return None

def click_if_visible(page, selectors):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=1500)
                return True
        except Exception:
            pass
    return False

def robust_open_login_modal(page):
    """
    On NextLevel, the login form is often a modal opened by a 'LOGIN' link/tab.
    Try several routes to ensure the inputs appear.
    """
    # If the modal is already open — great.
    if wait_first_selector(page, ["input#UserName", "input#Password",
                                  "input[name='UserName']", "input[name='Password']"]):
        return

    # Try clicking visible LOGIN controls
    click_if_visible(page, [
        "text=LOGIN",
        "text=Login",
        "a[href*='Login']",
        "button:has-text('Login')",
        "button:has-text('Log In')",
        "#loginLink",
        "a[role='button']:has-text('Login')"
    ])
    time.sleep(0.8)

    # If still not visible, trigger modal via JS (some sites bind click handlers)
    if not wait_first_selector(page, ["input#UserName", "input#Password",
                                      "input[name='UserName']", "input[name='Password']"]):
        try:
            page.evaluate("""
                () => {
                  const cands = Array.from(document.querySelectorAll('a,button'));
                  const el = cands.find(e => /login/i.test(e.textContent||''));
                  if (el) el.click();
                }
            """)
        except Exception:
            pass
        time.sleep(0.8)

def login(page, username: str, password: str):
    log("🌐 Opening NextLevel…")
    page.goto(NEXTLEVEL, wait_until="load", timeout=60000)

    robust_open_login_modal(page)

    # Locate inputs (several fallbacks)
    user_sel = wait_first_selector(page, [
        "input#UserName", "input[name='UserName']", "input[name='username']",
        "input[type='email']", "input[placeholder*=User]"
    ], per_timeout=4000, total_timeout=20000)
    pass_sel = wait_first_selector(page, [
        "input#Password", "input[name='Password']", "input[name='password']",
        "input[type='password']"
    ], per_timeout=4000, total_timeout=20000)

    if not user_sel or not pass_sel:
        # one more attempt: click LOGIN again and re-check
        robust_open_login_modal(page)
        user_sel = user_sel or wait_first_selector(page, ["input#UserName","input[name='UserName']"], 3000)
        pass_sel = pass_sel or wait_first_selector(page, ["input#Password","input[name='Password']"], 3000)

    if not user_sel or not pass_sel:
        page.screenshot(path=str(OUT.parent / "debug_no_inputs.png"))
        raise RuntimeError("Could not find login inputs")

    log("✏️ Filling credentials…")
    page.fill(user_sel, username)
    page.fill(pass_sel, password)

    log("🚪 Submitting login…")
    # Try clicking typical submit elements; also press Enter as fallback
    clicked = click_if_visible(page, [
        "button:has-text('Log In')",
        "input[type='submit'][value='Log In']",
        "button:has-text('Login')",
        "input[type='submit'][value='Login']"
    ])
    if not clicked:
        page.keyboard.press("Enter")

    # Let auth settle and UI update
    page.wait_for_timeout(1500)

    # Verify an auth cookie exists
    cookies = page.context.cookies(BASE)
    has_auth = any(c.get("name", "").lower().startswith(".aspxauth") for c in cookies)
    if not has_auth:
        page.screenshot(path=str(OUT.parent / "debug_after_submit.png"))
        raise RuntimeError("Could not obtain auth cookie after login")

    # Human-like pause you requested (single delay, not per-viewport)
    log(f"⏳ Sleeping {PAUSE_AFTER_LOGIN_SEC}s to mimic normal use…")
    time.sleep(PAUSE_AFTER_LOGIN_SEC)

def extract_any(payload: Any) -> List[Dict[str, Any]]:
    if not payload:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ["trains", "Trains", "markers", "Markers", "items", "Items",
                  "results", "Results", "features"]:
            v = payload.get(k)
            if isinstance(v, list):
                return v
        if payload.get("type") == "FeatureCollection" and isinstance(payload.get("features"), list):
            return payload["features"]
        for k in ["data", "payload"]:
            v = payload.get(k)
            if v:
                arr = extract_any(v)
                if arr: return arr
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []

def norm_row(r: Dict[str, Any], i: int) -> Dict[str, Any]:
    def pf(v):
        try: return float(v)
        except Exception: return None
    # GeoJSON
    if r.get("type") == "Feature" and r.get("geometry", {}).get("type") == "Point":
        coords = r.get("geometry", {}).get("coordinates") or []
        lo = pf(coords[0] if len(coords)>0 else None)
        la = pf(coords[1] if len(coords)>1 else None)
        p = r.get("properties") or {}
        return {
            "id": p.get("id") or p.get("ID") or p.get("Name") or f"train_{i}",
            "lon": lo, "lat": la,
            "label": p.get("label") or p.get("Label") or p.get("Title") or p.get("Operator") or "",
            "operator": p.get("operator") or p.get("Operator") or "",
            "heading": pf(p.get("heading") or p.get("bearing") or p.get("course")),
            "speed": pf(p.get("speed") or p.get("velocity")),
        }
    # Generic
    def g(*keys):
        for k in keys:
            if k in r: return r[k]
        return None
    lo = pf(g("lon","Lon","longitude","Longitude","x","X"))
    la = pf(g("lat","Lat","latitude","Latitude","y","Y"))
    return {
        "id": g("id","ID","Id","Name","Unit","locoId","LocoId") or f"train_{i}",
        "lon": lo, "lat": la,
        "label": g("label","Label","title","Title","Service","Operator","operator") or "",
        "operator": g("operator","Operator","company","Company") or "",
        "heading": pf(g("heading","Heading","bearing","Bearing","course","Course")),
        "speed": pf(g("speed","Speed","velocity","Velocity")),
    }

def sweep_viewport(page, lon: float, lat: float, zm: int) -> List[Dict[str, Any]]:
    page.goto(f"{NEXTLEVEL}?lat={lat}&lng={lon}&zm={zm}", wait_until="load", timeout=45000)
    page.wait_for_timeout(700 + random.randint(0, 700))
    # In-page fetch so auth cookies are used automatically
    js = """
      async () => {
        try {
          const res = await fetch('/Home/GetViewPortData', {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
          });
          const text = await res.text();
          try { return { ok: res.ok, status: res.status, kind: 'json', payload: JSON.parse(text) }; }
          catch { return { ok: res.ok, status: res.status, kind: 'text', payload: text.slice(0, 300) }; }
        } catch (e) {
          return { ok: false, status: 0, kind: 'error', payload: String(e) };
        }
      }
    """
    result = page.evaluate(js)
    if not result.get("ok") or result.get("kind") != "json":
        log(f"  ! viewport error at {lon},{lat} z{zm}: {result.get('payload')}")
        return []
    rows = extract_any(result["payload"])
    return [norm_row(r, i) for i, r in enumerate(rows)]

def main():
    user = os.getenv("TRAINFINDER_USERNAME", "").strip()
    pwd  = os.getenv("TRAINFINDER_PASSWORD", "").strip()
    if not user or not pwd:
        raise SystemExit("❌ Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD")

    all_rows: List[Dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()

        log("🌐 Logging in to TrainFinder…")
        login(page, user, pwd)

        log("🚉 Sweeping AU viewports…")
        for (lon, lat, zm) in VIEWPORTS:
            try:
                rows = sweep_viewport(page, lon, lat, zm)
                if rows:
                    all_rows.extend(rows)
                page.wait_for_timeout(800 + random.randint(0, 600))
            except Exception as e:
                log(f"  ! viewport error at {lon},{lat} z{zm}: {e}")

        browser.close()

    # dedupe by id (keep last)
    dedup = {}
    for r in all_rows:
        tid = str(r.get("id") or "")
        if not tid: continue
        dedup[tid] = r

    trains = list(dedup.values())
    OUT.write_text(json.dumps(trains, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ Wrote {OUT} with {len(trains)} trains")
    if not trains:
        log("⚠️ No trains collected (feed returned empty).")

    if OUT.stat().st_size > 0:
        print("✅ trains.json generated")

if __name__ == "__main__":
    main()
