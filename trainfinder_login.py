import os
import time
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Load secrets from GitHub Actions environment
username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")
proxy_user = os.getenv("PROXYMESH_USERNAME")
proxy_pass = os.getenv("PROXYMESH_PASSWORD")

# Set proxy server
proxy = f"http://{proxy_user}:{proxy_pass}@au.proxymesh.com:31280"

# Configure headless Chrome
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument(f"--proxy-server={proxy}")

# Launch browser
driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    time.sleep(3)

    try:
        # Wait for login form
        username_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "Username"))
        )
        username_field.send_keys(username)
        driver.find_element(By.ID, "Password").send_keys(password)
        driver.find_element(By.ID, "Password").send_keys(Keys.RETURN)

        time.sleep(5)

        # Grab cookie
        cookies = driver.get_cookies()
        for cookie in cookies:
            if cookie['name'] == '.ASPXAUTH':
                with open("cookie.txt", "w") as f:
                    f.write(cookie['value'])
                print("Cookie saved.")
                break
        else:
            raise Exception("Login succeeded but .ASPXAUTH cookie not found.")

    except Exception as e:
        print("Login form did not load or failed.")
        driver.save_screenshot("login_fail.png")
        with open("login_debug.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        # Auto-commit debug files to GitHub repo
        subprocess.run("git config user.name github-actions", shell=True)
        subprocess.run("git config user.email actions@github.com", shell=True)
        subprocess.run("git add login_fail.png login_debug.html", shell=True)
        subprocess.run("git commit -m 'Auto debug files from failed login'", shell=True)
        subprocess.run("git push", shell=True)

        raise e

finally:
    driver.quit()