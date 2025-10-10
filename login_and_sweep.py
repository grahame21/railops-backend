# login_and_sweep.py
# Auto-login TrainFinder → fetch trains.json
import os, json, time, random, requests
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

BASE = "https://trainfinder.otenko.com"
LOGIN = f"{BASE}/Home/NextLevel"
FETCH = f"{BASE}/Home/GetViewPortData"

USERNAME = os.environ.get("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD", "").strip()

def cookie_header_from_context(context):
    cookies = context.cookies()
    jar = []
    for c in cookies:
        if "otenko.com" in c.get("domain", ""):
            jar.append(f"{c['name']}={c['value']}")
    return "; ".join(jar)

def login_and_get_cookie(play):
    print("🌐 Opening TrainFinder…")
    browser = play.chromium.launch(headless=True, args=["--disable-gpu"])
    ctx = browser.new_context()
    page = ctx.new_page()
    page.set_default_timeout(25000)

    page.goto(LOGIN, wait_until="domcontentloaded")
    time.sleep(2)

    # If login tab must be clicked first
    try:
        page.locator("text=LOGIN, text=Log in, text=Sign in").first.click(timeout=3000)
        print("🔘 Clicking LOGIN tab…")
    except:
        pass

    # Fill credentials
    print("✏️ Filling credentials…")
    try:
        page.locator("input#useR_name").fill(USERNAME)
        page.locator("input#pasS_word").fill(PASSWORD)
    except:
        # fallback to first visible inputs
        page.locator("input[type='text']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)

    print("🚪 Submitting…")
    clicked = False
    for sel in [
        "button:has-text('Log In')",
        "input[type='submit'][value='Log In']",
        "div.button.button-green",
        "text=Log In",
    ]:
        try:
            page.locator(sel).first.click(timeout=5000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        page.keyboard.press("Enter")

    # Wait until either rules or home content shows (successful login)
    try:
        page.wait_for_selector("text=Rules", timeout=10000)
    except TimeoutError:
        pass  # sometimes it goes straight to map

    page.wait_for_timeout(1500)
    page.screenshot(path="debug_after_submit.png", full_page=True)

    cookie_header = cookie_header_from_context(ctx)
    if not cookie_header:
        raise RuntimeError("Could not obtain auth cookie after login")

    Path("cookie.txt").write_text(cookie_header)
    print("✅ Cookie saved to cookie.txt")
    browser.close()
    return cookie_header

def fetch_viewport(cookie_header):
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
    raise RuntimeError(f"Fetch failed {r.status_code}: {r.text[:300]}")

def main():
    if not USERNAME or not PASSWORD:
        raise SystemExit("❌ Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD")

    # Reuse cookie if possible
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
        time.sleep(random.uniform(0.8, 1.8))
        data = fetch_viewport(cookie_header)
        Path("trains.json").write_text(json.dumps(data, indent=2))
        print("✅ TrainFinder fetch successful")

if __name__ == "__main__":
    main()
