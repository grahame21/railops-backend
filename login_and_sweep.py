import os, json, time, random, requests
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

BASE = "https://trainfinder.otenko.com"
LOGIN = f"{BASE}/Home/NextLevel"
FETCH = f"{BASE}/Home/GetViewPortData"

USERNAME = os.environ.get("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD", "").strip()

# ======= viewport for whole-of-Australia =======
VIEWPORT = {
    "n": -10.0,    # north bound latitude
    "s": -44.0,    # south bound latitude
    "e": 154.0,    # east bound longitude
    "w": 112.0,    # west bound longitude
    "zm": 5        # zoom level (5–6 gives national view)
}

def cookie_header_from_context(context):
    cookies = context.cookies()
    return "; ".join([f"{c['name']}={c['value']}" for c in cookies if "otenko.com" in c.get("domain", "")])

def login_and_get_cookie(play):
    print("🌐 Opening TrainFinder…")
    browser = play.chromium.launch(headless=True, args=["--disable-gpu"])
    ctx = browser.new_context()
    page = ctx.new_page()
    page.set_default_timeout(25000)
    page.goto(LOGIN, wait_until="domcontentloaded")

    # click login tab if needed
    try: page.locator("text=LOGIN, text=Log in").first.click(timeout=2000)
    except: pass

    print("✏️ Filling credentials…")
    try:
        page.locator("#useR_name").fill(USERNAME)
        page.locator("#pasS_word").fill(PASSWORD)
    except:
        page.locator("input[type='text']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)

    print("🚪 Submitting…")
    try:
        page.locator("button:has-text('Log In'), input[value='Log In']").first.click(timeout=5000)
    except Exception:
        page.keyboard.press("Enter")

    page.wait_for_timeout(1500)
    cookie = cookie_header_from_context(ctx)
    Path("cookie.txt").write_text(cookie)
    print("✅ Cookie saved to cookie.txt")
    browser.close()
    return cookie

def fetch_viewport(cookie):
    headers = {
        "cookie": cookie,
        "x-requested-with": "XMLHttpRequest",
        "referer": LOGIN,
        "origin": BASE,
        "user-agent": "Mozilla/5.0 (ActionsBot)"
    }
    print("🚉 Requesting viewport data…")
    r = requests.post(FETCH, json=VIEWPORT, headers=headers, timeout=40)
    print(f"HTTP {r.status_code}")
    if r.ok:
        return r.json()
    raise RuntimeError(f"Fetch failed: {r.status_code} {r.text[:200]}")

def main():
    if not USERNAME or not PASSWORD:
        raise SystemExit("❌ Missing credentials")

    cookie = ""
    if Path("cookie.txt").exists():
        cookie = Path("cookie.txt").read_text().strip()
        try:
            data = fetch_viewport(cookie)
            Path("trains.json").write_text(json.dumps(data, indent=2))
            print("✅ TrainFinder fetch successful (existing cookie)")
            return
        except Exception as e:
            print(f"Cookie reuse failed: {e}")

    with sync_playwright() as p:
        cookie = login_and_get_cookie(p)
        time.sleep(random.uniform(1.0, 2.0))
        data = fetch_viewport(cookie)
        Path("trains.json").write_text(json.dumps(data, indent=2))
        print("✅ TrainFinder fetch successful")

if __name__ == "__main__":
    main()
