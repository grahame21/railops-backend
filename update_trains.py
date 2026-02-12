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

def login_and_get_trains():
    """Complete login flow with fixed SVG click handling"""
    
    print("🔄 Starting login flow...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Step 1: Load the page
        print(f"🔄 Loading page: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Step 2: Find and fill username
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.clear()
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        
        # Step 3: Find and fill password
        password = driver.find_element(By.ID, "pasS_word")
        password.clear()
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        
        # Step 4: Check Remember Me
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
                print("✅ Checked Remember Me")
        except:
            print("⚠️ Remember Me checkbox not found")
        
        # Step 5: Trigger login via JavaScript
        print("🔍 Triggering login...")
        
        login_script = """
        // Find and click the login button
        var loginButton = null;
        
        // Try to find by text
        var buttons = document.getElementsByTagName('button');
        for(var i = 0; i < buttons.length; i++) {
            if(buttons[i].textContent.trim().toLowerCase().includes('log in')) {
                loginButton = buttons[i];
                break;
            }
        }
        
        if(loginButton) {
            loginButton.click();
            return 'Login button clicked';
        }
        
        return 'No login button found';
        """
        
        result = driver.execute_script(login_script)
        print(f"✅ {result}")
        
        # Wait for login and warning page
        print("⏳ Waiting for login to process...")
        time.sleep(8)
        
        # Step 6: Close warning page - FIXED VERSION
        print("🔍 Looking for warning page close button...")
        
        # METHOD 1: Find the parent element of the SVG and click it
        close_script = """
        // Find the close button (parent of the SVG path)
        var closeButton = null;
        
        // Look for SVG path with the close icon
        var paths = document.getElementsByTagName('path');
        for(var i = 0; i < paths.length; i++) {
            var d = paths[i].getAttribute('d') || '';
            if(d.includes('M13.7,11l6.1-6.1')) {
                // Click the parent element (usually a button or div)
                var parent = paths[i].parentElement;
                while(parent && parent.tagName !== 'BUTTON' && parent.tagName !== 'DIV' && parent.tagName !== 'A') {
                    parent = parent.parentElement;
                }
                if(parent) {
                    parent.click();
                    return 'Close button clicked via parent';
                }
            }
        }
        
        // METHOD 2: Look for any element with class containing 'close'
        var closeElements = document.querySelectorAll('.close, .btn-close, [aria-label="Close"]');
        if(closeElements.length > 0) {
            closeElements[0].click();
            return 'Close button clicked via class';
        }
        
        return 'No close button found';
        """
        
        close_result = driver.execute_script(close_script)
        print(f"✅ {close_result}")
        
        # Wait for map to load
        print("⏳ Waiting for map to load...")
        time.sleep(5)
        
        # Step 7: Fetch train data directly
        print(f"🔄 Fetching train data from API...")
        driver.get(TF_URL)
        time.sleep(3)
        
        # Get the response
        page_source = driver.page_source
        print(f"📄 Response length: {len(page_source)} characters")
        
        # Check if we got JSON
        if page_source.strip().startswith(("{", "[")):
            print("✅ Successfully received JSON data!")
            
            try:
                data = json.loads(page_source)
                raw_list = extract_list(data)
                
                trains = []
                for i, item in enumerate(raw_list):
                    train = norm_item(item, i)
                    if train and train.get("lat") and train.get("lon"):
                        trains.append(train)
                
                print(f"✅ Extracted {len(trains)} trains")
                return trains, "ok"
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse error: {str(e)}")
                return [], "JSON parse error"
        else:
            print("⚠️ Response is not JSON")
            return [], "Non-JSON response"
        
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
    print(f"🚂 FINAL FIXED VERSION - SVG Click Fixed")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = login_and_get_trains()
    write_output(trains, note)
    
    print(f"\n🏁 Complete: {len(trains)} trains")
    print(f"📝 Status: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
