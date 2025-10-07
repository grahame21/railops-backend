import os
import time
from playwright.sync_api import sync_playwright

def snap(page, name):
    """Take debug screenshots"""
    os.makedirs("debug_artifacts", exist_ok=True)
    page.screenshot(path=f"debug_artifacts/{name}.png")

def run():
    username = os.getenv("TRAINFINDER_USERNAME")
    password = os.getenv("TRAINFINDER_PASSWORD")
    if not username or not password:
        raise Exception("TRAINFINDER_USERNAME and TRAINFINDER_PASSWORD must be set")

    print("🌐 Opening TrainFinder...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # Step 1: open the map page
        page.goto("https://trainfinder.otenko.com/Home/NextLevel", timeout=60000)
        time.sleep(5)
        snap(page, "1_loaded")

        # Step 2: Click the LOGIN button in the top nav
        try:
            print("🔘 Clicking LOGIN tab...")
            btns = page.locator("div.nav_btn", has_text="LOGIN")
            if btns.count() > 0:
                btns.first.click()
                time.sleep(3)
                snap(page, "2_login_clicked")
            else:
                print("⚠️ No LOGIN tab found in topnav.")
        except Exception as e:
            print("⚠️ Could not click LOGIN tab:", e)

        # Step 3: Wait for login form to appear
        try:
            page.wait_for_selector("input#UserName", timeout=15000)
            snap(page, "3_form_ready")
        except Exception:
            print("❌ Login form did not appear!")
            browser.close()
            raise

        # Step 4: Fill credentials
        print("✏️ Filling credentials...")
        page.fill("input#UserName", username)
        page.fill("input#Password", password)
        snap(page, "4_filled")

        # Step 5: Click the Log In button
        print("🚪 Submitting login...")
        page.click("input[value='Log In']")
        time.sleep(6)
        snap(page, "5_after_login")

        # Step 6: Wait for map load and cookie
        page.wait_for_load_state("networkidle", timeout=20000)
        cookies = page.context.cookies()
        aspxauth = None
        for c in cookies:
            if c.get("name") == ".ASPXAUTH":
                aspxauth = c.get("value")
                break

        if not aspxauth:
            raise Exception("❌ No .ASPXAUTH cookie found after login")

        with open("cookie.txt", "w") as f:
            f.write(aspxauth)
        print("✅ Cookie saved to cookie.txt")

        browser.close()

if __name__ == "__main__":
    try:
        run()
        print("✅ TrainFinder fetch successful")
    except Exception as e:
        print("❌ Headless fetch failed:", e)
        exit(1)
