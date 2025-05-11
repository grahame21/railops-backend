import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

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

    # Login form is on /home/nextlevel, not /account/login
    driver.find_element(By.ID, "Email").send_keys(username)
    driver.find_element(By.ID, "Password").send_keys(password)
    driver.find_element(By.ID, "Password").send_keys(Keys.RETURN)

    time.sleep(5)

    # Extract cookie
    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie['name'] == '.ASPXAUTH':
            with open("cookie.txt", "w") as f:
                f.write(cookie['value'])
            print("Cookie saved.")
            break
    else:
        raise Exception("Login failed or .ASPXAUTH cookie not found.")

finally:
    driver.quit()