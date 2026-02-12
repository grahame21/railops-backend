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
        for k in ["trains", "Trains", "markers", "Markers", "features", "data", "Data"]:
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
        "lat": to_float(item.get("lat") or item.get("latitude") or item.get("Lat")),
        "lon": to_float(item.get("lon") or item.get("longitude") or item.get("Lon")),
        "operator": item.get("operator") or item.get("Operator") or "",
        "heading": to_float(item.get("heading") or item.get("Heading") or 0)
    }

def login_and_get_trains():
    """Complete login flow with multiple API endpoint attempts"""
    
    print("=" * 60)
    print("🚂 FINAL VERSION - Multiple API Endpoint Attempts")
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
        
        # Step 8: Try multiple API endpoints
        print("\n📡 Attempting multiple API endpoints...")
        
        api_endpoints = [
            # GET requests
            {"method": "GET", "url": "https://trainfinder.otenko.com/Home/GetViewPortData"},
            {"method": "GET", "url": "https://trainfinder.otenko.com/Home/GetTrains"},
            {"method": "GET", "url": "https://trainfinder.otenko.com/Home/GetMarkers"},
            {"method": "GET", "url": "https://trainfinder.otenko.com/api/trains"},
            {"method": "GET", "url": "https://trainfinder.otenko.com/api/locations"},
            {"method": "GET", "url": "https://trainfinder.otenko.com/Home/GetData"},
            
            # POST requests
            {"method": "POST", "url": "https://trainfinder.otenko.com/Home/GetViewPortData", "body": {}},
            {"method": "POST", "url": "https://trainfinder.otenko.com/Home/GetTrains", "body": {}},
            {"method": "POST", "url": "https://trainfinder.otenko.com/api/trains", "body": {}},
        ]
        
        for endpoint in api_endpoints:
            print(f"\n   🔄 Trying: {endpoint['method']} {endpoint['url']}")
            
            if endpoint['method'] == 'GET':
                script = f"""
                return fetch('{endpoint['url']}', {{
                    method: 'GET',
                    headers: {{
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Referer': '{TF_LOGIN_URL}'
                    }},
                    credentials: 'include'
                }})
                .then(response => response.text())
                .then(text => {{
                    try {{
                        JSON.parse(text);
                        return {{success: true, data: text, url: '{endpoint['url']}'}};
                    }} catch(e) {{
                        return {{success: false, data: text.substring(0, 100), url: '{endpoint['url']}'}};
                    }}
                }})
                .catch(error => {{
                    return {{success: false, error: error.toString(), url: '{endpoint['url']}'}};
                }});
                """
            else:  # POST
                script = f"""
                return fetch('{endpoint['url']}', {{
                    method: 'POST',
                    headers: {{
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Referer': '{TF_LOGIN_URL}'
                    }},
                    credentials: 'include',
                    body: '{{}}'
                }})
                .then(response => response.text())
                .then(text => {{
                    try {{
                        JSON.parse(text);
                        return {{success: true, data: text, url: '{endpoint['url']}'}};
                    }} catch(e) {{
                        return {{success: false, data: text.substring(0, 100), url: '{endpoint['url']}'}};
                    }}
                }})
                .catch(error => {{
                    return {{success: false, error: error.toString(), url: '{endpoint['url']}'}};
                }});
                """
            
            result = driver.execute_script(script)
            
            if result.get('success'):
                print(f"   ✅ SUCCESS! Found working endpoint: {result['url']}")
                try:
                    data = json.loads(result['data'])
                    raw_list = extract_list(data)
                    
                    trains = []
                    for i, item in enumerate(raw_list):
                        train = norm_item(item, i)
                        if train and train.get("lat") and train.get("lon"):
                            trains.append(train)
                    
                    print(f"   ✅ Extracted {len(trains)} trains")
                    
                    # Save the working URL for future use
                    with open('working_endpoint.txt', 'w') as f:
                        f.write(f"{endpoint['method']} {result['url']}")
                    
                    return trains, f"ok - {result['url']}"
                    
                except json.JSONDecodeError as e:
                    print(f"   ❌ JSON parse error: {e}")
                    continue
            else:
                print(f"   ❌ Failed: {result.get('data', result.get('error', 'Unknown'))[:100]}")
        
        print("\n❌ No working API endpoint found")
        
        # Step 9: As a last resort, try to extract data from the page itself
        print("\n🔍 Attempting to extract data from page source...")
        page_source = driver.page_source
        
        # Look for any JSON-like data in the page
        import re
        json_pattern = r'(\{.*"trains".*\})'
        matches = re.findall(json_pattern, page_source)
        
        if matches:
            print(f"   Found potential JSON in page, trying to parse...")
            for match in matches[:5]:
                try:
                    data = json.loads(match)
                    raw_list = extract_list(data)
                    if raw_list:
                        trains = []
                        for i, item in enumerate(raw_list):
                            train = norm_item(item, i)
                            if train and train.get("lat") and train.get("lon"):
                                trains.append(train)
                        if trains:
                            print(f"   ✅ Extracted {len(trains)} trains from page source")
                            return trains, "ok - extracted from page"
                except:
                    continue
        
        return [], "No working API endpoint found"
        
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
    print("🚂🚂🚂 TRAIN TRACKER - FINAL MULTI-ENDPOINT VERSION 🚂🚂🚂")
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
