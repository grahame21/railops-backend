import os, json, time, random
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://trainfinder.otenko.com"
LOGIN = f"{BASE}/Home/NextLevel"
FETCH = f"{BASE}/Home/GetViewPortData"

USERNAME = os.environ.get("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD", "").strip()

def cookie_header_from_context(context):
    cookies = context.cookies()
    jar = []
    for c in cookies:
        # keep only site cookies
        if "otenko.com" in c.get("domain", ""):
            jar.append(f"{c['name']}={c['value']}")
    return "; ".join(jar)

def login_and_get_cookie(play):
    print("🌐 Opening TrainFinder…")
    browser = play.chromium.launch(headless=True, args=["--disable-gpu"])
    ctx = browser.new_context()
    page = ctx.new_page()
    page.set_default_timeout(20000)

    # Go to login page
    page.goto(LOGIN, wait_until="domcontentloaded")

    # If the login popup isn’t visible, click the LOGIN tab
    try:
        page.locator("text=LOGIN").first.click(timeout=2000)
    except:
        pass  # already open

    # Fill username/password – pick the first visible text/password inputs
    print("✏️ Filling credentials…")
    page.locator("input[type='text']").nth(0).fill(USERNAME)
    page.locator("input[type='password']").nth(0).fill(PASSWORD)

    print("🚪 Submitting…")
    # Click “Log In” button inside the dialog
    # Accept either <button> or <input type=submit value='Log In'>
    login_btn = page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first
    login_btn.click()
    # wait a moment for cookies to be set
    page.wait_for_timeout(1500)

    cookie_header = cookie_header_from_context(ctx)
    if not cookie_header:
        # Try a small wait + reload once
        page.wait_for_timeout(1500)
        cookie_header = cookie_header_from_context(ctx)

    if not cookie_header:
        # Save a debug screenshot to help diagnose (visible in Actions logs as base64 if needed)
        page.screenshot(path="debug_after_submit.png", full_page=True)
        browser.close()
        raise RuntimeError("Could not obtain auth cookie after login")

    # persist cookie locally (optional)
    Path("cookie.txt").write_text(cookie_header)
    print("✅ Cookie saved to cookie.txt")
    browser.close()
    return cookie_header

def fetch_viewport(cookie_header):
    # The site accepts an XHR POST without payload for current viewport data.
    headers = {
        "cookie": cookie_header,
        "x-requested-with": "XMLHttpRequest",
        "referer": LOGIN,
        "origin": BASE,
        "user-agent": "Mozilla/5.0 (ActionsBot)"
    }
    r = requests.post(FETCH, headers=headers, timeout=30)
    if r.ok:
        return r.json()
    else:
        raise RuntimeError(f"Fetch failed: {r.status_code} {r.text[:200]}")

def main():
    if not USERNAME or not PASSWORD:
        raise SystemExit("Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD secrets.")

    # Try login → fetch. If cookie already exists, try it first to be gentle.
    cookie_header = ""
    if Path("cookie.txt").exists():
        cookie_header = Path("cookie.txt").read_text().strip()
        try:
            data = fetch_viewport(cookie_header)
            Path("trains.json").write_text(json.dumps(data, indent=2))
            print("✅ TrainFinder fetch successful (existing cookie)")
            return
        except Exception as e:
            print(f"Cookie reuse failed, relogging: {e}")

    with sync_playwright() as p:
        cookie_header = login_and_get_cookie(p)
        # wait a short random time before fetching (be polite)
        time.sleep(random.uniform(0.8, 1.8))
        data = fetch_viewport(cookie_header)
        Path("trains.json").write_text(json.dumps(data, indent=2))
        print("✅ TrainFinder fetch successful")

if __name__ == "__main__":
    main()
