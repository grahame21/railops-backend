# trainfinder_fetch_pw.py
import os, sys, json, requests
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

        page.goto(LOGIN, wait_until="domcontentloaded", timeout=45000)

        # Try common username & password inputs
        user_sels = ["input[name='UserName']","input[name='Email']","input[type='email']","input[type='text']"]
        pass_sels = ["input[name='Password']","input[type='password']"]
        submit_sels = ["button[type='submit']","input[type='submit']","button:has-text('Log in')","button:has-text('Login')","button:has-text('Sign in')"]

        u = None
        for sel in user_sels:
            if page.locator(sel).count() > 0:
                u = page.locator(sel).first; break
        if not u: raise RuntimeError("No username/email input found")

        pbox = None
        for sel in pass_sels:
            if page.locator(sel).count() > 0:
                pbox = page.locator(sel).first; break
        if not pbox: raise RuntimeError("No password input found")

        u.fill(U); pbox.fill(P)
        clicked = False
        for sel in submit_sels:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click(); clicked = True; break
        if not clicked:
            pbox.press("Enter")

        page.wait_for_timeout(2500)

        cookies = ctx.cookies()
        aspx = next((c for c in cookies if c.get("name") == ".ASPXAUTH"), None)
        if not aspx:
            raise RuntimeError("Login failed (no .ASPXAUTH cookie)")
        val = aspx["value"]
        ctx.close(); browser.close()
        return val

def fetch_viewport_json(aspx_cookie):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": BASE + "/",
        "Accept": "application/json, text/plain, */*"
    })
    s.cookies.set(".ASPXAUTH", aspx_cookie, domain="trainfinder.otenko.com", path="/")

    r = s.post(VIEWPORT, timeout=30)
    if not r.ok:
        r = s.get(VIEWPORT, timeout=30)

    try:
        data = r.json()
    except ValueError:
        data = {"status": r.status_code, "preview": r.text[:400]}

    with open("trains.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ trains.json updated")

def main():
    cookie_val = headless_login_and_get_cookie()
    fetch_viewport_json(cookie_val)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("❌ Headless fetch failed:", e)
        sys.exit(1)
