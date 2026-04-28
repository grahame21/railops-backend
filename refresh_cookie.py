import os
import sys
import time
import json
import pickle
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"

COOKIE_TXT = "cookie.txt"
COOKIE_JSON = "trainfinder_cookies.json"
COOKIE_PKL = "trainfinder_cookies.pkl"

DEBUG_DIR = Path("debug_trainfinder")
DEBUG_DIR.mkdir(exist_ok=True)


def log(msg):
    print(msg, flush=True)


def save_debug(driver, name):
    try:
        html_path = DEBUG_DIR / f"{name}.html"
        png_path = DEBUG_DIR / f"{name}.png"

        html_path.write_text(driver.page_source, encoding="utf-8", errors="ignore")
        driver.save_screenshot(str(png_path))

        log(f"🧪 Saved debug HTML: {html_path}")
        log(f"🧪 Saved debug screenshot: {png_path}")
    except Exception as e:
        log(f"⚠️ Could not save debug files: {e}")


def build_driver():
    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1000")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def find_input(driver, possible_selectors):
    for by, selector in possible_selectors:
        try:
            elements = driver.find_elements(by, selector)
            for el in elements:
                if el.is_displayed() and el.is_enabled():
                    return el
        except Exception:
            pass
    return None


def main():
    username = os.environ.get("TF_USERNAME", "").strip()
    password = os.environ.get("TF_PASSWORD", "").strip()

    if not username:
        raise RuntimeError("Missing GitHub Secret: TF_USERNAME")

    if not password:
        raise RuntimeError("Missing GitHub Secret: TF_PASSWORD")

    driver = build_driver()

    try:
        log("🌐 Opening TrainFinder login page...")
        driver.get(LOGIN_URL)
        time.sleep(5)
        save_debug(driver, "01_login_page")

        log(f"📍 Current URL: {driver.current_url}")
        log(f"📄 Page title: {driver.title}")

        email_input = find_input(driver, [
            (By.ID, "useR_name"),
            (By.NAME, "useR_name"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[name*='user' i]"),
            (By.CSS_SELECTOR, "input[id*='user' i]"),
            (By.CSS_SELECTOR, "input[name*='email' i]"),
            (By.CSS_SELECTOR, "input[id*='email' i]"),
            (By.CSS_SELECTOR, "input[type='text']"),
        ])

        password_input = find_input(driver, [
            (By.ID, "pasS_word"),
            (By.NAME, "pasS_word"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.CSS_SELECTOR, "input[name*='pass' i]"),
            (By.CSS_SELECTOR, "input[id*='pass' i]"),
        ])

        if not email_input:
            save_debug(driver, "02_no_email_input")
            raise RuntimeError("Could not find TrainFinder username/email input")

        if not password_input:
            save_debug(driver, "03_no_password_input")
            raise RuntimeError("Could not find TrainFinder password input")

        log("✍️ Entering login details...")
        email_input.clear()
        email_input.send_keys(username)

        password_input.clear()
        password_input.send_keys(password)

        save_debug(driver, "04_filled_login")

        submit_button = find_input(driver, [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (By.CSS_SELECTOR, "button"),
            (By.CSS_SELECTOR, "input[value*='Login' i]"),
            (By.CSS_SELECTOR, "input[value*='Sign' i]"),
        ])

        if not submit_button:
            save_debug(driver, "05_no_submit_button")
            raise RuntimeError("Could not find TrainFinder login button")

        log("🔐 Clicking login button...")
        submit_button.click()

        time.sleep(8)
        save_debug(driver, "06_after_login_click")

        log(f"📍 After-login URL: {driver.current_url}")
        log(f"📄 After-login title: {driver.title}")

        page_text = driver.page_source.lower()

        if "an error occurred while processing your request" in page_text:
            raise RuntimeError("TrainFinder returned ASP.NET error page after login")

        if "could not establish trainfinder session" in page_text:
            raise RuntimeError("TrainFinder session error appeared in page")

        if "login" in driver.current_url.lower() and ".aspxauth" not in str(driver.get_cookies()).lower():
            log("⚠️ Still appears to be on login page after submit")

        cookies = driver.get_cookies()

        log("🍪 Cookies returned by browser:")
        for cookie in cookies:
            safe_value = cookie.get("value", "")
            if len(safe_value) > 12:
                safe_value = safe_value[:6] + "..." + safe_value[-6:]
            log(f" - {cookie.get('name')} = {safe_value}")

        auth_cookie = None
        for cookie in cookies:
            if cookie.get("name", "").lower() == ".aspxauth":
                auth_cookie = cookie
                break

        if not auth_cookie:
            save_debug(driver, "07_no_aspxauth_cookie")
            raise RuntimeError("could not establish TrainFinder session - no .ASPXAUTH cookie found")

        cookie_value = auth_cookie["value"].strip()

        if not cookie_value:
            raise RuntimeError("Found .ASPXAUTH cookie but value was empty")

        Path(COOKIE_TXT).write_text(cookie_value, encoding="utf-8")

        with open(COOKIE_JSON, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        with open(COOKIE_PKL, "wb") as f:
            pickle.dump(cookies, f)

        log("✅ TrainFinder session established")
        log(f"✅ Saved {COOKIE_TXT}")
        log(f"✅ Saved {COOKIE_JSON}")
        log(f"✅ Saved {COOKIE_PKL}")

    except Exception as e:
        log(f"❌ Refresh failed: {e}")
        save_debug(driver, "99_failure")
        raise

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
