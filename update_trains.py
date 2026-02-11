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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests
from webdriver_manager.chrome import ChromeDriverManager

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

def log_step(step, status="✅", details=""):
    print(f"{status} STEP {step}: {details}")

def login_and_get_cookies():
    """Debug version with detailed logging"""
    
    log_step("1", "🔄", "Starting login process")
    
    if not TF_USERNAME or not TF_PASSWORD:
        log_step("1", "❌", "Missing credentials")
        return None
    
    log_step("2", "🔄", f"Setting up Chrome (username length: {len(TF_USERNAME)})")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = None
    try:
        log_step("3", "🔄", "Installing ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        log_step("3", "✅", "ChromeDriver installed and browser launched")
        
        log_step("4", "🔄", f"Loading login page: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Save page source for debugging
        page_source = driver.page_source
        page_title = driver.title
        current_url = driver.current_url
        log_step("4", "✅", f"Page loaded - Title: {page_title}, URL: {current_url}")
        
        # Check if we're already on a different page
        if "nextlevel" not in current_url:
            log_step("4", "⚠️", f"Redirected to: {current_url}")
        
        # Try to find ALL input fields to see what's available
        log_step("5", "🔄", "Scanning for input fields...")
        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        log_step("5", "✅", f"Found {len(all_inputs)} input fields")
        
        for i, inp in enumerate(all_inputs):
            input_type = inp.get_attribute("type") or "text"
            input_name = inp.get_attribute("name") or "no-name"
            input_id = inp.get_attribute("id") or "no-id"
            input_placeholder = inp.get_attribute("placeholder") or ""
            log_step("5", "ℹ️", f"  Input {i}: type={input_type}, name={input_name}, id={input_id}, placeholder={input_placeholder}")
        
        # Try to find username field - multiple strategies
        username = None
        
        # Strategy 1: Look for email/username inputs
        for inp in all_inputs:
            input_type = inp.get_attribute("type") or ""
            input_name = (inp.get_attribute("name") or "").lower()
            input_id = (inp.get_attribute("id") or "").lower()
            input_placeholder = (inp.get_attribute("placeholder") or "").lower()
            
            if input_type in ["text", "email"] or "user" in input_name or "email" in input_name or "user" in input_id:
                username = inp
                log_step("6", "✅", f"Found username field - name={inp.get_attribute('name')}, id={inp.get_attribute('id')}")
                break
        
        if not username:
            # Strategy 2: First text input
            for inp in all_inputs:
                if inp.get_attribute("type") in ["text", "email", None]:
                    username = inp
                    log_step("6", "⚠️", f"Using first text input as username field")
                    break
        
        if not username:
            log_step("6", "❌", "Could not find username field")
            driver.save_screenshot("debug_no_username.png")
            return None
        
        username.clear()
        username.send_keys(TF_USERNAME)
        log_step("6", "✅", "Username entered")
        
        # Find password field
        password = None
        for inp in all_inputs:
            if inp.get_attribute("type") == "password":
                password = inp
                log_step("7", "✅", f"Found password field - name={inp.get_attribute('name')}")
                break
        
        if not password:
            log_step("7", "❌", "Could not find password field")
            return None
        
        password.clear()
        password.send_keys(TF_PASSWORD)
        log_step("7", "✅", "Password entered")
        
        # Find login button
        log_step("8", "🔄", "Looking for login button...")
        
        # Try buttons first
        buttons = driver.find_elements(By.TAG_NAME, "button")
        log_step("8", "✅", f"Found {len(buttons)} button elements")
        
        login_button = None
        for btn in buttons:
            btn_text = btn.text.lower().strip()
            btn_class = (btn.get_attribute("class") or "").lower()
            btn_id = (btn.get_attribute("id") or "").lower()
            log_step("8", "ℹ️", f"  Button: text='{btn.text[:20]}', class='{btn_class[:20]}', id='{btn_id[:20]}'")
            
            if "login" in btn_text or "sign" in btn_text or "submit" in btn_text:
                login_button = btn
                log_step("8", "✅", f"Found login button by text: '{btn.text}'")
                break
        
        if not login_button:
            # Try input type submit
            for inp in all_inputs:
                if inp.get_attribute("type") == "submit":
                    login_button = inp
                    log_step("8", "✅", "Found submit input button")
                    break
        
        if not login_button:
            log_step("8", "❌", "Could not find login button")
            driver.save_screenshot("debug_no_button.png")
            return None
        
        login_button.click()
        log_step("8", "✅", "Login button clicked")
        time.sleep(5)
        
        # Check page after login
        post_login_url = driver.current_url
        post_login_title = driver.title
        post_login_source = driver.page_source.lower()
        log_step("9", "✅", f"After login - URL: {post_login_url}, Title: {post_login_title}")
        
        # Check for warning page
        warning_keywords = ["warning", "continue", "proceed", "acknowledge", "accept"]
        for keyword in warning_keywords:
            if keyword in post_login_source:
                log_step("10", "⚠️", f"Warning page detected - contains '{keyword}'")
                
                # Try to find continue button
                continue_buttons = driver.find_elements(By.TAG_NAME, "button")
                for btn in continue_buttons:
                    btn_text = btn.text.lower()
                    if "continue" in btn_text or "proceed" in btn_text or "accept" in btn_text:
                        btn.click()
                        log_step("10", "✅", f"Clicked '{btn.text}' button")
                        time.sleep(3)
                        break
                break
        
        # Get cookies
        cookies = driver.get_cookies()
        log_step("11", "✅", f"Retrieved {len(cookies)} cookies")
        
        for i, cookie in enumerate(cookies[:5]):  # Show first 5 cookies
            log_step("11", "ℹ️", f"  Cookie {i}: name={cookie['name']}, domain={cookie.get('domain', '')}")
        
        # Take a screenshot of final state
        driver.save_screenshot("final_state.png")
        log_step("11", "✅", "Screenshot saved: final_state.png")
        
        # Convert to cookie string
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        return cookie_str
        
    except Exception as e:
        log_step("ERROR", "❌", f"Exception: {type(e).__name__}: {str(e)}")
        try:
            driver.save_screenshot("error_screenshot.png")
            log_step("ERROR", "✅", "Error screenshot saved")
        except:
            pass
        return None
    finally:
        if driver:
            driver.quit()
            log_step("12", "✅", "Browser closed")

def fetch_train_data(cookie_str):
    if not cookie_str:
        return [], "No cookies"
    
    log_step("13", "🔄", "Fetching train data...")
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie_str,
        "Referer": TF_LOGIN_URL
    })
    
    try:
        log_step("13", "🔄", f"GET {TF_URL}")
        r = session.get(TF_URL, timeout=30, allow_redirects=False)
        log_step("13", "✅", f"Response: {r.status_code}, Content-Type: {r.headers.get('content-type', 'unknown')}")
        
        if r.status_code in (301, 302, 303, 307, 308):
            location = r.headers.get("Location", "unknown")
            log_step("13", "⚠️", f"Redirected to: {location}")
            return [], f"Redirected to: {location}"
        
        if "application/json" not in r.headers.get("content-type", "").lower():
            preview = r.text[:200] if r.text else "empty"
            log_step("13", "⚠️", f"Non-JSON response: {preview}")
            return [], "Non-JSON response"
        
        data = r.json()
        log_step("13", "✅", "JSON parsed successfully")
        
        raw_list = extract_list(data)
        log_step("13", "✅", f"Extracted {len(raw_list)} raw train records")
        
        trains = []
        for i, item in enumerate(raw_list):
            train = norm_item(item, i)
            if train and train.get("lat") and train.get("lon"):
                trains.append(train)
        
        log_step("13", "✅", f"Normalized {len(trains)} valid trains")
        return trains, "ok"
        
    except Exception as e:
        log_step("13", "❌", f"Fetch error: {type(e).__name__}: {str(e)}")
        return [], f"Error: {type(e).__name__}"

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
        "id": str(item.get("id") or item.get("ID") or item.get("Name") or f"train_{i}"),
        "lat": to_float(item.get("lat") or item.get("latitude") or item.get("Lat")),
        "lon": to_float(item.get("lon") or item.get("longitude") or item.get("Lon")),
        "operator": item.get("operator") or item.get("Operator") or "",
        "heading": to_float(item.get("heading") or item.get("Heading") or 0)
    }

def main():
    print("=" * 60)
    print(f"🚂 RAILOPS DEBUG RUN - {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    cookie = login_and_get_cookies()
    if not cookie:
        print("❌ LOGIN FAILED - No cookie returned")
        write_output([], "Login failed")
        return
    
    print(f"✅ Cookie obtained (length: {len(cookie)})")
    
    trains, note = fetch_train_data(cookie)
    write_output(trains, note)
    
    print("=" * 60)
    print(f"🏁 Complete: {len(trains)} trains")
    print("=" * 60)

if __name__ == "__main__":
    main()
