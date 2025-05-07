from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import os

USERNAME = os.getenv("TRAINFINDER_USERNAME")
PASSWORD = os.getenv("TRAINFINDER_PASSWORD")

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    time.sleep(2)

    driver.find_element(By.ID, "useR_name").send_keys(USERNAME)
    driver.find_element(By.ID, "pasS_word").send_keys(PASSWORD)
    driver.find_element(By.ID, "btnLogiN").click()
    time.sleep(4)

    # Save .ASPXAUTH cookie
    for cookie in driver.get_cookies():
        if cookie['name'] == '.ASPXAUTH':
            with open("cookie.txt", "w") as f:
                f.write(cookie['value'])
            print("✅ .ASPXAUTH cookie saved locally.")
            print("==== COPY BELOW AND UPDATE IN GITHUB SECRETS ====")
            print(cookie['value'])
            print("==== END COOKIE ====")

finally:
    driver.quit()