# trainfinder_login_username.py

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

USERNAME = os.getenv("TRAINFINDER_USERNAME")
PASSWORD = os.getenv("TRAINFINDER_PASSWORD")

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

print("Launching browser...")
driver = webdriver.Chrome(options=chrome_options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")

print("Filling login form...")
try:
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "useR_name")))
    driver.find_element(By.ID, "useR_name").send_keys(USERNAME)
    driver.find_element(By.ID, "pasS_word").send_keys(PASSWORD)
    driver.find_element(By.XPATH, "//div[text()='Log In']").click()
except Exception as e:
    print(f"❌ Login form error: {e}")
    driver.quit()
    exit(1)

print("Waiting for successful login...")
try:
    WebDriverWait(driver, 10).until(EC.url_contains("/home/nextlevel"))
except Exception as e:
    print(f"❌ Login failed: {e}")
    driver.quit()
    exit(1)

print("Login successful, extracting cookies...")
cookies = driver.get_cookies()
aspxauth = None
for cookie in cookies:
    if cookie['name'] == ".ASPXAUTH":
        aspxauth = cookie['value']
        break

if not aspxauth:
    print("❌ .ASPXAUTH cookie not found.")
    driver.quit()
    exit(1)

with open("cookie.txt", "w") as f:
    f.write(aspxauth)
print("✅ Cookie saved to cookie.txt")

driver.quit()
