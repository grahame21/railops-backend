#!/usr/bin/env python3
import os, re, json, time, random
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

BASE   = "https://trainfinder.otenko.com"
LOGIN  = f"{BASE}/Home/NextLevel"
FETCH  = f"{BASE}/Home/GetViewPortData"

USERNAME = os.environ.get("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD", "").strip()

VIEWPORTS = [
    {"name":"Melbourne","n":-37.60,"s":-38.20,"e":145.30,"w":144.40,"zm":12},
    {"name":"Sydney",   "n":-33.70,"s":-34.20,"e":151.30,"w":150.70,"zm":12},
    {"name":"VIC",      "n":-33.8, "s":-39.2, "e":149.0, "w":140.5, "zm":8},
    {"name":"NSW",      "n":-28.0, "s":-37.6, "e":153.8, "w":141.0, "zm":8},
    {"name":"AU",       "n":-10.0, "s":-44.0, "e":154.0, "w":112.0, "zm":5},
]

EMPTY_SIGNATURE = {"favs": None, "alerts": None, "places": None, "tts": None, "webcams": None, "atcsGomi": None, "atcsObj": None}

def msg(s): print(s, flush=True)

def cookie_header_from_context(ctx):
    cookies = ctx.cookies()
    parts = []
    for c in cookies:
        # Only send the TF cookies
        if "otenko.com" in c.get("domain",""):
            parts.append(f"{c['name']}={c['value']}")
    return "; ".join(parts)

def playwright_login_get_cookie_and_token():
    with sync_playwright() as p:
        msg("🌐 Opening TrainFinder…")
        browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_timeout(25000)

        page.goto(LOGIN, wait_until="domcontentloaded")
        # Some UIs need the LOGIN tab click; safe to try
        try: page.locator("text=LOGIN, text=Log in").first.click(timeout=1500)
        except: pass

        msg("✏️ Filling credentials…")
        # try stable ids first (they appear obfuscated sometimes)
        filled = False
        for sel_user in ["#useR_name", "input[name='UserName']", "input[type='text']"]:
            for sel_pw in   ["#pasS_word", "input[name='Password']", "input[type='password']"]:
                try:
                    page.locator(sel_user).first.fill(USERNAME, timeout=2000)
                    page.locator(sel_pw).first.fill(PASSWORD, timeout=2000)
                    filled = True
                    break
                except: continue
            if filled: break
        if not filled:
            raise RuntimeError("Could not find login inputs")

        msg("🚪 Submitting…")
        try:
            page.locator("button:has-text('Log In'), input[value='Log In']").first.click(timeout=2500)
        except:
            page.keyboard.press("Enter")

        # Wait a moment for auth cookies to set and token to appear
        page.wait_for_timeout(2000)

        # Grab antiforgery token from the DOM (ASP.NET renders a hidden input)
        html = page.content()
        # common patterns: name="__RequestVerificationToken" value="..."; or
        # <input type="hidden" id="RequestVerificationToken" value="...">
        m = re.search(r'name=[\'"]__RequestVerificationToken[\'"][^>]*value=[\'"]([^\'"]+)[\'"]', html, re.I) \
            or re.search(r'id=[\'"]RequestVerificationToken[\'"][^>]*value=[\'"]([^\'"]+)[\'"]', html, re.I)
        token = m.group(1) if m else ""

        cookie = cookie_header_from_context(ctx)
        Path("cookie.txt").write_text(cookie)
        if token:
            Path("token.txt").write_text(token)

        browser.close()
        msg("✅ Cookie saved" + (" and token saved" if token else " (no token found)"))
        return cookie, token

def load_cookie_and_token_from_files():
    cookie = Path("cookie.txt").read_text().strip() if Path("cookie.txt").exists() else ""
    token  = Path("token.txt").read_text().strip()  if Path("token.txt").exists()  else ""
    return cookie, token

def looks_empty(data):
    if isinstance(data, dict) and set(EMPTY_SIGNATURE).issubset(data.keys()):
        return all(data[k] is None for k in EMPTY_SIGNATURE)
    if isinstance(data, list) and not data:
        return True
    return False

def do_fetch(session, headers, vp, use_json_first=False):
    payload = {"n":vp["n"], "s":vp["s"], "e":vp["e"], "w":vp["w"], "zm":vp["zm"]}
    def post_json(): return session.post(FETCH, json=payload, headers=headers, timeout=40)
    def post_form(): return session.post(FETCH, data=payload, headers=headers, timeout=40)
    order = (post_json, post_form) if use_json_first else (post_form, post_json)
    for fn in order:
        r = fn()
        msg(f"   • {vp['name']} {fn.__name__}: HTTP {r.status_code}")
        if r.ok:
            try: return r.json()
            except Exception: return {"_raw": r.text}
    return {"_raw": "request failed"}

def fetch_any_view(cookie, token):
    s = requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0 (ActionsBot)"})
    # Build headers for AJAX
    headers = {
        "cookie": cookie,
        "x-requested-with": "XMLHttpRequest",
        "referer": LOGIN,
        "origin": BASE,
    }
    # Anti-forgery header if we have it
    if token:
        headers["RequestVerificationToken"] = token

    for vp in VIEWPORTS:
        msg(f"🚉 Requesting viewport: {vp['name']} (z={vp['zm']}) …")
        data = do_fetch(s, headers, vp, use_json_first=False)
        if not looks_empty(data) and "_raw" not in data:
            return data
        # try other encoding
        data2 = do_fetch(s, headers, vp, use_json_first=True)
        if not looks_empty(data2) and "_raw" not in data2:
            return data2
        msg(f"…empty for {vp['name']}, next")
    # Return last attempt (even if raw) so we can inspect
    return data2 if 'data2' in locals() else data

def main():
    if not USERNAME or not PASSWORD:
        raise SystemExit("❌ Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD")

    # 1) Try reuse
    cookie, token = load_cookie_and_token_from_files()
    if cookie:
        try:
            msg("🔁 Reusing cookie…")
            data = fetch_any_view(cookie, token)
            Path("last_response.json").write_text(json.dumps(data, indent=2))
            Path("trains.json").write_text(json.dumps(data, indent=2))
            msg("✅ TrainFinder fetch (reused cookie)")
            return
        except Exception as e:
            msg(f"Cookie reuse failed, relogging: {e}")

    # 2) Fresh login to get cookie + token
    cookie, token = playwright_login_get_cookie_and_token()
    time.sleep(random.uniform(1.0, 2.0))
    data = fetch_any_view(cookie, token)
    Path("last_response.json").write_text(json.dumps(data, indent=2))
    Path("trains.json").write_text(json.dumps(data, indent=2))
    msg("✅ TrainFinder fetch successful")

if __name__ == "__main__":
    main()
