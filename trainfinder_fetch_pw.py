import os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

def snap(page, name):
    Path("debug_artifacts").mkdir(exist_ok=True)
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

        page.goto("https://trainfinder.otenko.com/Home/NextLevel", timeout=60000)
        time.sleep(5)
        snap(page, "1_loaded")

        print("🔘 Clicking LOGIN...")
        try:
            page.locator("div.nav_btn", has_text="LOGIN").first.click()
            time.sleep(4)
            snap(page, "2_login_clicked")
        except Exception as e:
            print(f"⚠️ Could not click LOGIN: {e}")

        # --- Wait until form loads ---
        try:
            print("⌛ Waiting for form...")
            page.wait_for_selector("input#UserName", timeout=25000)
            snap(page, "3_form_ready")
        except Exception:
            print("❌ Login form did not appear")
            browser.close()
            raise

        print("✏️ Filling credentials...")
        page.fill("input#UserName", username)
        page.fill("input#Password", password)
        snap(page, "4_filled")

        print("🚪 Clicking Log In...")
        page.click("input[value='Log In']")
        time.sleep(6)
        snap(page, "5_after_login")

        # --- Check for cookie ---
        cookies = page.context.cookies()
        aspxauth = next((c["value"] for c in cookies if c["name"] == ".ASPXAUTH"), None)
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
