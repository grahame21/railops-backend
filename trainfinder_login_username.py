from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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

# Wait for full page load
time.sleep(3)

# Fill in username and password
driver.find_element(By.ID, "useR_name").send_keys(USERNAME)
password_input = driver.find_element(By.ID, "pasS_word")
password_input.send_keys(PASSWORD)

# Press Enter to trigger login
password_input.send_keys(Keys.RETURN)

# Wait for login to process
time.sleep(5)

# Look for the cookie
cookies = driver.get_cookies()
for cookie in cookies:
    if cookie['name'] == '.ASPXAUTH':
        with open("cookie.txt", "w") as f:
            f.write(cookie['value'])

driver.quit()
print("✅ .ASPXAUTH cookie saved locally.")