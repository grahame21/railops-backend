from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import os
import time

USERNAME = os.getenv("TRAINFINDER_USERNAME")
PASSWORD = os.getenv("TRAINFINDER_PASSWORD")

options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")

# Wait to ensure page is fully loaded
time.sleep(3)

# Fill in the login fields
driver.find_element(By.ID, "useR_name").send_keys(USERNAME)
driver.find_element(By.ID, "pasS_word").send_keys(PASSWORD)

# Press Enter or simulate login
driver.find_element(By.ID, "pasS_word").submit()

# Wait for login to complete
time.sleep(5)

# Get cookies
cookies = driver.get_cookies()
for cookie in cookies:
    if cookie['name'] == '.ASPXAUTH':
        with open("cookie.txt", "w") as f:
            f.write(cookie['value'])

driver.quit()

print("✅ .ASPXAUTH cookie saved locally.")