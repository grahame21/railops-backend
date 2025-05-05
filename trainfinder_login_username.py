import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

USERNAME = os.environ.get("TRAINFINDER_USERNAME")
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD")

if not USERNAME or not PASSWORD:
    raise Exception("❌ Missing login credentials in environment variables.")

options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")

try:
    print("Logging in to TrainFinder...")
    time.sleep(3)

    driver.find_element(By.ID, "useR_name").send_keys(USERNAME)
    pw_field = driver.find_element(By.ID, "pasS_word")
    pw_field.send_keys(PASSWORD)
    pw_field.send_keys(Keys.RETURN)

    time.sleep(5)

    cookies = driver.get_cookies()
    auth_cookie = next((c["value"] for c in cookies if c["name"] == ".ASPXAUTH"), None)

    if auth_cookie:
        with open("cookie.txt", "w") as f:
            f.write(auth_cookie)
        print("✅ .ASPXAUTH cookie saved to cookie.txt")
    else:
        print("❌ .ASPXAUTH cookie not found — login likely failed")

except Exception as e:
    print("❌ Login failed:", e)

finally:
    driver.quit()
