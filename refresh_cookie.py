import os
import pickle
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

print("🔄 Refreshing TrainFinder cookie...")

username = os.environ.get("TF_USERNAME", "")
password = os.environ.get("TF_PASSWORD", "")

if not username or not password:
    print("❌ Missing credentials")
    exit(1)

options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--window-size=1920,1080')

driver = webdriver.Chrome(options=options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")
time.sleep(3)

driver.find_element(By.ID, "useR_name").send_keys(username)
driver.find_element(By.ID, "pasS_word").send_keys(password)
driver.execute_script("document.querySelector('div.button-green').click()")
time.sleep(5)

# Close warning if present
try:
    driver.execute_script("""
        var paths = document.getElementsByTagName('path');
        for(var i = 0; i < paths.length; i++) {
            var d = paths[i].getAttribute('d') || '';
            if(d.includes('M13.7,11l6.1-6.1')) {
                var parent = paths[i].parentElement;
                while(parent && parent.tagName !== 'BUTTON' && parent.tagName !== 'DIV' && parent.tagName !== 'A') {
                    parent = parent.parentElement;
                }
                if(parent) parent.click();
                break;
            }
        }
    """)
except:
    pass

time.sleep(3)

cookies = driver.get_cookies()
print(f"✅ Got {len(cookies)} cookies")

with open("trainfinder_cookies.pkl", "wb") as f:
    pickle.dump(cookies, f)

driver.quit()
print("✅ Cookie saved")
