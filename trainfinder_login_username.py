from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Setup
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(options=options)

# Navigate to TrainFinder
driver.get("https://trainfinder.otenko.com/home/nextlevel")
print("Current URL:", driver.current_url)

try:
    # Enter login details
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "useR_name"))
    )
    driver.find_element(By.ID, "useR_name").send_keys("RAIL-01")
    driver.find_element(By.ID, "pasS_word").send_keys("cextih-jaskoJ-4susda")
    driver.find_element(By.XPATH, "//div[contains(text(), 'Log In')]").click()

    # Wait for login to process
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "mainMenuBar"))
    )

    # Extract .ASPXAUTH cookie
    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie['name'] == '.ASPXAUTH':
            with open("cookie.txt", "w") as f:
                f.write(cookie['value'])
            print("✅ .ASPXAUTH cookie saved.")

    # Try to find current location (if town/suburb label exists)
    try:
        location_elem = driver.find_element(By.CLASS_NAME, "stationDisplay")
        location = location_elem.text.strip()
        with open("location.txt", "w") as locf:
            locf.write(location)
        print("📍 Location saved:", location)
    except:
        print("⚠️ Location not found.")

except Exception as e:
    print("❌ Login error:", str(e))

finally:
    driver.quit()