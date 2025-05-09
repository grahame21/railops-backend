from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

import os

username = os.environ.get("TRAINFINDER_USERNAME")
password = os.environ.get("TRAINFINDER_PASSWORD")

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    print("Current URL:", driver.current_url)

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "useR_name"))
    )

    driver.find_element(By.ID, "useR_name").send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)

    login_button = driver.find_element(By.XPATH, "//div[contains(text(),'Log In')]")
    login_button.click()

    WebDriverWait(driver, 10).until(lambda d: d.current_url != "https://trainfinder.otenko.com/home/nextlevel")

    cookies = driver.get_cookies()
    auth_cookie = next((c for c in cookies if c["name"] == ".ASPXAUTH"), None)

    if not auth_cookie:
        raise Exception("❌ .ASPXAUTH cookie not found.")

    with open("cookie.txt", "w") as f:
        f.write(auth_cookie["value"])
        print("✅ Saved .ASPXAUTH cookie.")

    with open("location.txt", "w") as f:
        f.write(driver.current_url)
        print("✅ Saved current location.")

except Exception as e:
    print("❌ Login error:", e)

finally:
    driver.quit()