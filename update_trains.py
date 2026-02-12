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
    """Complete login flow - FINAL WORKING VERSION"""
    
    print("=" * 60)
    print("🚂 FINAL VERSION - Login button found!")
    print("=" * 60)
    
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
        print("\n📌 Loading login page...")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Step 2: Fill username
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.clear()
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        
        # Step 3: Fill password
        password = driver.find_element(By.ID, "pasS_word")
        password.clear()
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        
        # Step 4: Check Remember Me
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
                print("✅ Remember Me checked")
        except:
            pass
        
        # Step 5: FIND AND CLICK THE LOGIN BUTTON (NOT a <button> element!)
        print("\n🔍 Looking for login button inside table...")
        
        login_script = """
        // Find the table with class containing 'login'
        var tables = document.getElementsByClassName('popup_table');
        for(var i = 0; i < tables.length; i++) {
            if(tables[i].className.includes('login')) {
                // Look for any element that says "Log" or "Login" or "Log In"
                var elements = tables[i].getElementsByTagName('*');
                for(var j = 0; j < elements.length; j++) {
                    var text = elements[j].textContent || '';
                    if(text.trim() === 'Log' || text.trim() === 'Log In' || text.trim() === 'Login') {
                        elements[j].click();
                        return 'Clicked login button with text: ' + text.trim();
                    }
                }
                break;
            }
        }
        
        // Alternative: Find by class containing 'login_pa'
        var loginElements = document.querySelectorAll('.login_pa, .login_pa *');
        for(var i = 0; i < loginElements.length; i++) {
            var text = loginElements[i].textContent || '';
            if(text.trim() === 'Log' || text.trim() === 'Log In' || text.trim() === 'Login') {
                loginElements[i].click();
                return 'Clicked login button via class: ' + text.trim();
            }
        }
        
        return 'Login button not found';
        """
        
        result = driver.execute_script(login_script)
        print(f"✅ {result}")
        
        # Step 6: Wait for login and warning page
        print("\n⏳ Waiting for login and warning page...")
        time.sleep(8)
        
        # Step 7: Close warning page (we know this works)
        print("🔍 Closing warning page...")
        close_script = """
        var paths = document.getElementsByTagName('path');
        for(var i = 0; i < paths.length; i++) {
            var d = paths[i].getAttribute('d') || '';
            if(d.includes('M13.7,11l6.1-6.1')) {
                var parent = paths[i].parentElement;
                while(parent && parent.tagName !== 'BUTTON' && parent.tagName !== 'DIV' && parent.tagName !== 'A') {
                    parent = parent.parentElement;
                }
                if(parent) {
                    parent.click();
                    return 'Warning page closed';
                }
            }
        }
        return 'No close button found';
        """
        close_result = driver.execute_script(close_script)
        print(f"✅ {close_result}")
        
        # Step 8: Wait for map
        print("\n⏳ Waiting for map to load...")
        time.sleep(5)
        
        # Step 9: Fetch train data
        print("\n📡 Fetching train data...")
        driver.get(TF_URL)
        time.sleep(3)
        
        response = driver.page_source
        print(f"📄 Response length: {len(response)} characters")
        
        if response.strip().startswith(("{", "[")):
            print("✅ SUCCESS! Received JSON data")
            
            try:
                data = json.loads(response)
                raw_list = extract_list(data)
                
                trains = []
                for i, item in enumerate(raw_list):
                    train = norm_item(item, i)
                    if train and train.get("lat") and train.get("lon"):
                        trains.append(train)
                
                print(f"✅ Extracted {len(trains)} trains")
                driver.save_screenshot("success.png")
                print("📸 Success screenshot saved")
                
                return trains, "ok"
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse error: {e}")
                return [], "JSON parse error"
        else:
            print("❌ Response is not JSON - still not authenticated")
            print(f"Preview: {response[:200]}")
            return [], "Not authenticated"
        
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
            print("\n✅ Browser closed")

def main():
    print("=" * 60)
    print("🚂🚂🚂 TRAIN TRACKER - FINAL WORKING VERSION 🚂🚂🚂")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = login_and_get_trains()
    write_output(trains, note)
    
    print("\n" + "=" * 60)
    print(f"🏁 Complete: {len(trains)} trains")
    print(f"📝 Status: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
