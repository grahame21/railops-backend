import os, sys, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

USERNAME = os.getenv("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.getenv("TRAINFINDER_PASSWORD", "").strip()

LOGIN_URL    = "https://trainfinder.otenko.com/Home/NextLevel"
VIEWPORT_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

OUT_JSON = Path("trains.json")
DBG_DIR  = Path("debug_artifacts")
DBG_DIR.mkdir(exist_ok=True)

def snap(page, name):
    """Always dump a screenshot + HTML for debugging."""
    try:
        page.screenshot(path=str(DBG_DIR / f"{name}.png"), full_page=True)
    except Exception:
        pass
    try:
        (DBG_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass

def main():
    if not USERNAME or not PASSWORD:
        print("❌ Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD")
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1366, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
            locale="en-AU",
            timezone_id="Australia/Adelaide",
        )
        page = ctx.new_page()

        try:
            print("🌐 Opening NextLevel…")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
            time.sleep(3)  # let modal animate in
            snap(page, "1_loaded")

            # If a small LOGIN tab exists, click it to open the modal.
            for sel in ["text=LOGIN", "a:has-text('LOGIN')", "button:has-text('LOGIN')", "role=button[name=/login/i]"]:
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        loc.click(timeout=1500)
                        time.sleep(0.5)
                        break
                except Exception:
                    pass

            # Try multiple selectors for the two fields.
            user_sels = [
                "input#UserName",
                "input[name='UserName']",
                "input[placeholder*='User' i]",
                "xpath=//label[normalize-space()='Username']/following::input[1]"
            ]
            pass_sels = [
                "input#Password",
                "input[name='Password']",
                "input[type='password']",
                "xpath=//label[normalize-space()='Password']/following::input[1]"
            ]
            submit_sels = [
                "input[type='submit'][value='Log In']",
                "input[type='submit']",
                "button:has-text('Log In')",
                "button:has-text('Login')"
            ]

            # Find username field (wait on the best-known selector, then fallbacks).
            username_sel = None
            try:
                page.wait_for_selector("input#UserName", timeout=20000)
                username_sel = "input#UserName"
            except TimeoutError:
                for s in user_sels:
                    try:
                        if page.locator(s).first.count():
                            username_sel = s; break
                    except Exception:
                        pass
            if not username_sel:
                snap(page, "error_no_username")
                raise TimeoutError("No username field found")

            # Fill username (fallback to JS fill if needed).
            try:
                page.fill(username_sel, USERNAME, timeout=15000)
            except Exception:
                page.evaluate("""(sel,val)=>{const el=document.querySelector(sel); if(el){el.value=val; el.dispatchEvent(new Event('input',{bubbles:true}))}}""",
                              username_sel, USERNAME)

            # Find password field.
            password_sel = None
            for s in pass_sels:
                try:
                    if page.locator(s).first.count():
                        password_sel = s; break
                except Exception:
                    pass
            if not password_sel:
                snap(page, "error_no_password")
                raise TimeoutError("No password field found")

            # Fill password.
            try:
                page.fill(password_sel, PASSWORD, timeout=15000)
            except Exception:
                page.evaluate("""(sel,val)=>{const el=document.querySelector(sel); if(el){el.value=val; el.dispatchEvent(new Event('input',{bubbles:true}))}}""",
                              password_sel, PASSWORD)

            snap(page, "2_filled")

            # Click a submit control; otherwise press Enter.
            clicked = False
            for s in submit_sels:
                try:
                    loc = page.locator(s).first
                    if loc.count():
                        loc.click(timeout=15000)
                        clicked = True
                        break
                except Exception:
                    pass
            if not clicked:
                page.keyboard.press("Enter")

            print("🔑 Submitted; waiting for network idle…")
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except TimeoutError:
                pass

            snap(page, "3_after_login")

            # Optional: confirm by checking for LOGOUT, but continue regardless.
            try:
                page.wait_for_selector("text=/LOGOUT|Logout/i", timeout=8000)
                print("✅ Login confirmed (LOGOUT visible)")
            except TimeoutError:
                print("⚠️ Couldn’t confirm login visually; attempting API anyway")

            print("📡 Fetching trains…")
            # Prefer POST (site uses AJAX POST), fallback to GET.
            resp = page.request.post(VIEWPORT_URL, headers={"x-requested-with":"XMLHttpRequest"})
            if resp.status != 200:
                print(f"↻ POST {resp.status}; trying GET")
                resp = page.request.get(VIEWPORT_URL, headers={"x-requested-with":"XMLHttpRequest"})

            # Save JSON or minimal error payload.
            try:
                data = resp.json()
            except Exception:
                data = {"status": resp.status, "preview": resp.text()[:400]}
            OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print("✅ trains.json updated")

        except Exception as e:
            print(f"❌ Headless fetch failed: {e}")
            snap(page, "error")
            sys.exit(1)
        finally:
            ctx.close()
            browser.close()

if __name__ == "__main__":
    main()
