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

def find_api_endpoint():
    """Login and capture the real API endpoint from network traffic"""
    
    print("=" * 60)
    print("🔍 FINDING THE REAL API ENDPOINT")
    print("=" * 60)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Enable performance logging to capture network requests
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
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
        
        # Step 5: Click login button (we know this works!)
        print("\n🔍 Clicking login button...")
        login_script = """
        var tables = document.getElementsByClassName('popup_table');
        for(var i = 0; i < tables.length; i++) {
            if(tables[i].className.includes('login')) {
                var elements = tables[i].getElementsByTagName('*');
                for(var j = 0; j < elements.length; j++) {
                    var text = elements[j].textContent || '';
                    if(text.trim() === 'Log In' || text.trim() === 'Log' || text.trim() === 'Login') {
                        elements[j].click();
                        return 'Clicked: ' + text.trim();
                    }
                }
                break;
            }
        }
        return 'Button not found';
        """
        result = driver.execute_script(login_script)
        print(f"✅ {result}")
        
        # Step 6: Wait for login and warning page
        time.sleep(8)
        
        # Step 7: Close warning page
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
        
        # Step 8: Wait for map to load
        time.sleep(5)
        
        # Step 9: Capture all network requests from the performance logs
        print("\n📡 Capturing network requests...")
        logs = driver.get_log('performance')
        
        api_endpoints = []
        for log in logs:
            try:
                import json
                message = json.loads(log['message'])['message']
                
                # Look for XHR/fetch requests
                if message['method'] == 'Network.responseReceived':
                    url = message['params']['response']['url']
                    # Look for train data endpoints
                    if 'GetViewPortData' in url or 'trains' in url.lower() or 'markers' in url.lower():
                        api_endpoints.append(url)
                        print(f"   🔗 Found: {url}")
            except:
                pass
        
        # Step 10: Try each found endpoint
        print("\n🔍 Testing found endpoints...")
        for endpoint in api_endpoints[:5]:  # Test first 5
            print(f"\n   Testing: {endpoint}")
            driver.get(endpoint)
            time.sleep(2)
            response = driver.page_source
            if response.strip().startswith(("{", "[")):
                print(f"   ✅ SUCCESS! JSON data found at: {endpoint}")
                try:
                    data = json.loads(response)
                    raw_list = extract_list(data)
                    trains = []
                    for i, item in enumerate(raw_list):
                        train = norm_item(item, i)
                        if train and train.get("lat") and train.get("lon"):
                            trains.append(train)
                    print(f"   ✅ Extracted {len(trains)} trains")
                    return trains, endpoint
                except:
                    pass
            else:
                print(f"   ❌ Not JSON")
        
        # Step 11: If no endpoints found, try to get the current page URL
        current_url = driver.current_url
        print(f"\n📍 Current page URL: {current_url}")
        
        # Step 12: Save the page source for inspection
        page_source = driver.page_source
        with open("debug_page_after_login.html", "w") as f:
            f.write(page_source[:10000])
        print("\n📄 Saved page source to debug_page_after_login.html")
        
        return [], "No API endpoint found"
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        return [], f"Error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()
            print("\n✅ Browser closed")

def main():
    print("=" * 60)
    print("🚂🚂🚂 FINDING THE REAL API ENDPOINT 🚂🚂🚂")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = find_api_endpoint()
    write_output(trains, note)
    
    print("\n" + "=" * 60)
    print(f"🏁 Complete: {len(trains)} trains")
    print(f"📝 API Endpoint: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
