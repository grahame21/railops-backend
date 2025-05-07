from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

USERNAME = "your-email@example.com"
PASSWORD = "your-password"

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")
time.sleep(2)

driver.find_element("id", "Username").send_keys(USERNAME)
driver.find_element("id", "Password").send_keys(PASSWORD)
driver.find_element("xpath", "//input[@value='Login']").click()
time.sleep(3)

cookies = driver.get_cookies()
for cookie in cookies:
    if cookie["name"] == ".ASPXAUTH":
        with open("cookie.txt", "w") as f:
            f.write(cookie["value"])
        break

driver.quit()
