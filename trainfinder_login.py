import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")
proxy_user = os.getenv("PROXYMESH_USERNAME")
proxy_pass = os.getenv("PROXYMESH_PASSWORD")

proxy = f"http://{proxy_user}:{proxy_pass}@au.proxymesh.com:31280"

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument(f"--proxy-server={proxy}")

driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    time.sleep(3)

    try:
        # Fix: Wait for Username instead of Email
        username_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "Username"))
        )
        username_field.send_keys(username)
        driver.find_element(By.ID, "Password").send_keys(password)
        driver.find_element(By.ID, "Password").send_keys(Keys.RETURN)

        time.sleep(5)

        # Save cookie
        cookies = driver.get_cookies()
        for cookie in cookies:
            if cookie['name'] == '.ASPXAUTH':
                with open("cookie.txt", "w") as f:
                    f.write(cookie['value'])
                print("Cookie saved.")
                break
        else:
            raise Exception("Login succeeded but no cookie found.")

    except Exception as e:
        print("Login form did not load or failed.")
        driver.save_screenshot("login_fail.png")
        with open("login_debug.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise e

finally:
    driver.quit()