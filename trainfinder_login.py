import os
import time
import subprocess
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Load secrets
username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")
proxy_user = os.getenv("PROXYMESH_USERNAME")
proxy_pass = os.getenv("PROXYMESH_PASSWORD")

# ProxyMesh config
proxy = f"http://{proxy_user}:{proxy_pass}@au.proxymesh.com:31280"

options = uc.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument(f'--proxy-server={proxy}')

driver = uc.Chrome(options=options, headless=True)

try:
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    time.sleep(3)

    try:
        username_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "Username"))
        )
        username_field.send_keys(username)
        driver.find_element(By.ID, "Password").send_keys(password)
        driver.find_element(By.ID, "Password").send_keys(Keys.RETURN)
        time.sleep(5)

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
        subprocess.run("git config user.name github-actions", shell=True)
        subprocess.run("git config user.email actions@github.com", shell=True)
        subprocess.run("git add login_fail.png login_debug.html", shell=True)
        subprocess.run("git commit -m 'Auto debug files from failed login'", shell=True)
        subprocess.run("git push", shell=True)
        raise e

finally:
    driver.quit()