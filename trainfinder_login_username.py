from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

USERNAME = "RAIL-01"
PASSWORD = "cextih-jaskoJ-4susda"

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")

# Attempt logout if already logged in
try:
    logout_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//span[text()='QUIT']"))
    )
    logout_button.click()
    print("✅ Logged out first.")
    time.sleep(2)
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
except Exception:
    print("⚠️ No logout needed. Proceeding to login...")

# Attempt login
try:
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "useR_name"))
    ).send_keys(USERNAME)

    driver.find_element(By.ID, "pasS_word").send_keys(PASSWORD)
    driver.find_element(By.XPATH, "//div[text()='Log In']").click()

    # Wait for login to complete
    WebDriverWait(driver, 10).until(EC.url_contains("nextlevel"))
    print("✅ Logged in successfully.")
except Exception as e:
    print("❌ Login failed:", e)
    driver.quit()
    exit(1)

# Save .ASPXAUTH cookie to cookie.txt
cookie = next((c for c in driver.get_cookies() if c["name"] == ".ASPXAUTH"), None)
if cookie:
    with open("cookie.txt", "w") as f:
        f.write(cookie["value"])
    print("✅ .ASPXAUTH cookie saved.")
else:
    print("❌ .ASPXAUTH cookie not found.")

driver.quit()
