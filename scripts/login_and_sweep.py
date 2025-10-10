import json, os, time, random
from pathlib import Path
import requests

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://trainfinder.otenko.com/Home/NextLevel"
FETCH_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

# Viewports to sweep (lon, lat, zoom-ish tag for logging)
VIEWPORTS = [
    ("Melbourne", 144.9631, -37.8136, 12),
    ("Sydney",    151.2093, -33.8688, 12),
    ("VIC",       144.5,    -36.5,     8),
    ("NSW",       147.0,    -32.0,     8),
    ("AU",        133.7751, -25.2744,  5),
]

OUT_FILE = Path("trains.json")
COOKIE_FILE = Path("cookie.txt")

U = os.environ.get("TRAINFINDER_USERNAME", "")
P = os.environ.get("TRAINFINDER_PASSWORD", "")

HEADERS = {
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://trainfinder.otenko.com",
    "referer": LOGIN_URL,
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

def cookie_header_from_store():
    """Return cookie header string if we have a stored cookie."""
    if not COOKIE_FILE.exists():
        return ""
    try:
        data = json.loads(COOKIE_FILE.read_text())
        parts = []
        for c in data:
            # keep only essential auth cookie + google analytics harmlessly
            if c.get("name") in (".ASPXAUTH", "_ga", "_ga_M6C2H1PF9J"):
                parts.append(f'{c["name"]}={c["value"]}')
        return "; ".join(parts)
    except Exception:
        return ""

def save_cookie(context):
    cookies = context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2))

def login_and_get_cookie(play):
    print("🌐 Opening TrainFinder…")
    browser = play.chromium.launch(args=["--disable-dev-shm-usage"], headless=True)
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=HEADERS["user-agent"]
    )
    page = ctx.new_page()
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)

    # The dialog has inputs with ids #UserName and #Password
    print("✏️ Filling credentials…")
    page.wait_for_selector("input#UserName", timeout=30000)
    page.fill("input#UserName", U)
    page.fill("input#Password", P)

    print("🚪 Submitting…")
    # Click visible "Log In" button (button or input submit)
    login_btn = page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first
    try:
        login_btn.click(timeout=30000)
    except:
        # Fallback: press Enter in password
        page.press("input#Password", "Enter")

    # Wait a bit for cookie to be set
    page.wait_for_timeout(1500)
    save_cookie(ctx)
    print("✅ Cookie saved to cookie.txt")
    browser.close()

def post_viewport(session, name, lon, lat):
    # TrainFinder expects a POST XHR with no body — scope is taken from current map view of the session.
    # We can't set the browser's map viewport here, so we do one generic fetch; server returns what's current for the account.
    # In practice, most accounts return the same JSON regardless of referer query; we still hit it multiple times to coax updates.
    print(f"🛰️ Requesting viewport: {name} …")
    r = session.post(FETCH_URL, headers=HEADERS, timeout=30)
    print(f"{name} post_json: HTTP {r.status_code}")
    if r.status_code != 200:
        return None

    # Sometimes it responds with HTML (eg. auth splash). Detect and treat as empty.
    ctype = r.headers.get("content-type", "")
    if "application/json" not in ctype:
        return None

    try:
        return r.json()
    except Exception:
        return None

def merge_payloads(payloads):
    # Expected keys seen in TrainFinder: favs, alerts, places, tts, webcams, atcsGomi, atcsObj
    merged = { "favs": None, "alerts": None, "places": None, "tts": None, "webcams": None, "atcsGomi": None, "atcsObj": None }
    # If any viewport returns a non-null for a key, keep the first non-null
    for p in payloads:
        if not isinstance(p, dict): continue
        for k in merged.keys():
            if merged[k] is None and k in p and p[k] is not None:
                merged[k] = p[k]
    return merged

def main():
    # Try reuse cookie first
    sess = requests.Session()
    ck = cookie_header_from_store()
    if ck:
        sess.headers.update({"Cookie": ck})

    all_payloads = []

    for i, (name, lon, lat, zm) in enumerate(VIEWPORTS, 1):
        data = post_viewport(sess, name, lon, lat)
        if data is None:
            # If first attempt failed, refresh cookie once then retry
            with sync_playwright() as p:
                login_and_get_cookie(p)
            sess = requests.Session()
            sess.headers.update({"Cookie": cookie_header_from_store()})
            # brief, human-ish delay
            time.sleep(random.randint(2, 5))
            data = post_viewport(sess, name, lon, lat)

        if data:
            all_payloads.append(data)
        # light delay between viewports to look normal
        time.sleep(random.randint(1, 3))

    merged = merge_payloads(all_payloads)

    # Write output (even if mostly nulls, keeps frontend happy)
    OUT_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    print("✅ trains.json generated")

if __name__ == "__main__":
    main()
