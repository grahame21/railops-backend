# trainfinder_fetch_pw.py
import os, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

DBG = Path("debug_artifacts"); DBG.mkdir(exist_ok=True)
def snap(page, name): 
    page.screenshot(path=str(DBG/f"{name}.png"), full_page=True)

def dump(page, name):
    (DBG/f"{name}.html").write_text(page.content())

def find_login_inputs(page):
    """Return (frame_or_page, user_sel, pass_sel) if found, else (None,None,None)."""
    selectors = [
        ("input#UserName", "input#Password"),
        ("input[name='UserName']", "input[name='Password']"),
        ("input[placeholder='Username']", "input[placeholder='Password']"),
        ("input[type='text']", "input[type='password']"),
    ]
    # check main page first
    for u,pw in selectors:
        if page.locator(u).count() and page.locator(pw).count():
            return page, u, pw
    # then any iframe
    for f in page.frames:
        for u,pw in selectors:
            if f.locator(u).count() and f.locator(pw).count():
                return f, u, pw
    return None, None, None

def click_login_tab(page):
    # several ways to hit the “LOGIN” tab/button
    candidates = [
        "div.nav_btn:has-text('LOGIN')",
        "text=LOGIN",
        ".nav_btn >> text=LOGIN",
        "//div[contains(@class,'nav_btn')][contains(.,'LOGIN')]",
    ]
    for sel in candidates:
        try:
            page.locator(sel).first.click()
            return True
        except Exception:
            pass
    # last resort: JS click the first visible nav_btn containing LOGIN
    try:
        page.evaluate("""
            () => {
              const xs = Array.from(document.querySelectorAll('.nav_btn')).filter(x=>/login/i.test(x.textContent));
              if (xs[0]) xs[0].dispatchEvent(new MouseEvent('click', {bubbles:true}));
            }
        """)
        return True
    except Exception:
        return False

def main():
    user = os.getenv("TRAINFINDER_USERNAME")
    pwd  = os.getenv("TRAINFINDER_PASSWORD")
    if not user or not pwd:
        print("❌ Set TRAINFINDER_USERNAME and TRAINFINDER_PASSWORD"); sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        print("🌐 Opening TrainFinder…")
        page.goto("https://trainfinder.otenko.com/Home/NextLevel", timeout=60000)
        # give the OL map time to finish starting up; the modal doesn’t mount instantly
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        time.sleep(4)
        snap(page, "1_loaded"); dump(page, "1_loaded")

        # if the form is already there, skip clicking
        frame, u_sel, p_sel = find_login_inputs(page)
        if not frame:
            print("🔘 Clicking LOGIN…")
            click_login_tab(page)
            # wait a bit and try again, with retries
            for i in range(6):
                time.sleep(3)
                frame, u_sel, p_sel = find_login_inputs(page)
                if frame:
                    break
                # try clicking again (the first click sometimes focuses but doesn’t open)
                click_login_tab(page)
            snap(page, "2_after_click"); dump(page, "2_after_click")

        if not frame:
            snap(page, "error_no_form"); dump(page, "error_no_form")
            raise PwTimeout("Login form did not appear after multiple attempts.")

        print("✏️ Filling credentials…")
        frame.fill(u_sel, user)
        frame.fill(p_sel, pwd)
        snap(page, "3_filled")

        print("🚪 Submitting…")
        # green “Log In” button inside the modal
        # try several options
        clicked = False
        for sel in ["input[value='Log In']", "text=Log In", "//input[@value='Log In']"]:
            try:
                frame.locator(sel).first.click()
                clicked = True; break
            except Exception:
                pass
        if not clicked:
            # press Enter in password box
            frame.locator(p_sel).press("Enter")
        time.sleep(6)
        snap(page, "4_after_login"); dump(page, "4_after_login")

        # success = cookie appears
        cookies = page.context.cookies()
        aspx = next((c["value"] for c in cookies if c["name"] == ".ASPXAUTH"), None)
        if not aspx:
            raise Exception("No .ASPXAUTH cookie found after login")

        Path("cookie.txt").write_text(aspx)
        print("✅ Cookie saved to cookie.txt")

        browser.close()

if __name__ == "__main__":
    try:
        main()
        print("✅ TrainFinder fetch successful")
    except Exception as e:
        print("❌ Headless fetch failed:", e)
        # still exit 1 so Actions marks the job as failed, but you’ll have PNG/HTML to inspect
        sys.exit(1)
