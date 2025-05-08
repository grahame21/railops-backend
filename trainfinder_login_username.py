from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time

username = os.environ.get("TRAINFINDER_USERNAME")
password = os.environ.get("TRAINFINDER_PASSWORD")

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "useR_name")))

    # Fill in the login form
    driver.find_element(By.ID, "useR_name").send_keys(username)
    driver.find_element(By.ID, "user_passworD").send_keys(password)
    driver.find_element(By.ID, "btnLogiN").click()

    # Wait for redirect or cookie to appear
    WebDriverWait(driver, 10).until(lambda d: d.current_url != "https://trainfinder.otenko.com/home/nextlevel")
    print("Current URL:", driver.current_url)

    cookies = driver.get_cookies()
    auth_cookie = next((c["value"] for c in cookies if c.get("name") == ".ASPXAUTH"), None)

    if auth_cookie:
        with open("cookie.txt", "w") as f:
            f.write(auth_cookie)
        print("✅ .ASPXAUTH cookie saved locally.")
    else:
        print("❌ Login failed: .ASPXAUTH cookie not found.")
        exit(1)

except Exception as e:
    print("❌ Login error:", str(e))
    exit(1)
finally:
    driver.quit()