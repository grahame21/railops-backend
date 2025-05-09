from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os

username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    print("Current URL:", driver.current_url)

    # Fill in username/password
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "useR_name"))).send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)

    # Click login button
    driver.find_element(By.CLASS_NAME, "button-green").click()

    # Wait until redirected to map page
    WebDriverWait(driver, 10).until(EC.url_contains("nextlevel"))

    # Extract the .ASPXAUTH cookie
    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie["name"] == ".ASPXAUTH":
            with open("cookie.txt", "w") as f:
                f.write(cookie["value"])
            print("✅ Cookie saved.")
            break
    else:
        raise Exception("❌ .ASPXAUTH cookie not found.")

except Exception as e:
    print("❌ Login error:", str(e))
finally:
    driver.quit()

# Optional: call update_secret.py automatically
os.system("python update_secret.py")
