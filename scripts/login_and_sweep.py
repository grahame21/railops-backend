import json, os, time, random
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://trainfinder.otenko.com/Home/NextLevel"
FETCH_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

VIEWPORTS = [
    ("Melbourne", 144.9631, -37.8136, 12),
    ("Sydney", 151.2093, -33.8688, 12),
    ("VIC", 144.5, -36.5, 8),
    ("NSW", 147.0, -32.0, 8),
    ("AU", 133.7751, -25.2744, 5),
]

OUT_FILE = Path("trains.json")
COOKIE_FILE = Path("cookie.txt")
DBG_DIR = Path("debug"); DBG_DIR.mkdir(exist_ok=True)

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

def wait_for_login_form(page, timeout=30000):
    try:
        tab = page.locator("a:has-text('LOGIN'), a:has-text('Log In'), button:has-text('LOGIN'), button:has-text('Log In')")
        if tab.count() > 0:
            tab.first.click(timeout=3000)
            page.wait_for_timeout(500)
    except Exception:
        pass

    selectors = [
        "input#UserName", "input#Username", "input[name='UserName']", "input[name='Username']",
        "input[type='email']", "input[type='text']",
    ]
    pw_selectors = ["input#Password", "input[name='Password']", "input[type='password']"]

    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=timeout)
            for psel in pw_selectors:
                if page.locator(psel).count() > 0:
                    return sel, psel
        except Exception:
            continue

    try:
        pw = page.locator("input[type='password']").first
        pw.wait_for(state="visible", timeout=timeout//2)
        user = page.locator("input[type='text'], input[type='email']").first
        user.wait_for(state="visible", timeout=timeout//2)
        return ("input[type='text'], input[type='email']", "input[type='password']")
    except Exception:
        return (None, None)

def login_and_get_cookie(play):
    print("🌐 Opening TrainFinder login…")
    browser = play.chromium.launch(args=["--disable-dev-shm-usage"], headless=True)
    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, user_agent=HEADERS["user-agent"])
    page = ctx.new_page()
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)

    print("✏️ Locating login form…")
    u_sel, p_sel = wait_for_login_form(page, timeout=35000)
    if not u_sel or not p_sel:
        print("⚠️ Login inputs not found — saving screenshot")
        page.screenshot(path=str(DBG_DIR / "login_no_inputs.png"), full_page=True)
        (DBG_DIR / "login_no_inputs.html").write_text(page.content())
        browser.close()
        raise RuntimeError("Login form not found")

    print("✏️ Filling credentials…")
    page.fill(u_sel, U)
    page.fill(p_sel, P)

    print("🚪 Submitting login…")
    try:
        page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first.click(timeout=8000)
    except Exception:
        page.press(p_sel, "Enter")

    page.wait_for_timeout(1500)
    page.screenshot(path=str(DBG_DIR / "after_submit.png"), full_page=True)
    save_cookie(ctx)
    print("✅ Cookie saved")
    browser.close()

def post_viewport(session, name, lon, lat, zm=6):
    referer = f"{LOGIN_URL}?zm={zm}&cx={lon}&cy={lat}"
    headers = dict(HEADERS); headers["referer"] = referer
    print(f"🚉 Requesting viewport data for {name} ({lon},{lat}, zm={zm})")
    r = session.post(FETCH_URL, headers=headers, timeout=30)
    print("HTTP", r.status_code)
    if "application/json" not in r.headers.get("content-type", ""):
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
