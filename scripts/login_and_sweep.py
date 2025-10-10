import json, os, time, random
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://trainfinder.otenko.com/Home/NextLevel"
FETCH_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

# (name, lon, lat, zoomHint) – used only to build a Referer that hints the map center
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
    "origin": LOGIN_URL.rsplit("/", 1)[0],
    "referer": LOGIN_URL,
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

def cookie_header_from_store():
    if not COOKIE_FILE.exists():
        return ""
    try:
        data = json.loads(COOKIE_FILE.read_text())
        parts = []
        for c in data:
            if c.get("name") in (".ASPXAUTH", "_ga", "_ga_M6C2H1PF9J"):
                parts.append(f'{c["name"]}={c["value"]}')
        return "; ".join(parts)
    except Exception:
        return ""

def save_cookie(context):
    cookies = context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2))

def login_and_get_cookie(play):
    print("🌐 Opening TrainFinder login…")
    browser = play.chromium.launch(args=["--disable-dev-shm-usage"], headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, user_agent=HEADERS["user-agent"])
    page = ctx.new_page()
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)

    print("✏️ Filling credentials…")
    page.wait_for_selector("input#UserName", timeout=30000)
    page.fill("input#UserName", U)
    page.fill("input#Password", P)

    print("🚪 Submitting login…")
    login_btn = page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first
    try:
        login_btn.click(timeout=15000)
    except:
        page.press("input#Password", "Enter")

    page.wait_for_timeout(1500)
    save_cookie(ctx)
    print("✅ Cookie saved")
    browser.close()

def post_viewport(session, name, lon, lat, zm=6):
    referer = f"{LOGIN_URL}?zm={zm}&cx={lon}&cy={lat}"
    headers = dict(HEADERS); headers["referer"] = referer
    print(f"🚉 Requesting viewport data for {name} ({lon},{lat}, zm={zm})")
    r = session.post(FETCH_URL, headers=headers, timeout=30)
    print("HTTP", r.status_code)
    ctype = r.headers.get("content-type", "")
    if "application/json" not in ctype:
        print("⚠️ Empty or HTML response")
        return None
    try:
        return r.json()
    except Exception as e:
        print("⚠️ JSON decode failed:", e)
        return None

def merge_payloads(payloads):
    merged = { "favs": None, "alerts": None, "places": None, "tts": None, "webcams": None, "atcsGomi": None, "atcsObj": None }
    for p in payloads:
        if not isinstance(p, dict): continue
        for k in merged.keys():
            if merged[k] is None and k in p and p[k] is not None:
                merged[k] = p[k]
    # Attach generation stamp
    merged["generated_at"] = int(time.time() * 1000)
    return merged

def main():
    sess = requests.Session()
    ck = cookie_header_from_store()
    if ck:
        sess.headers.update({"Cookie": ck})

    all_payloads = []

    for (name, lon, lat, zm) in VIEWPORTS:
        data = post_viewport(sess, name, lon, lat, zm)
        if data is None:
            print("⚠️ Refreshing cookie then retrying…")
            with sync_playwright() as p:
                login_and_get_cookie(p)
            sess = requests.Session()
            sess.headers.update({"Cookie": cookie_header_from_store()})
            time.sleep(random.randint(2, 5))
            data = post_viewport(sess, name, lon, lat, zm)

        if data:
            all_payloads.append(data)
        time.sleep(random.randint(1, 3))

    merged = merge_payloads(all_payloads)
    OUT_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    print("✅ trains.json generated")

if __name__ == "__main__":
    main()
