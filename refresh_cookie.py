import os
import time
import json
import pickle
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


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

        log(f"Saved debug HTML: {html_path}")
        log(f"Saved debug screenshot: {png_path}")
    except Exception as e:
        log(f"Could not save debug files: {e}")


def build_driver():
    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1000")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def wait_for_element(driver, by, value, timeout=30):
    end = time.time() + timeout

    while time.time() < end:
        try:
            element = driver.find_element(by, value)
            if element.is_displayed():
                return element
        except Exception:
            pass

        time.sleep(0.5)

    return None


def wait_for_auth_cookie(driver, timeout=45):
    end = time.time() + timeout

    while time.time() < end:
        cookies = driver.get_cookies()

        for cookie in cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "").strip()

            if name.lower() == ".aspxauth" and value:
                return cookie

        time.sleep(1)

    return None


def close_trainfinder_popup(driver):
    """
    Closes the TrainFinder rules / obligation popup after login.
    """
    log("Checking for TrainFinder popup...")

    possible_selectors = [
        ".jsPanel-btn-close",
        ".jsPanel-hdr-r .jsPanel-btn-close",
        ".jsPanel-headerbar .jsPanel-btn-close",
        "button.jsPanel-btn-close",
        ".jsPanel-btn.jsPanel-btn-close",
    ]

    for selector in possible_selectors:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, selector)

            for button in buttons:
                if button.is_displayed():
                    driver.execute_script("arguments[0].click();", button)
                    log(f"Closed popup using selector: {selector}")
                    time.sleep(2)
                    return True
        except Exception:
            pass

    # Fallback: click the large white X in the top-right of the popup.
    try:
        driver.execute_script("""
            const buttons = Array.from(document.querySelectorAll('*'));
            const closeBtn = buttons.find(el => {
                const txt = (el.innerText || el.textContent || '').trim();
                return txt === '×' || txt === 'X' || txt === 'x';
            });
            if (closeBtn) closeBtn.click();
        """)
        time.sleep(2)
        log("Tried closing popup using text fallback.")
        return True
    except Exception as e:
        log(f"No popup close fallback worked: {e}")

    log("No popup close button found. Continuing anyway.")
    return False


def save_cookie_files(driver, auth_cookie):
    cookies = driver.get_cookies()

    cookie_value = auth_cookie["value"].strip()

    Path(COOKIE_TXT).write_text(cookie_value, encoding="utf-8")

    with open(COOKIE_JSON, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)

    with open(COOKIE_PKL, "wb") as f:
        pickle.dump(cookies, f)

    log(f"Saved {COOKIE_TXT}")
    log(f"Saved {COOKIE_JSON}")
    log(f"Saved {COOKIE_PKL}")


def main():
    username = os.environ.get("TF_USERNAME", "").strip()
    password = os.environ.get("TF_PASSWORD", "").strip()

    if not username:
        raise RuntimeError("Missing GitHub Secret: TF_USERNAME")

    if not password:
        raise RuntimeError("Missing GitHub Secret: TF_PASSWORD")

    driver = build_driver()

    try:
        log("Opening TrainFinder login page...")
        driver.get(LOGIN_URL)
        time.sleep(5)
        save_debug(driver, "01_login_page")

        log(f"Current URL: {driver.current_url}")
        log(f"Page title: {driver.title}")

        username_input = wait_for_element(driver, By.ID, "useR_name", timeout=30)
        password_input = wait_for_element(driver, By.ID, "pasS_word", timeout=30)

        if not username_input:
            save_debug(driver, "02_no_username_input")
            raise RuntimeError("Could not find TrainFinder username input: #useR_name")

        if not password_input:
            save_debug(driver, "03_no_password_input")
            raise RuntimeError("Could not find TrainFinder password input: #pasS_word")

        log("Entering TrainFinder login details...")
        username_input.clear()
        username_input.send_keys(username)

        password_input.clear()
        password_input.send_keys(password)

        save_debug(driver, "04_filled_login")

        log("Clicking real TrainFinder login button...")

        clicked = False

        try:
            login_button = driver.find_element(
                By.CSS_SELECTOR,
                "table.login_pane div.button.button-green"
            )

            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                login_button
            )

            time.sleep(1)

            driver.execute_script(
                "arguments[0].click();",
                login_button
            )

            clicked = True
            log("Clicked TrainFinder login button.")
        except Exception as e:
            log(f"CSS login button click failed: {e}")

        if not clicked:
            try:
                driver.execute_script("attemptAuthentication();")
                clicked = True
                log("Triggered TrainFinder login using attemptAuthentication().")
            except Exception as e:
                log(f"JavaScript attemptAuthentication failed: {e}")

        if not clicked:
            save_debug(driver, "05_could_not_click_login")
            raise RuntimeError("Could not click or trigger TrainFinder login")

        time.sleep(10)
        save_debug(driver, "06_after_login_click")

        page_source_lower = driver.page_source.lower()

        if "an error occurred while processing your request" in page_source_lower:
            save_debug(driver, "07_aspnet_error")
            raise RuntimeError("TrainFinder returned ASP.NET error page after login")

        if "invalid" in page_source_lower and "password" in page_source_lower:
            save_debug(driver, "08_invalid_login")
            raise RuntimeError("TrainFinder appears to be rejecting the username or password")

        log("Waiting for .ASPXAUTH cookie...")
        auth_cookie = wait_for_auth_cookie(driver, timeout=45)

        if not auth_cookie:
            save_debug(driver, "09_no_aspxauth_cookie")

            log("Cookies returned by browser:")
            for cookie in driver.get_cookies():
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                safe_value = value[:6] + "..." + value[-6:] if len(value) > 12 else value
                log(f" - {name} = {safe_value}")

            raise RuntimeError("could not establish TrainFinder session - no .ASPXAUTH cookie found")

        log("TrainFinder auth cookie found.")

        close_trainfinder_popup(driver)
        time.sleep(3)

        save_debug(driver, "10_after_popup_close")

        save_cookie_files(driver, auth_cookie)

        log("TrainFinder session established successfully.")

    except Exception as e:
        log(f"Refresh failed: {e}")
        save_debug(driver, "99_failure")
        raise

    finally:
        driver.quit()


if __name__ == "__main__":
    main()