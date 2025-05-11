import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Load credentials from environment
USERNAME = os.getenv("TRAINFINDER_USERNAME")
PASSWORD = os.getenv("TRAINFINDER_PASSWORD")

# Start headless Chrome
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")

    # Wait for login input fields
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "useR_name"))
    )
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "pasS_word"))
    )

    # Enter username and password
    driver.find_element(By.ID, "useR_name").send_keys(USERNAME)
    driver.find_element(By.ID, "pasS_word").send_keys(PASSWORD)

    # Click the login button
    login_button = driver.find_element(By.XPATH, '//div[text()="Log In"]')
    login_button.click()

    # Wait for login to complete
    WebDriverWait(driver, 10).until(
        lambda d: "nextlevel" in d.current_url or ".ASPXAUTH" in [c['name'] for c in d.get_cookies()]
    )

    print("Current URL:", driver.current_url)

    # Extract .ASPXAUTH cookie
    auth_cookie = next((c for c in driver.get_cookies() if c["name"] == ".ASPXAUTH"), None)
    if auth_cookie:
        with open("cookie.txt", "w") as f:
            f.write(f"{auth_cookie['name']}={auth_cookie['value']}")
        print("✅ Cookie saved to cookie.txt")
    else:
        print("❌ .ASPXAUTH cookie not found.")

except Exception as e:
    print("❌ Login error:", e)

finally:
    driver.quit()
