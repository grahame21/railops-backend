import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

USERNAME = os.getenv("TRAINFINDER_USERNAME")
PASSWORD = os.getenv("TRAINFINDER_PASSWORD")

if not USERNAME or not PASSWORD:
    print("❌ Missing credentials. Make sure TRAINFINDER_USERNAME and TRAINFINDER_PASSWORD are set.")
    exit(1)

# Set up headless Chrome
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    time.sleep(2)

    driver.find_element(By.ID, "useR_name").send_keys(USERNAME)
    driver.find_element(By.ID, "pasS_word").send_keys(PASSWORD)
    driver.find_element(By.ID, "btnLogiN").click()
    time.sleep(3)

    # Grab .ASPXAUTH cookie
    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie["name"] == ".ASPXAUTH":
            with open("cookie.txt", "w") as f:
                f.write(cookie["value"])
            print("✅ .ASPXAUTH cookie saved locally.")
            print("==== COPY BELOW AND UPDATE IN GITHUB SECRETS ====")
            print(cookie["value"])
            print("==== END COOKIE ====")
            break
    else:
        print("❌ .ASPXAUTH cookie not found. Login may have failed.")

finally:
    driver.quit()