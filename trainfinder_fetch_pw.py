# trainfinder_fetch_pw.py — robust + always-save debug artifacts
import os, json, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

USERNAME = os.getenv("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.getenv("TRAINFINDER_PASSWORD", "").strip()

LOGIN_URL   = "https://trainfinder.otenko.com/Home/NextLevel"
VIEWPORT_URL= "https://trainfinder.otenko.com/Home/GetViewPortData"
OUT_JSON    = Path("trains.json")
DBG_DIR     = Path("debug_artifacts")

def snap(page, name):
    DBG_DIR.mkdir(exist_ok=True)
    try:
        page.screenshot(path=str(DBG_DIR / f"{name}.png"), full_page=True)
    except Exception as e:
        Path(DBG_DIR / f"{name}.txt").write_text(f"Screenshot failed: {e}")

def dump_html(page, name):
    try:
        DBG_DIR.mkdir(exist_ok=True)
        (DBG_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
    except Exception as e:
        (DBG_DIR / f"{name}.txt").write_text(f"HTML dump failed: {e}")

def main():
    if not USERNAME or not PASSWORD:
        print("❌ Missing TRAINFINDER_USERNAME/PASSWORD env vars"); sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)  # set to False to watch it
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()

        # capture console for troubleshooting
        page.on("console", lambda msg: Path(DBG_DIR/"console.log").write_text(
            (Path(DBG_DIR/"console.log").read_text() if (DBG_DIR/"console.log").exists() else "") + msg.text() + "\n",
            encoding="utf-8"))

        try:
            print("🌐 Opening login…")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
            time.sleep(4)              # modal animation
            snap(page, "1_loaded"); dump_html(page, "1_loaded")

            # Try several selectors for username/password + submit
            user_sels = ["input#UserName","input[name='UserName']","input[placeholder*='User']"]
            pass_sels = ["input#Password","input[name='Password']","input[type='password']"]
            submit_sels = ["input[type='submit']","button:has-text('Log In')","button:has-text('Login')"]

            user_sel = next((s for s in user_sels if page.locator(s).first.count() or page.locator(s).is_visible()), None)
            if not user_sel:
                page.wait_for_selector(user_sels[0], timeout=20000)
                user_sel = user_sels[0]

            # Fill
            page.fill(user_sel, USERNAME, timeout=15000)
            for ps in pass_sels:
                if page.locator(ps).first.count():
                    page.fill(ps, PASSWORD, timeout=15000)
                    break
            snap(page, "2_filled")

            # Submit
            clicked = False
            for ss in submit_sels:
                if page.locator(ss).first.count():
                    page.click(ss, timeout=15000)
                    clicked = True
                    break
            if not clicked:
                # fallback: press Enter in password box
                page.keyboard.press("Enter")

            print("🔑 Submitted; waiting for navigation/network idle…")
            with page.expect_load_state("networkidle", timeout=30000):
                pass
            snap(page, "3_after_login"); dump_html(page, "3_after_login")

            # Try detecting post-login UI (but proceed regardless)
            try:
                page.wait_for_selector("text=/logout/i", timeout=8000)
                print("✅ Logged in (logout visible)")
            except TimeoutError:
                print("⚠️ Logout not visible; attempting API anyway")

            print("📡 Fetching trains…")
            # Prefer POST, fallback GET
            resp = page.request.post(VIEWPORT_URL, headers={"x-requested-with":"XMLHttpRequest"})
            if resp.status != 200:
                resp = page.request.get(VIEWPORT_URL, headers={"x-requested-with":"XMLHttpRequest"})
            OUT_JSON.write_text(json.dumps(resp.json(), indent=2), encoding="utf-8")
            print("✅ trains.json updated")

        except Exception as e:
            print(f"❌ Headless fetch failed: {e}")
            snap(page, "error"); dump_html(page, "error")
            sys.exit(1)
        finally:
            ctx.close(); browser.close()

if __name__ == "__main__":
    main()
