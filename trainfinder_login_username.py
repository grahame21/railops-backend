# trainfinder_login_username.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os

username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

print("Launching browser to login...")
driver = webdriver.Chrome(options=chrome_options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")
print("Current URL:", driver.current_url)

try:
    driver.find_element(By.ID, "useR_name").send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)
    driver.find_element(By.XPATH, "//div[contains(@class, 'button-green')]").click()

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "zoomToTrain"))
    )

    cookies = driver.get_cookies()
    aspx_cookie = next((c["value"] for c in cookies if c["name"] == ".ASPXAUTH"), None)

    if aspx_cookie:
        with open("cookie.txt", "w") as f:
            f.write(aspx_cookie)
        print("✅ Login successful. Cookie saved to cookie.txt")
    else:
        print("❌ .ASPXAUTH cookie not found.")
        exit(1)

except Exception as e:
    print("❌ Login error:", e)
    exit(1)

finally:
    driver.quit()
