import os
import pickle
import time
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

print("=" * 60)
print("🔄 REFRESHING TRAINFINDER COOKIE")
print("=" * 60)
print(f"Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()
COOKIE_FILE = "trainfinder_cookies.pkl"

if not TF_USERNAME or not TF_PASSWORD:
    print("❌ Missing TrainFinder credentials")
    sys.exit(1)

print(f"✅ Credentials loaded")

def login_and_get_cookies():
    print("\n🔧 Setting up Chrome...")
    
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    try:
        print("\n📌 Navigating to TrainFinder...")
        driver.get("https://trainfinder.otenko.com/home/nextlevel")
        time.sleep(5)
        
        # Look for login trigger
        try:
            login_trigger = driver.find_element(By.XPATH, "//*[contains(text(), 'Login')]")
            login_trigger.click()
            print("✅ Clicked login trigger")
            time.sleep(3)
        except:
            pass
        
        # Fill username
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.clear()
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        time.sleep(1)
        
        # Fill password
        password = driver.find_element(By.ID, "pasS_word")
        password.clear()
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        time.sleep(1)
        
        # Click login button (DIV)
        login_button = driver.find_element(By.CSS_SELECTOR, "div.button-green")
        driver.execute_script("arguments[0].click();", login_button)
        print("✅ Clicked login button")
        time.sleep(8)
        
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
            print("✅ Closed warning popup")
        except:
            pass
        
        # Get cookies
        cookies = driver.get_cookies()
        print(f"\n📦 Found {len(cookies)} cookies")
        
        if len(cookies) == 0:
            print("❌ No cookies found")
            return False
        
        # Save cookies
        with open(COOKIE_FILE, 'wb') as f:
            pickle.dump(cookies, f)
        print(f"✅ Saved cookies to {COOKIE_FILE}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        driver.quit()

if __name__ == "__main__":
    success = login_and_get_cookies()
    sys.exit(0 if success else 1)
