# trainfinder_fetch_pw.py
# Logs in at /Home/NextLevel, then fetches /Home/GetViewPortData -> trains.json

import os, json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://trainfinder.otenko.com"
NEXTLEVEL = f"{BASE}/Home/NextLevel"         # <- your requested login page
VIEWPORT  = f"{BASE}/Home/GetViewPortData"

USERNAME = os.getenv("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.getenv("TRAINFINDER_PASSWORD", "").strip()
if not USERNAME or not PASSWORD:
    print("❌ Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD")
    sys.exit(1)

DEBUG_DIR = Path("debug"); DEBUG_DIR.mkdir(exist_ok=True)

def save_debug(page, tag):
    try:
        page.screenshot(path=str(DEBUG_DIR / f"{tag}.png"), full_page=True)
    except Exception:
        pass
    try:
        (DEBUG_DIR / f"{tag}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass

def first_visible(frame, selectors, timeout=1500):
    """Return first visible element in this frame for any selector."""
    for sel in selectors:
        try:
            el = frame.locator(sel).first
            el.wait_for(state="visible", timeout=timeout)
            return el
        except Exception:
            continue
    return None

def find_in_all_frames(page, selectors, timeout=1500):
    """Search main frame + all child frames."""
    # Try main frame first
    el = first_visible(page.main_frame, selectors, timeout)
    if el: return el
    # Then all other frames
    for fr in page.frames:
        el = first_visible(fr, selectors, timeout)
        if el: return el
    return None

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        try:
            # 1) Land directly on NextLevel (map page with LOGIN tab)
            page.goto(NEXTLEVEL, wait_until="domcontentloaded", timeout=60000)

            # Best-effort close cookie/consent banners
            for txt in ("Accept", "Agree", "OK"):
                try:
                    page.get_by_role("button", name=txt, exact=False).first.click(timeout=1000)
                except Exception:
                    pass

            # 2) Open LOGIN panel (small blue tab at top-left)
            login_triggers = [
                "text=LOGIN",
                "a:has-text('LOGIN')",
                "role=button[name=/login/i]",
                "button:has-text('LOGIN')",
            ]
            trigger = find_in_all_frames(page, login_triggers, timeout=2000)
            if not trigger:
                save_debug(page, "no_login_trigger")
                raise RuntimeError("Could not find LOGIN trigger on NextLevel")
            trigger.click()
            page.wait_for_timeout(400)  # brief animation

            # 3) Locate username/password inputs inside the Authentication modal
            username_selectors = [
                "input[name='UserName']",
                "input#UserName",
                "input[placeholder*='User' i]",
                "xpath=//label[normalize-space()='Username']/following::input[1]",
                "xpath=(//input[@type='text' or @type='email' or not(@type)])[1]",
                "role=textbox",
            ]
            password_selectors = [
                "input[name='Password']",
                "input#Password",
                "input[type='password']",
                "input[placeholder*='Pass' i]",
                "xpath=//label[normalize-space()='Password']/following::input[1]",
            ]

            ubox = find_in_all_frames(page, username_selectors, timeout=2500)
            if not ubox:
                save_debug(page, "no_username_input")
                raise RuntimeError("No username/email input found in modal")

            pbox = find_in_all_frames(page, password_selectors, timeout=2500)
            if not pbox:
                save_debug(page, "no_password_input")
                raise RuntimeError("No password input found in modal")

            ubox.fill(USERNAME)
            pbox.fill(PASSWORD)

            # 4) Click Log In
            login_buttons = [
                "button:has-text('Log In')",
                "button:has-text('Login')",
                "role=button[name=/log ?in/i]",
                "input[type='submit']",
                "xpath=//button[contains(.,'Log In') or contains(.,'Login')]",
            ]
            btn = find_in_all_frames(page, login_buttons, timeout=2000)
            if not btn:
                save_debug(page, "no_login_button")
                raise RuntimeError("No Log In button found")
            btn.click()

            # 5) Wait for login to complete (modal disappears or logout appears)
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except PWTimeout:
                pass

            # Quick heuristic: modal gone OR logout appears
            logged_in = False
            try:
                if page.get_by_text("LOGOUT", exact=False).count() > 0:
                    logged_in = True
            except Exception:
                pass

            if not logged_in:
                # As a functional check, try hitting the JSON endpoint via page context
                res = page.evaluate(
                    """async (url) => {
                        const r = await fetch(url, {method:'POST',headers:{'x-requested-with':'XMLHttpRequest'}});
                        return {ok:r.ok, status:r.status};
                    }""",
                    VIEWPORT
                )
                if res.get("ok"):
                    logged_in = True

            if not logged_in:
                save_debug(page, "login_not_verified")
                raise RuntimeError("Could not verify login (modal/LOGOUT not detected)")

            print("✅ Logged in")

            # 6) Fetch the data (POST first, fallback GET)
            def fetch_json(method):
                if method == "POST":
                    r = page.request.post(VIEWPORT, headers={"x-requested-with":"XMLHttpRequest"})
                else:
                    r = page.request.get(VIEWPORT, headers={"x-requested-with":"XMLHttpRequest"})
                return r

            r = fetch_json("POST")
            if r.status != 200:
                r = fetch_json("GET")

            if r.status != 200:
                save_debug(page, "fetch_failed")
                raise RuntimeError(f"GetViewPortData failed: HTTP {r.status} {r.text()[:200]}")

            data = {}
            try:
                data = r.json()
            except Exception:
                data = {"status": r.status, "preview": r.text()[:400]}

            Path("trains.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print("✅ trains.json updated")

        except Exception as e:
            print(f"❌ Headless fetch failed: {e}", file=sys.stderr)
            save_debug(page, "fatal")
            raise
        finally:
            ctx.close()
            browser.close()

if __name__ == "__main__":
    run()
