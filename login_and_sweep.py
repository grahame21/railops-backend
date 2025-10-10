#!/usr/bin/env python3
import os, json, time, random
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

BASE = "https://trainfinder.otenko.com"
LOGIN_URL = f"{BASE}/home/nextlevel"
FETCH_URL = f"{BASE}/Home/GetViewPortData"

USERNAME = os.environ.get("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD", "").strip()

HEADERS_TEMPLATE = {
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "origin": BASE,
    "priority": "u=1, i",
    "referer": f"{BASE}/home/nextlevel?lat=-34.7406336&lng=138.5889792&zm=12",
    "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}

def msg(s): print(s, flush=True)

def cookie_header_from_context(ctx):
    cookies = ctx.cookies()
    parts = []
    for c in cookies:
        if "otenko.com" in c.get("domain", ""):
            parts.append(f"{c['name']}={c['value']}")
    return "; ".join(parts)

def playwright_login_and_get_cookie():
    with sync_playwright() as p:
        msg("🌐 Opening TrainFinder login page…")
        browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        try: page.locator("text=LOGIN, text=Log in").first.click(timeout=1500)
        except: pass

        msg("✏️ Filling credentials…")
        try:
            page.locator("#useR_name").fill(USERNAME, timeout=3000)
            page.locator("#pasS_word").fill(PASSWORD, timeout=3000)
        except:
            page.locator("input[type='text']").first.fill(USERNAME)
            page.locator("input[type='password']").first.fill(PASSWORD)

        msg("🚪 Submitting login…")
        try:
            page.locator("button:has-text('Log In'), input[value='Log In']").first.click(timeout=2000)
        except:
            page.keyboard.press("Enter")

        page.wait_for_timeout(2000)
        cookie = cookie_header_from_context(ctx)
        Path("cookie.txt").write_text(cookie)
        msg("✅ Cookie saved")
        browser.close()
        return cookie

def fetch_data(cookie):
    headers = HEADERS_TEMPLATE.copy()
    headers["cookie"] = cookie
    r = requests.post(FETCH_URL, headers=headers, timeout=40)
    msg(f"HTTP {r.status_code}")
    try:
        data = r.json()
    except Exception:
        data = {"_raw": r.text[:500]}
    return data

def looks_empty(data):
    return (
        isinstance(data, dict)
        and all(v is None for v in data.values() if not v)
    )

def main():
    if not USERNAME or not PASSWORD:
        raise SystemExit("❌ Missing TRAINFINDER_USERNAME or TRAINFINDER_PASSWORD")

    # try reuse
    cookie = Path("cookie.txt").read_text().strip() if Path("cookie.txt").exists() else ""
    if not cookie:
        cookie = playwright_login_and_get_cookie()

    while True:
        msg("🚉 Requesting viewport data…")
        data = fetch_data(cookie)
        Path("last_response.json").write_text(json.dumps(data, indent=2))
        Path("trains.json").write_text(json.dumps(data, indent=2))
        if looks_empty(data) or "_raw" in data:
            msg("⚠️ Empty or HTML response — refreshing cookie…")
            cookie = playwright_login_and_get_cookie()
        else:
            msg("✅ TrainFinder fetch successful and saved to trains.json")

        # wait 30–90 s before next sweep
        delay = random.randint(30, 90)
        msg(f"⏳ Sleeping {delay}s to mimic normal use…\n")
        time.sleep(delay)

if __name__ == "__main__":
    main()
