import os
import json
import datetime
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import requests

OUT_FILE = "trains.json"
TF_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

def write_output(trains, note=""):
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains or []
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"📝 Output: {len(trains or [])} trains, status: {note}")

def extract_list(data):
    if not data: return []
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ["trains", "Trains", "markers", "Markers", "features"]:
            if isinstance(data.get(k), list):
                return data[k]
    return []

def to_float(x):
    try: return float(x) if x is not None else None
    except: return None

def norm_item(item, i):
    if not isinstance(item, dict): return None
    return {
        "id": str(item.get("id") or item.get("ID") or f"train_{i}"),
        "lat": to_float(item.get("lat") or item.get("latitude")),
        "lon": to_float(item.get("lon") or item.get("longitude")),
        "operator": item.get("operator") or "",
        "heading": to_float(item.get("heading") or 0)
    }

def login_and_get_cookies():
    """Targeted login using the exact element IDs we now know exist"""
    
    print("🔄 Starting targeted login...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print(f"🔄 Loading login page: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        
        # Wait for JavaScript to render the form
        time.sleep(5)
        
        # Find username field - we KNOW the ID is useR_name
        try:
            username = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            print("✅ Found username field")
            username.clear()
            username.send_keys(TF_USERNAME)
            print("✅ Username entered")
        except:
            print("❌ Could not find username field")
            driver.save_screenshot("debug_no_username.png")
            return None
        
        # Find password field - we KNOW the ID is pasS_word
        try:
            password = driver.find_element(By.ID, "pasS_word")
            print("✅ Found password field")
            password.clear()
            password.send_keys(TF_PASSWORD)
            print("✅ Password entered")
        except:
            print("❌ Could not find password field")
            driver.save_screenshot("debug_no_password.png")
            return None
        
        # Find and click the Log In button
        # The button text is exactly "Log In"
        try:
            # Look for button with exact text "Log In"
            buttons = driver.find_elements(By.TAG_NAME, "button")
            login_button = None
            for btn in buttons:
                if btn.text.strip() == "Log In":
                    login_button = btn
                    break
            
            if login_button:
                driver.execute_script("arguments[0].click();", login_button)
                print("✅ Log In button clicked")
            else:
                print("❌ Could not find Log In button")
                driver.save_screenshot("debug_no_button.png")
                return None
        except Exception as e:
            print(f"❌ Error clicking button: {str(e)}")
            return None
        
        # Wait for login to process
        time.sleep(5)
        
        # Check if we got redirected away from login page
        current_url = driver.current_url
        if "nextlevel" not in current_url:
            print(f"✅ Redirected to: {current_url}")
        else:
            print("⚠️ Still on login page - may have failed")
        
        # Get cookies
        cookies = driver.get_cookies()
        print(f"✅ Got {len(cookies)} cookies")
        
        if len(cookies) == 0:
            print("⚠️ No cookies - checking localStorage...")
            # Some sites use localStorage instead of cookies
            localStorage = driver.execute_script("return Object.keys(localStorage).map(key => ({key, value: localStorage.getItem(key)}));")
            print(f"📦 Found {len(localStorage)} localStorage items")
            
            if localStorage:
                # If we have localStorage, we might still be authenticated
                print("✅ Authentication may be in localStorage")
        
        # Convert cookies to string
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        return cookie_str
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        try:
            driver.save_screenshot("error.png")
        except:
            pass
        return None
    finally:
        if driver:
            driver.quit()
            print("✅ Browser closed")

def fetch_train_data(cookie_str):
    if not cookie_str:
        return [], "No cookies"
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": TF_LOGIN_URL,
        "Cookie": cookie_str
    })
    
    try:
        print(f"🔄 Fetching train data...")
        r = session.get(TF_URL, timeout=30, allow_redirects=False)
        print(f"✅ Response: {r.status_code}")
        
        if r.status_code in (301, 302, 303, 307, 308):
            location = r.headers.get("Location", "unknown")
            print(f"⚠️ Redirected to: {location}")
            return [], f"Redirected"
        
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        
        if "application/json" not in r.headers.get("content-type", "").lower():
            return [], "Non-JSON response"
        
        data = r.json()
        raw_list = extract_list(data)
        
        trains = []
        for i, item in enumerate(raw_list):
            train = norm_item(item, i)
            if train and train.get("lat") and train.get("lon"):
                trains.append(train)
        
        return trains, "ok"
        
    except Exception as e:
        return [], f"Error: {type(e).__name__}"

def main():
    print("=" * 60)
    print(f"🚂 TARGETED LOGIN - Using exact element IDs")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    cookie = login_and_get_cookies()
    
    if not cookie:
        print("❌ Login failed - no cookie")
        write_output([], "Login failed")
        return
    
    print(f"✅ Cookie obtained (length: {len(cookie)})")
    
    trains, note = fetch_train_data(cookie)
    write_output(trains, note)
    
    print(f"🏁 Complete: {len(trains)} trains")
    print("=" * 60)

if __name__ == "__main__":
    main()
