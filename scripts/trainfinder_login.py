#!/usr/bin/env python3
import sys, time, json, re
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://trainfinder.otenko.com"
NEXTLEVEL = f"{BASE}/home/nextlevel"
COOKIE_OUT = Path("cookie.txt")
DEBUG_DIR = Path("debug"); DEBUG_DIR.mkdir(exist_ok=True)

def log(msg): print(msg, flush=True)

def dump(page, name):
    (DEBUG_DIR / f"{name}.html").write_text(page.content())
    page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/trainfinder_login.py <USERNAME> <PASSWORD>")
        sys.exit(2)

    user, pwd = sys.argv[1], sys.argv[2]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        log("🌐 Opening NextLevel…")
        page.goto(NEXTLEVEL, wait_until="load", timeout=60000)
        page.wait_for_timeout(1500)

        # Try to open login modal if present
        try:
            page.locator("div.nav_btn:has-text('Login')").first.click(timeout=3000)
            log("🪟 Login modal opened")
        except Exception:
            log("ℹ️ Login nav_btn not clickable (continuing)")

        # Fields (case-obfuscated ids on site)
        try:
            page.wait_for_selector("input#useR_name", timeout=10000)
            page.wait_for_selector("input#pasS_word", timeout=10000)
            log("🧾 Found username & password inputs")
        except Exception:
            dump(page, "err_no_inputs")
            print("❌ Could not find login inputs (see debug/err_no_inputs.html)", flush=True)
            browser.close()
            sys.exit(1)

        page.fill("input#useR_name", user)
        page.fill("input#pasS_word", pwd)
        log("✏️ Credentials entered")

        # Submit
        try:
            page.locator("div.button.button-green:has-text('Log In')").first.click(timeout=5000)
        except Exception:
            # Fallback to site JS helper if button locator fails
            try:
                page.evaluate("attemptAuthentication && attemptAuthentication()")
            except Exception:
                pass
        log("🚪 Submitted login form")

        # Wait for auth cookie
        ok = False
        for _ in range(15):
            cookies = ctx.cookies(BASE)
            if any(c.get("name","").lower().startswith(".aspxauth") for c in cookies):
                ok = True
                break
            time.sleep(1)

        if not ok:
            dump(page, "debug_no_cookie_after_login")
            print("❌ No auth cookie set (see debug/debug_no_cookie_after_login.*)", flush=True)
            browser.close()
            sys.exit(1)

        # Save cookie to cookie.txt as ".ASPXAUTH=VALUE"
        aspx = [c for c in ctx.cookies(BASE) if c.get("name","").lower().startswith(".aspxauth")]
        value = aspx[0]["value"] if aspx else ""
        COOKIE_OUT.write_text(f".ASPXAUTH={value}\n")
        log(f"💾 Saved cookie to {COOKIE_OUT}")

        browser.close()
        log("✅ Login success")
        return

if __name__ == "__main__":
    main()
