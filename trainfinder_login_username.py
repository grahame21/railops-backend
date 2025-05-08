from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os

username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")
print("Current URL:", driver.current_url)

try:
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "useR_name")))
    driver.find_element(By.ID, "useR_name").send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "btnLogiN")))
    driver.find_element(By.ID, "btnLogiN").click()

    WebDriverWait(driver, 10).until(lambda d: "NextLevel" in d.current_url)

    # Save cookie
    cookie = driver.get_cookie(".ASPXAUTH")["value"]
    with open("cookie.txt", "w") as f:
        f.write(cookie)
    print("✅ .ASPXAUTH cookie saved locally.")

except Exception as e:
    print("❌ Login error:", e)
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)

driver.quit()