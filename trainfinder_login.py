import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

USERNAME = "RAIL-01"  # replace with your TrainFinder email
PASSWORD = "cextih-jaskoJ-4susda"           # replace with your TrainFinder password

options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=options)

try:
    print("Opening TrainFinder login page...")
    driver.get("https://trainfinder.otenko.com/home/nextlevel")
    time.sleep(5)

    if "Rules" in driver.page_source:
        print("Detected 'Rules' page, clicking accept...")
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='Accept']").click()
        time.sleep(2)

    print("Filling in login credentials...")
    driver.find_element(By.ID, "useR_name").send_keys(USERNAME)
    driver.find_element(By.ID, "pasS_word").send_keys(PASSWORD)
    driver.find_element(By.XPATH, "//input[@type='submit' and @value='Login']").click()
    time.sleep(5)

    print("Login submitted, saving cookie...")

    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie['name'] == '.ASPXAUTH':
            with open("cookie.txt", "w") as f:
                f.write(cookie['value'])
            print("✅ Cookie saved to cookie.txt")
            break
    else:
        print("❌ Login successful but no .ASPXAUTH cookie found!")

except Exception as e:
    print(f"❌ Error: {e}")

finally:
    driver.quit()
