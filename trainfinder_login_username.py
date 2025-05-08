from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Set up Chrome in headless mode
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

# Launch browser
driver = webdriver.Chrome(options=chrome_options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")

# Wait until login page loads
WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "useR_name")))

# Fill in login fields
driver.find_element(By.ID, "useR_name").send_keys("RAIL-01")
driver.find_element(By.ID, "pasS_word").send_keys("cextih-jaskoJ-4susda")

# Print current URL for debugging
print("Current URL:", driver.current_url)

# Try to click login button
try:
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "btnLogiN"))
    ).click()
except:
    # Fallback if the button ID changes
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and contains(@value, 'Login')]"))
    ).click()

# Wait for login to complete and cookie to be set
WebDriverWait(driver, 10).until(lambda d: ".ASPXAUTH" in [c['name'] for c in d.get_cookies()])

# Extract .ASPXAUTH cookie
cookie_value = None
for cookie in driver.get_cookies():
    if cookie["name"] == ".ASPXAUTH":
        cookie_value = cookie["value"]
        break

# Save cookie to file
if cookie_value:
    with open("cookie.txt", "w") as f:
        f.write(cookie_value)
    print("✅ .ASPXAUTH cookie saved locally.")
else:
    print("❌ Login failed or cookie not found.")

# Clean up
driver.quit()