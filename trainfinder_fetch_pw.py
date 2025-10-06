# trainfinder_fetch_pw.py
import os, sys, json, time, requests
from playwright.sync_api import sync_playwright

BASE = "https://trainfinder.otenko.com"
LOGIN = f"{BASE}/Home/NextLevel"
VIEWPORT = f"{BASE}/Home/GetViewPortData"

U = os.environ.get("TRAINFINDER_USERNAME", "").strip()
P = os.environ.get("TRAINFINDER_PASSWORD", "").strip()
if not U or not P:
    print("❌ Missing TRAINFINDER_USERNAME or TRAINFINDER_PASSWORD")
    sys.exit(1)

def headless_login_and_get_cookie():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        # Go to login page
        page.goto(LOGIN, wait_until="domcontentloaded", timeout=45000)

        # Heuristics: find a username/email field, then password, then submit
        # Try common selectors first
        user_locators = [
            "input[name='UserName']",
            "input[name='Email']",
            "input[type='email']",
            "input[type='text']"
        ]
        pass_locators = [
            "input[name='Password']",
            "input[type='password']"
        ]
        submit_locators = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Log in')",
            "button:has-text('Login')",
            "button:has-text('Sign in')"
        ]

        username_box = None
        for sel in user_locators:
            loc = page.locator(sel)
            if loc.count() > 0:
                username_box = loc.first
                break
        if not username_box:
            raise RuntimeError("No username/email input found on login page")

        password_box = None
        for sel in pass_locators:
            loc = page.locator(sel)
            if loc.count() > 0:
                password_box = loc.first
                break
        if not password_box:
            raise RuntimeError("No password input found on login page")

        username_box.fill(U)
        password_box.fill(P)

        submitted = False
        for sel in submit_locators:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click()
                submitted = True
                break
        if not submitted:
            # fallback: press Enter in password field
            password_box.press("Enter")

        # Wait for navigation or any network to settle
        page.wait_for_timeout(2000)
        # If still on a login-ish URL, give it a bit more time
        for _ in range(5):
            if "login" in page.url.lower():
                page.wait_for_timeout(1000)
            else:
                break

        # Check we got a session cookie
        cookies = ctx.cookies()
        aspx = next((c for c in cookies if c.get("name") == ".ASPXAUTH"), None)
        if not aspx:
            raise RuntimeError("Login appears to have failed (no .ASPXAUTH cookie)")

        cookie_val = aspx["value"]
        ctx.close()
        browser.close()
        return cookie_val

def fetch_viewport_json(aspx_cookie):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": BASE + "/",
        "Accept": "application/json, text/plain, */*"
    })
    # Set the auth cookie
    s.cookies.set(".ASPXAUTH", aspx_cookie, domain="trainfinder.otenko.com", path="/")

    # Try POST first, then GET fallback
    r = s.post(VIEWPORT, timeout=30)
    if not r.ok:
        r = s.get(VIEWPORT, timeout=30)

    try:
        data = r.json()
    except ValueError:
        # Not JSON; include a short preview for debugging
        data = {"status": r.status_code, "preview": r.text[:400]}

    with open("trains.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ trains.json updated")

def main():
    try:
        cookie_val = headless_login_and_get_cookie()
        fetch_viewport_json(cookie_val)
    except Exception as e:
        print("❌ Headless fetch failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
