# trainfinder_fetch_pw.py
import os, json, sys, time, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

USERNAME = os.environ.get("TRAINFINDER_USERNAME", "")
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD", "")
BASE = "https://trainfinder.otenko.com"

DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)

def save_debug(page, name="debug"):
    try:
        page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
    except Exception:
        pass
    try:
        (DEBUG_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass

def first_present(locators):
    """Return the first locator that exists and is visible, else None."""
    for loc in locators:
        try:
            el = loc.first
            el.wait_for(state="visible", timeout=1200)
            return el
        except Exception:
            continue
    return None

def find_in_all_frames(page, selector_list):
    """Try each selector in every frame; return the first visible match."""
    for frame in [page.main_frame, *page.frames]:
        locators = [frame.locator(sel) for sel in selector_list]
        el = first_present(locators)
        if el: 
            return el
    return None

def run():
    if not USERNAME or not PASSWORD:
        print("❌ Missing TRAINFINDER_USERNAME/PASSWORD env vars", file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width":1280, "height":900})
        page = ctx.new_page()
        try:
            page.goto(BASE, wait_until="load", timeout=60000)

            # Some sessions show the small "LOGIN" tab at top-left; click it if present.
            login_tab = find_in_all_frames(page, [
                "text=LOGIN",                      # exact text node
                "role=button[name=/login/i]",      # ARIA
                "a:has-text('LOGIN')",
            ])
            if login_tab:
                login_tab.click()
                time.sleep(0.5)

            # Wait for the Authentication modal to appear (title text)
            first_present([
                page.locator("text=/Authentication/i"),
                page.locator("text=/Login/i")
            ])

            # Try robust selectors for the two inputs (across frames)
            user_input = find_in_all_frames(page, [
                "input[name='UserName']",
                "input#UserName",
                "input[placeholder='Username']",
                "xpath=//label[normalize-space()='Username']/following::input[1]",
                "xpath=(//input[@type='text' or not(@type)])[1]",
                "role=textbox"
            ])
            if not user_input:
                save_debug(page, "no_username")
                raise RuntimeError("No username/email input found")

            pass_input = find_in_all_frames(page, [
                "input[name='Password']",
                "input#Password",
                "input[placeholder='Password']",
                "xpath=//label[normalize-space()='Password']/following::input[1]",
                "xpath=(//input[@type='password'])[1]"
            ])
            if not pass_input:
                save_debug(page, "no_password")
                raise RuntimeError("No password input found")

            # Fill credentials
            user_input.fill(USERNAME)
            pass_input.fill(PASSWORD)

            # Find and click the "Log In" button
            login_button = find_in_all_frames(page, [
                "button:has-text('Log In')",
                "role=button[name=/log in/i]",
                "input[type='submit']",
                "xpath=//button[contains(.,'Log In') or contains(.,'Login')]",
            ])
            if not login_button:
                save_debug(page, "no_login_button")
                raise RuntimeError("No login button found")

            login_button.click()

            # Wait for the login modal to disappear or for something that only appears after login
            try:
                page.wait_for_timeout(800)  # brief settle
                page.wait_for_selector("text=/Logout|LOGOUT|Profile/i", timeout=8000)
            except PWTimeout:
                # Fallback: consider it logged in if the modal vanished
                pass

            # Call the JSON endpoint (XHR) after auth cookies are set
            fetch_url = f"{BASE}/Home/GetViewPortData"
            # Some installs require POST with X-Requested-With
            res = page.request.post(fetch_url, headers={"x-requested-with":"XMLHttpRequest"})
            if res.status != 200:
                save_debug(page, "after_login")
                raise RuntimeError(f"Fetch failed: {res.status} {res.text()[:200]}")

            data = res.json()
            Path("trains.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
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
