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
    """AJAX login - trigger login via JavaScript events"""
    
    print("🔄 Starting AJAX login flow...")
    
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
        
        # Step 5: TRIGGER LOGIN VIA JAVASCRIPT
        # The login button likely triggers an AJAX call
        print("🔍 Triggering login via JavaScript...")
        
        login_script = """
        // Find the login button or trigger the login event
        var usernameField = document.getElementById('useR_name');
        var passwordField = document.getElementById('pasS_word');
        
        // Trigger change events
        usernameField.dispatchEvent(new Event('change', { bubbles: true }));
        passwordField.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Find and click the login element
        var loginButton = null;
        
        // Try to find by text
        var buttons = document.getElementsByTagName('button');
        for(var i = 0; i < buttons.length; i++) {
            if(buttons[i].textContent.trim().toLowerCase().includes('log in')) {
                loginButton = buttons[i];
                break;
            }
        }
        
        // If no button found, try to find by class or role
        if(!loginButton) {
            loginButton = document.querySelector('[type="submit"], .btn-login, .login-button');
        }
        
        // If found, click it
        if(loginButton) {
            loginButton.click();
            return 'Login button clicked';
        } else {
            // Last resort: try to submit the login via AJAX
            // You may need to adjust this based on the actual API endpoint
            fetch('https://trainfinder.otenko.com/Account/Login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: arguments[0],
                    password: arguments[1]
                })
            });
            return 'AJAX login attempted';
        }
        """
        
        result = driver.execute_script(login_script, TF_USERNAME, TF_PASSWORD)
        print(f"✅ {result}")
        
        # Wait for login and warning page
        print("⏳ Waiting for login to process...")
        time.sleep(8)
        
        # Step 6: Close warning page
        print("🔍 Looking for warning page close button...")
        
        close_script = """
        // Find and click the close button
        var closeButton = null;
        
        // Look for SVG path with the close icon
        var paths = document.getElementsByTagName('path');
        for(var i = 0; i < paths.length; i++) {
            var d = paths[i].getAttribute('d') || '';
            if(d.includes('M13.7,11l6.1-6.1')) {
                paths[i].click();
                return 'Close button clicked via path';
            }
        }
        
        // Look for close buttons by class
        closeButton = document.querySelector('.close, .btn-close, [aria-label="Close"]');
        if(closeButton) {
            closeButton.click();
            return 'Close button clicked via selector';
        }
        
        return 'No close button found';
        """
        
        close_result = driver.execute_script(close_script)
        print(f"✅ {close_result}")
        
        # Wait for map
        print("⏳ Waiting for map to load...")
        time.sleep(5)
        
        # Step 7: Fetch train data
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
                # Save the response for debugging
                with open("debug_response.json", "w") as f:
                    f.write(page_source[:5000])
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
    print(f"🚂 AJAX LOGIN - Final Version")
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
