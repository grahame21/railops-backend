import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Get environment variables
username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")
proxy_user = os.getenv("PROXYMESH_USERNAME")
proxy_pass = os.getenv("PROXYMESH_PASSWORD")

# Set up ProxyMesh
proxy = f"http://{proxy_user}:{proxy_pass}@au.proxymesh.com:31280"

# Set Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument(f"--proxy-server={proxy}")

# Launch Chrome
driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    time.sleep(3)  # allow page redirect or dynamic content to start loading

    # Wait for login form to appear
    email_field = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "Email"))
    )
    email_field.send_keys(username)
    driver.find_element(By.ID, "Password").send_keys(password)
    driver.find_element(By.ID, "Password").send_keys(Keys.RETURN)

    time.sleep(5)  # wait for login to process

    # Extract .ASPXAUTH cookie
    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie['name'] == '.ASPXAUTH':
            with open("cookie.txt", "w") as f:
                f.write(cookie['value'])
            print("Cookie saved.")
            break
    else:
        raise Exception("Login failed or .ASPXAUTH cookie not found.")

except Exception as e:
    print("Error during login:", e)
    driver.save_screenshot("login_fail.png")
    raise

finally:
    driver.quit()