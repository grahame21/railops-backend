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
    """Complete login flow with proper AJAX request - FIXED"""
    
    print("=" * 60)
    print("🚂 FINAL VERSION - Direct AJAX Request (FIXED)")
    print("=" * 60)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Set up logging preferences
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Step 1: Load the page
        print("\n📌 Loading login page...")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Step 2: Fill credentials
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.clear()
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        
        password = driver.find_element(By.ID, "pasS_word")
        password.clear()
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        
        # Step 3: Remember Me
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
                print("✅ Remember Me checked")
        except:
            pass
        
        # Step 4: Click login button
        print("\n🔍 Clicking login button...")
        login_script = """
        var tables = document.getElementsByClassName('popup_table');
        for(var i = 0; i < tables.length; i++) {
            if(tables[i].className.includes('login')) {
                var elements = tables[i].getElementsByTagName('*');
                for(var j = 0; j < elements.length; j++) {
                    var text = elements[j].textContent || '';
                    if(text.trim() === 'Log In') {
                        elements[j].click();
                        return 'Clicked Log In';
                    }
                }
                break;
            }
        }
        return 'Button not found';
        """
        result = driver.execute_script(login_script)
        print(f"✅ {result}")
        
        # Step 5: Wait for login and warning
        time.sleep(8)
        
        # Step 6: Close warning
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
                    return 'Warning closed';
                }
            }
        }
        return 'No close button';
        """
        close_result = driver.execute_script(close_script)
        print(f"✅ {close_result}")
        
        # Step 7: Wait for map
        time.sleep(5)
        
        # Step 8: Make AJAX request for train data
        print("\n📡 Making AJAX request for train data...")
        
        ajax_script = """
        // Make the same request the website makes
        return fetch('https://trainfinder.otenko.com/Home/GetViewPortData', {
            method: 'GET',
            headers: {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': 'https://trainfinder.otenko.com/home/nextlevel'
            },
            credentials: 'include'
        })
        .then(response => response.text())
        .then(text => {
            // Check if it's JSON
            try {
                JSON.parse(text);
                return {success: true, data: text, length: text.length};
            } catch(e) {
                return {success: false, data: text.substring(0, 200), length: text.length};
            }
        })
        .catch(error => {
            return {success: false, error: error.toString()};
        });
        """
        
        result = driver.execute_script(ajax_script)
        
        if result.get('success'):
            print(f"✅ SUCCESS! Received JSON data ({result.get('length', 0)} bytes)")
            try:
                data = json.loads(result['data'])
                raw_list = extract_list(data)
                
                trains = []
                for i, item in enumerate(raw_list):
                    train = norm_item(item, i)
                    if train and train.get("lat") and train.get("lon"):
                        trains.append(train)
                
                print(f"✅ Extracted {len(trains)} trains")
                
                # Save a sample of the data for verification
                if trains:
                    print(f"\n📊 Sample train:")
                    print(f"   ID: {trains[0].get('id')}")
                    print(f"   Location: {trains[0].get('lat')}, {trains[0].get('lon')}")
                    print(f"   Heading: {trains[0].get('heading')}")
                
                driver.save_screenshot("success.png")
                print("📸 Success screenshot saved")
                
                return trains, "ok"
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse error: {e}")
                return [], "JSON parse error"
        else:
            print(f"❌ Request failed - received {result.get('length', 0)} bytes")
            print(f"   Preview: {result.get('data', result.get('error', 'Unknown'))[:200]}")
            
            # If we got HTML, save it for debugging
            if result.get('data', '').strip().startswith('<'):
                with open('debug_response.html', 'w') as f:
                    f.write(result['data'])
                print("📄 Saved HTML response to debug_response.html")
            
            return [], "API request failed"
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
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
    print("🚂🚂🚂 TRAIN TRACKER - FINAL FIXED VERSION 🚂🚂🚂")
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
