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

def login_and_get_session():
    """Complete login flow with warning page handling"""
    
    print("🔄 Starting complete login flow...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Step 1: Load the login/map page
        print(f"🔄 Loading page: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)  # Wait for JavaScript to render
        
        # Step 2: Find and fill username field
        try:
            username = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            print("✅ Found username field")
            username.clear()
            username.send_keys(TF_USERNAME)
            print("✅ Username entered")
        except Exception as e:
            print(f"❌ Could not find username field: {str(e)}")
            driver.save_screenshot("debug_no_username.png")
            return None
        
        # Step 3: Find and fill password field
        try:
            password = driver.find_element(By.ID, "pasS_word")
            print("✅ Found password field")
            password.clear()
            password.send_keys(TF_PASSWORD)
            print("✅ Password entered")
        except Exception as e:
            print(f"❌ Could not find password field: {str(e)}")
            driver.save_screenshot("debug_no_password.png")
            return None
        
        # Step 4: Find the "Remember Me" checkbox and check it (optional)
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
                print("✅ Checked Remember Me")
        except:
            print("⚠️ Could not find Remember Me checkbox")
        
        # Step 5: Find and click the LOGIN BUTTON
        # IMPORTANT: The login button is NOT a button element!
        # It might be an input type="submit" or a styled div
        print("🔍 Looking for login button...")
        
        login_button = None
        
        # Method 1: Look for input type="submit"
        submit_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='submit']")
        for inp in submit_inputs:
            value = inp.get_attribute("value") or ""
            if "log in" in value.lower() or "login" in value.lower():
                login_button = inp
                print(f"✅ Found submit button with value: '{value}'")
                break
        
        # Method 2: Look for button with text
        if not login_button:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                btn_text = btn.text.strip()
                if "log in" in btn_text.lower() or "login" in btn_text.lower():
                    login_button = btn
                    print(f"✅ Found button with text: '{btn_text}'")
                    break
        
        # Method 3: Look for any element with onclick or submit functionality
        if not login_button:
            # Try to find the form and submit it directly
            forms = driver.find_elements(By.TAG_NAME, "form")
            if forms:
                print(f"✅ Found {len(forms)} form(s), submitting the first one")
                driver.execute_script("arguments[0].submit();", forms[0])
                login_button = "form_submit"
                print("✅ Form submitted via JavaScript")
        
        if login_button and login_button != "form_submit":
            try:
                login_button.click()
                print("✅ Login button clicked")
            except:
                driver.execute_script("arguments[0].click();", login_button)
                print("✅ Login button clicked via JavaScript")
        
        # Wait for login to process and warning page to appear
        print("⏳ Waiting for warning page...")
        time.sleep(5)
        
        # Step 6: Handle the warning page - click the X/Close button
        print("🔍 Looking for warning page close button...")
        
        # Method 1: Look for SVG path with the specific d attribute
        svg_paths = driver.find_elements(By.TAG_NAME, "path")
        for path in svg_paths:
            d_attr = path.get_attribute("d") or ""
            if "M13.7,11l6.1-6.1" in d_attr or "close" in d_attr.lower():
                try:
                    path.click()
                    print("✅ Clicked warning page close button (SVG path)")
                    break
                except:
                    try:
                        driver.execute_script("arguments[0].click();", path)
                        print("✅ Clicked warning page close button via JavaScript")
                        break
                    except:
                        pass
        
        # Method 2: Look for any close/dismiss button
        if not svg_paths:
            close_buttons = driver.find_elements(By.CSS_SELECTOR, ".close, .dismiss, .btn-close, [aria-label='Close']")
            for btn in close_buttons:
                btn.click()
                print("✅ Clicked close button")
                break
        
        # Wait for map to load
        print("⏳ Waiting for map to load...")
        time.sleep(5)
        
        # Step 7: Get cookies and session data
        cookies = driver.get_cookies()
        print(f"✅ Got {len(cookies)} cookies")
        
        # Convert cookies to string
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        # Step 8: Try to access the API directly
        print(f"🔄 Attempting to fetch train data...")
        driver.get(TF_URL)
        time.sleep(2)
        
        page_source = driver.page_source
        if page_source.strip().startswith(("{", "[")):
            print("✅ Successfully accessed train data API!")
            try:
                import json
                data = json.loads(page_source)
                raw_list = extract_list(data)
                trains = []
                for i, item in enumerate(raw_list):
                    train = norm_item(item, i)
                    if train and train.get("lat") and train.get("lon"):
                        trains.append(train)
                
                # Save screenshot of success
                driver.save_screenshot("login_success.png")
                print("📸 Success screenshot saved")
                
                return trains, "ok"
            except:
                pass
        
        return [], "Login flow completed but no train data"
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        try:
            driver.save_screenshot("error.png")
            print("📸 Error screenshot saved")
        except:
            pass
        return [], f"Error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()
            print("✅ Browser closed")

def main():
    print("=" * 60)
    print(f"🚂 COMPLETE LOGIN FLOW - With Warning Page Handling")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = login_and_get_session()
    write_output(trains, note)
    
    print(f"\n🏁 Complete: {len(trains)} trains")
    print(f"📝 Status: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
