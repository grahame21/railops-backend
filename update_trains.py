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

def login_and_get_session():
    """Login and capture FULL browser session state (cookies + localStorage + sessionStorage)"""
    
    print("🔄 Starting login with full session capture...")
    
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
        
        # Find username field - use the exact ID from debug
        try:
            username = driver.find_element(By.ID, "useR_name")
            print("✅ Found username field with ID: useR_name")
        except:
            try:
                username = driver.find_element(By.ID, "un")
                print("✅ Found username field with ID: un")
            except:
                print("❌ Could not find username field")
                driver.save_screenshot("no_username.png")
                return None
        
        username.clear()
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        
        # Find password field - use the exact ID from debug
        try:
            password = driver.find_element(By.ID, "pasS_word")
            print("✅ Found password field with ID: pasS_word")
        except:
            try:
                password = driver.find_element(By.ID, "pw")
                print("✅ Found password field with ID: pw")
            except:
                print("❌ Could not find password field")
                driver.save_screenshot("no_password.png")
                return None
        
        password.clear()
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        
        # Look for ANY button that might submit
        print("🔍 Looking for submit button...")
        
        # Try to find the actual login button - it might be hidden or have specific text
        login_button = None
        
        # Check all buttons
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            btn_text = btn.text.lower().strip()
            btn_html = btn.get_attribute("outerHTML").lower()
            if "login" in btn_text or "sign in" in btn_text or "submit" in btn_text:
                login_button = btn
                print(f"✅ Found login button with text: '{btn.text}'")
                break
        
        # Check input type submit
        if not login_button:
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                if inp.get_attribute("type") == "submit":
                    login_button = inp
                    print("✅ Found submit input button")
                    break
        
        # Try to find by common class names
        if not login_button:
            for btn in buttons:
                btn_class = btn.get_attribute("class") or ""
                if "btn" in btn_class.lower() and "primary" in btn_class.lower():
                    login_button = btn
                    print("✅ Found button with btn-primary class")
                    break
        
        # Last resort - click the first button that's not zoom control
        if not login_button:
            for btn in buttons:
                btn_text = btn.text.strip()
                if btn_text not in ["+", "−", "i"]:  # Not zoom buttons
                    login_button = btn
                    print("⚠️ Using first non-control button")
                    break
        
        if not login_button:
            print("❌ Could not find any button to click")
            driver.save_screenshot("no_button.png")
            return None
        
        # Click the button
        driver.execute_script("arguments[0].click();", login_button)
        print("✅ Login button clicked via JavaScript")
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
                driver.execute_script("arguments[0].click();", continue_btn)
                print("✅ Continue button clicked")
                time.sleep(3)
        
        # Now try to access the train data page directly
        print(f"🔄 Navigating to train data endpoint...")
        driver.get(TF_URL)
        time.sleep(3)
        
        # Check what we got
        page_text = driver.page_source
        content_type = None
        
        # Try to determine if we got JSON or HTML
        if page_text.strip().startswith(("{", "[")):
            print("✅ Successfully accessed JSON endpoint!")
            content_type = "application/json"
        else:
            print("⚠️ Got HTML response, not JSON")
            content_type = "text/html"
        
        # CAPTURE EVERYTHING - cookies, localStorage, sessionStorage
        print("📦 Capturing full session state...")
        
        # 1. Cookies
        cookies = driver.get_cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}
        print(f"✅ Captured {len(cookies)} cookies")
        
        # 2. localStorage
        localStorage = driver.execute_script("""
            var items = {};
            for (var i = 0; i < localStorage.length; i++) {
                var key = localStorage.key(i);
                items[key] = localStorage.getItem(key);
            }
            return items;
        """) or {}
        print(f"✅ Captured {len(localStorage)} localStorage items")
        
        # 3. sessionStorage
        sessionStorage = driver.execute_script("""
            var items = {};
            for (var i = 0; i < sessionStorage.length; i++) {
                var key = sessionStorage.key(i);
                items[key] = sessionStorage.getItem(key);
            }
            return items;
        """) or {}
        print(f"✅ Captured {len(sessionStorage)} sessionStorage items")
        
        # 4. Current URL and page title
        current_url = driver.current_url
        page_title = driver.title
        
        # Save screenshot of successful login
        driver.save_screenshot("login_success.png")
        print("📸 Login success screenshot saved")
        
        # Return COMPLETE session state
        session_state = {
            "cookies": cookie_dict,
            "localStorage": localStorage,
            "sessionStorage": sessionStorage,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "referer": TF_LOGIN_URL,
            "current_url": current_url,
            "page_title": page_title
        }
        
        return session_state
        
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

def fetch_train_data_with_session(session_state):
    """Fetch train data using captured session state"""
    
    if not session_state:
        return [], "No session state"
    
    session = requests.Session()
    
    # Set cookies
    if session_state.get("cookies"):
        session.cookies.update(session_state["cookies"])
    
    # Set headers
    session.headers.update({
        "User-Agent": session_state.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": session_state.get("referer", TF_LOGIN_URL)
    })
    
    # If there's localStorage, we might need to send it as headers or in the request body
    # Some sites use X-* headers for auth tokens
    if session_state.get("localStorage"):
        for key, value in session_state["localStorage"].items():
            if "token" in key.lower() or "auth" in key.lower() or "session" in key.lower():
                session.headers[f"X-{key}"] = value
                print(f"✅ Added auth header: X-{key}")
    
    try:
        print(f"🔄 Fetching train data with full session...")
        r = session.get(TF_URL, timeout=30, allow_redirects=False)
        print(f"✅ Response: {r.status_code}")
        
        if r.status_code in (301, 302, 303, 307, 308):
            location = r.headers.get("Location", "unknown")
            print(f"⚠️ Redirected to: {location}")
            return [], f"Redirected to: {location}"
        
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        
        if "application/json" not in r.headers.get("content-type", "").lower():
            preview = r.text[:200] if r.text else "empty"
            print(f"⚠️ Non-JSON response: {preview}")
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
        print(f"❌ Fetch error: {type(e).__name__}: {str(e)}")
        return [], f"Error: {type(e).__name__}"

def main():
    print("=" * 60)
    print(f"🚂 FULL SESSION CAPTURE - {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    # Login and capture full session state
    session_state = login_and_get_session()
    
    if not session_state:
        print("❌ Login failed - no session state")
        write_output([], "Login failed")
        return
    
    print(f"✅ Session captured successfully")
    print(f"   - Cookies: {len(session_state.get('cookies', {}))}")
    print(f"   - localStorage: {len(session_state.get('localStorage', {}))}")
    print(f"   - sessionStorage: {len(session_state.get('sessionStorage', {}))}")
    
    # Fetch train data using captured session
    trains, note = fetch_train_data_with_session(session_state)
    write_output(trains, note)
    
    print(f"🏁 Complete: {len(trains)} trains")
    print("=" * 60)

if __name__ == "__main__":
    main()
