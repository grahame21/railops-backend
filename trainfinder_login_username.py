import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

username = os.environ["TRAINFINDER_USERNAME"]
password = os.environ["TRAINFINDER_PASSWORD"]

# Set up headless Chrome
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

# Ensure logout first
driver.get("https://trainfinder.otenko.com/account/logout")
time.sleep(1)

# Go to login page
driver.get("https://trainfinder.otenko.com/home/nextlevel")
print("Current URL:", driver.current_url)

try:
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "useR_name")))
    driver.find_element(By.ID, "useR_name").send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)
    driver.find_element(By.ID, "btnLogiN").click()

    # Wait for successful login
    WebDriverWait(driver, 10).until(lambda d: "NextLevel" in d.current_url)
except Exception as e:
    print("❌ Login error:", e)
    driver.quit()
    exit(1)

# Grab .ASPXAUTH cookie
cookie_value = None
for cookie in driver.get_cookies():
    if cookie["name"] == ".ASPXAUTH":
        cookie_value = cookie["value"]
        break

driver.quit()

# Save cookie
if cookie_value:
    with open("cookie.txt", "w") as f:
        f.write(cookie_value)
    print("✅ .ASPXAUTH cookie saved locally.")
else:
    print("❌ Failed to find .ASPXAUTH cookie.")
    exit(1)