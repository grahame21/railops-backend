import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

username = os.environ["TRAINFINDER_USERNAME"]
password = os.environ["TRAINFINDER_PASSWORD"]

# Chrome options
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-gpu")

# Start browser
driver = webdriver.Chrome(options=options)
driver.get("https://trainfinder.otenko.com/account/logout")  # force logout

# Then go to login page
driver.get("https://trainfinder.otenko.com/home/nextlevel")
time.sleep(2)
print("Current URL:", driver.current_url)

# Wait for login field
try:
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "useR_name")))
    driver.find_element(By.ID, "useR_name").send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)

    # Click login
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "btnLogiN"))).click()

    # Wait for dashboard redirect
    WebDriverWait(driver, 10).until(lambda d: "NextLevel" in d.current_url)
except Exception as e:
    print("Login form not found or login failed:", e)

# Extract ASPXAUTH cookie
cookie_value = None
for cookie in driver.get_cookies():
    if cookie["name"] == ".ASPXAUTH":
        cookie_value = cookie["value"]
        break

# Save cookie to file
if cookie_value:
    with open("cookie.txt", "w") as f:
        f.write(cookie_value)
    print("✅ .ASPXAUTH cookie saved locally.")
else:
    print("❌ Cookie not found.")

driver.quit()