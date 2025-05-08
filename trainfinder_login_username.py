from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os

# Load credentials from environment
username = os.environ.get("TRAINFINDER_USERNAME")
password = os.environ.get("TRAINFINDER_PASSWORD")

# Setup headless browser
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    print("Current URL:", driver.current_url)

    # Wait for the fields to load
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "useR_name")))

    # Enter login info
    driver.find_element(By.ID, "useR_name").send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)

    # Click the login <div>
    login_button = driver.find_element(By.XPATH, '//div[contains(@class, "button-green") and contains(text(), "Log In")]')
    login_button.click()

    # Wait for successful login (e.g. change in URL or disappearance of login fields)
    WebDriverWait(driver, 15).until(EC.url_contains("nextlevel"))

    # Extract .ASPXAUTH cookie
    cookies = driver.get_cookies()
    auth_cookie = next((c for c in cookies if c["name"] == ".ASPXAUTH"), None)

    if auth_cookie:
        with open("cookie.txt", "w") as f:
            f.write(auth_cookie["value"])
        print("✅ .ASPXAUTH cookie saved locally.")
        print("==== COPY BELOW AND UPDATE IN GITHUB SECRETS ====")
        print(auth_cookie["value"])
        print("==== END COOKIE ====")
    else:
        print("❌ .ASPXAUTH cookie not found.")

except Exception as e:
    print(f"❌ Login error: {e}")

finally:
    driver.quit()