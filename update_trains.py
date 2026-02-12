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
        for k in ["trains", "Trains", "markers", "Markers", "features", "data"]:
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
    """Target the specific field IDs we saw in the debug log"""
    
    print("🔄 Starting login with specific field IDs...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = None
    try:
        # Install driver and launch
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Load login page
        print(f"🔄 Loading: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(3)
        
        # TRY 1: Look for the specific IDs we saw
        print("🔍 Trying field IDs from debug log...")
        
        # Try username field - use the exact ID from debug log
        try:
            username = driver.find_element(By.ID, "useR_name")
            print("✅ Found username field with ID: useR_name")
        except:
            try:
                username = driver.find_element(By.ID, "un")
                print("✅ Found username field with ID: un")
            except:
                print("❌ Could not find username field")
                return None
        
        username.clear()
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        
        # Try password field - use the exact ID from debug log
        try:
            password = driver.find_element(By.ID, "pasS_word")
            print("✅ Found password field with ID: pasS_word")
        except:
            try:
                password = driver.find_element(By.ID, "pw")
                print("✅ Found password field with ID: pw")
            except:
                print("❌ Could not find password field")
                return None
        
        password.clear()
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        
        # Look for ANY button that might be a login button
        print("🔍 Looking for login/submit button...")
        
        # Try to find any button or submit input
        login_button = None
        
        # Method 1: Look for button with "Login" or "Sign" text
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            btn_text = btn.text.lower()
            if "login" in btn_text or "sign" in btn_text or "submit" in btn_text:
                login_button = btn
                print(f"✅ Found button with text: '{btn.text}'")
                break
        
        # Method 2: Look for any submit input
        if not login_button:
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                if inp.get_attribute("type") == "submit":
                    login_button = inp
                    print("✅ Found submit input button")
                    break
        
        # Method 3: Just click the first button if nothing else found
        if not login_button and buttons:
            login_button = buttons[0]
            print("⚠️ Using first available button")
        
        if not login_button:
            print("❌ Could not find any button to click")
            driver.save_screenshot("no_button.png")
            return None
        
        # Click the button
        login_button.click()
        print("✅ Login button clicked")
        time.sleep(5)
        
        # Check for warning/continue page
        page_source = driver.page_source.lower()
        if "warning" in page_source or "continue" in page_source or "proceed" in page_source:
            print("⚠️ Warning page detected, looking for continue button...")
            
            # Look for continue button
            continue_btn = None
            for btn in driver.find_elements(By.TAG_NAME, "button"):
                btn_text = btn.text.lower()
                if "continue" in btn_text or "proceed" in btn_text or "accept" in btn_text:
                    continue_btn = btn
                    break
            
            if continue_btn:
                continue_btn.click()
                print("✅ Continue button clicked")
                time.sleep(3)
        
        # Get cookies
        cookies = driver.get_cookies()
        print(f"✅ Got {len(cookies)} cookies")
        
        if len(cookies) == 0:
            print("⚠️ No cookies received - login may have failed")
            return None
        
        # Convert to cookie string
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        return cookie_str
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        try:
            driver.save_screenshot("error.png")
            print("📸 Error screenshot saved")
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
            return [], f"Redirected to: {location}"
        
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
    print(f"🚂 LOGIN ATTEMPT - {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
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
