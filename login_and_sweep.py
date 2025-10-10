#!/usr/bin/env python3
import os, json, time, random, requests
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE   = "https://trainfinder.otenko.com"
LOGIN  = f"{BASE}/Home/NextLevel"
FETCH  = f"{BASE}/Home/GetViewPortData"

USERNAME = os.environ.get("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD", "").strip()

# Candidate viewports (n, s, e, w, zm)
VIEWPORTS = [
    # City scale first (more likely to return trains)
    {"name":"Melbourne", "n": -37.60, "s": -38.20, "e": 145.30, "w": 144.40, "zm": 12},
    {"name":"Sydney",    "n": -33.70, "s": -34.20, "e": 151.30, "w": 150.70, "zm": 12},
    # State scale
    {"name":"VIC",       "n": -33.8,  "s": -39.2,  "e": 149.0,  "w": 140.5,  "zm": 8},
    {"name":"NSW",       "n": -28.0,  "s": -37.6,  "e": 153.8,  "w": 141.0,  "zm": 8},
    # Fallback whole AU (least likely to return data)
    {"name":"AU",        "n": -10.0,  "s": -44.0,  "e": 154.0,  "w": 112.0,  "zm": 5},
]

EMPTY_SIGNATURE = {"favs": None, "alerts": None, "places": None, "tts": None, "webcams": None, "atcsGomi": None, "atcsObj": None}

def cookie_header_from_context(ctx):
    cookies = ctx.cookies()
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if "otenko.com" in c.get("domain",""))

def playwright_login_and_get_cookie():
    with sync_playwright() as p:
        print("🌐 Opening TrainFinder…")
        browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_timeout(25000)
        page.goto(LOGIN, wait_until="domcontentloaded")

        # Some devices show a “LOGIN” tab; try to click if present
        try: page.locator("text=LOGIN, text=Log in").first.click(timeout=1500)
        except: pass

        print("✏️ Filling credentials…")
        # These ids exist but with odd casing; fall back to first text/password if not found
        try:
            page.locator("#useR_name").fill(USERNAME, timeout=3000)
            page.locator("#pasS_word").fill(PASSWORD, timeout=3000)
        except:
            page.locator("input[type='text']").first.fill(USERNAME)
            page.locator("input[type='password']").first.fill(PASSWORD)

        print("🚪 Submitting…")
        try:
            page.locator("button:has-text('Log In'), input[value='Log In']").first.click(timeout=3000)
        except:
            page.keyboard.press("Enter")

        page.wait_for_timeout(1500)
        ck = cookie_header_from_context(ctx)
        Path("cookie.txt").write_text(ck)
        print("✅ Cookie saved to cookie.txt")
        browser.close()
        return ck

def fetch_with_payload(cookie, vp, as_json_first=False):
    headers = {
        "cookie": cookie,
        "x-requested-with": "XMLHttpRequest",
        "referer": LOGIN,
        "origin": BASE,
        "user-agent": "Mozilla/5.0 (ActionsBot)"
    }
    payload = {"n": vp["n"], "s": vp["s"], "e": vp["e"], "w": vp["w"], "zm": vp["zm"]}

    def do_json():
        r = requests.post(FETCH, json=payload, headers=headers, timeout=40)
        return r

    def do_form():
        r = requests.post(FETCH, data=payload, headers=headers, timeout=40)
        return r

    order = (do_json, do_form) if as_json_first else (do_form, do_json)
    for fn in order:
        r = fn()
        print(f"   • {vp['name']} {fn.__name__}: HTTP {r.status_code}")
        if r.ok:
            try:
                return r.json()
            except Exception:
                return {"_raw": r.text}
    raise RuntimeError(f"Fetch failed for {vp['name']}")

def looks_empty(data):
    # Typical empty structure we’ve been seeing
    if isinstance(data, dict) and set(EMPTY_SIGNATURE.keys()).issubset(set(data.keys())):
        return all(data[k] is None for k in EMPTY_SIGNATURE.keys())
    # If it’s a list with nothing inside
    if isinstance(data, list) and not data:
        return True
    return False

def fetch_any_view(cookie):
    # Try city → state → AU; try form first then json
    for vp in VIEWPORTS:
        print(f"🚉 Requesting viewport: {vp['name']} (z={vp['zm']}) …")
        data = fetch_with_payload(cookie, vp, as_json_first=False)
        if not looks_empty(data):
            print(f"✅ Got non-empty data for {vp['name']}")
            return data
        # Try the other encoding before moving on
        data = fetch_with_payload(cookie, vp, as_json_first=True)
        if not looks_empty(data):
            print(f"✅ Got non-empty data for {vp['name']} (json)")
            return data
        print(f"… empty for {vp['name']}, trying next viewport")
    return data  # whatever the last attempt returned

def main():
    if not USERNAME or not PASSWORD:
        raise SystemExit("❌ Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD")

    cookie = ""
    # Try reusing cookie if present
    if Path("cookie.txt").exists():
        try:
            cookie = Path("cookie.txt").read_text().strip()
            print("🔁 Reusing cookie…")
            data = fetch_any_view(cookie)
            Path("last_response.json").write_text(json.dumps(data, indent=2))
            Path("trains.json").write_text(json.dumps(data, indent=2))
            print("✅ TrainFinder fetch successful (existing cookie)")
            return
        except Exception as e:
            print(f"Cookie reuse failed, relogging: {e}")

    # Fresh login
    cookie = playwright_login_and_get_cookie()
    # small backoff
    time.sleep(random.uniform(1.0, 2.0))
    data = fetch_any_view(cookie)
    Path("last_response.json").write_text(json.dumps(data, indent=2))
    Path("trains.json").write_text(json.dumps(data, indent=2))
    print("✅ TrainFinder fetch successful")

if __name__ == "__main__":
    main()
