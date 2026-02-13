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

def login_and_capture_network():
    """Capture ALL network requests to find the real data source"""
    
    print("=" * 60)
    print("🚂 RAILOPS - NETWORK CAPTURE MODE")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    # Enable performance logging
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # STEP 1: LOGIN
        print("\n📌 Logging in...")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Fill username
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        
        # Fill password
        password = driver.find_element(By.ID, "pasS_word")
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        
        # Remember Me
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
                print("✅ Remember Me checked")
        except:
            pass
        
        # Click login button
        driver.execute_script("""
            var tables = document.getElementsByClassName('popup_table');
            for(var i = 0; i < tables.length; i++) {
                if(tables[i].className.includes('login')) {
                    var elements = tables[i].getElementsByTagName('*');
                    for(var j = 0; j < elements.length; j++) {
                        if(elements[j].textContent.trim() === 'Log In') {
                            elements[j].click();
                            return;
                        }
                    }
                }
            }
        """)
        print("✅ Login button clicked")
        
        # Wait for login and warning
        time.sleep(8)
        
        # Close warning page
        driver.execute_script("""
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
                        return;
                    }
                }
            }
        """)
        print("✅ Warning page closed")
        
        # Wait for map to load
        print("\n⏳ Loading map...")
        time.sleep(10)
        
        # Clear logs before capturing
        driver.get_log('performance')
        
        # Wait a bit more to capture all requests
        time.sleep(5)
        
        # STEP 2: CAPTURE ALL NETWORK REQUESTS
        print("\n📡 Capturing network requests...")
        logs = driver.get_log('performance')
        
        api_calls = []
        json_responses = []
        
        for log in logs:
            try:
                message = json.loads(log['message'])['message']
                
                # Look for network responses
                if message['method'] == 'Network.responseReceived':
                    url = message['params']['response']['url']
                    mime_type = message['params']['response'].get('mimeType', '')
                    
                    # Look for API/train data endpoints
                    if any(x in url.lower() for x in ['api', 'train', 'marker', 'data', 'get']):
                        if 'json' in mime_type.lower() or 'javascript' in mime_type.lower():
                            api_calls.append({
                                'url': url,
                                'mime_type': mime_type,
                                'status': message['params']['response']['status']
                            })
                            print(f"\n   🔗 Found API endpoint: {url}")
                            print(f"      Status: {message['params']['response']['status']}")
                            print(f"      Type: {mime_type}")
                
                # Try to get response body
                if message['method'] == 'Network.responseReceived' and 'requestId' in message['params']:
                    request_id = message['params']['requestId']
                    try:
                        response = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                        body = response.get('body', '')
                        
                        # Check if it's JSON and contains train data
                        if body.strip().startswith(('{', '[')):
                            try:
                                data = json.loads(body)
                                # Look for train-related data
                                if any(x in str(data).lower() for x in ['lat', 'lon', 'train', 'marker']):
                                    json_responses.append({
                                        'url': url,
                                        'data': data,
                                        'size': len(body)
                                    })
                                    print(f"      ✅ Contains JSON data ({len(body)} bytes)")
                            except:
                                pass
                    except:
                        pass
                        
            except Exception as e:
                continue
        
        print(f"\n📊 Found {len(api_calls)} potential API endpoints")
        print(f"📊 Found {len(json_responses)} JSON responses with train data")
        
        # STEP 3: EXTRACT TRAINS FROM THE RESPONSES
        all_trains = []
        train_ids = set()
        
        for response in json_responses:
            data = response['data']
            url = response['url']
            
            # Try to extract trains from various JSON structures
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        lat = item.get('lat') or item.get('latitude') or item.get('Lat') or item.get('y')
                        lon = item.get('lon') or item.get('longitude') or item.get('Lon') or item.get('x')
                        if lat and lon:
                            train = {
                                'id': str(item.get('id') or item.get('ID') or item.get('name') or f"train_{len(all_trains)}"),
                                'lat': float(lat),
                                'lon': float(lon),
                                'heading': float(item.get('heading') or item.get('Heading') or 0),
                                'speed': float(item.get('speed') or item.get('Speed') or 0),
                                'operator': item.get('operator') or item.get('Operator') or '',
                                'service': item.get('service') or item.get('Service') or item.get('trainNumber') or ''
                            }
                            if train['id'] not in train_ids:
                                train_ids.add(train['id'])
                                all_trains.append(train)
            
            elif isinstance(data, dict):
                # Check common container keys
                for key in ['trains', 'Train', 'markers', 'features', 'data', 'results']:
                    items = data.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                lat = item.get('lat') or item.get('latitude') or item.get('Lat') or item.get('y')
                                lon = item.get('lon') or item.get('longitude') or item.get('Lon') or item.get('x')
                                if lat and lon:
                                    train = {
                                        'id': str(item.get('id') or item.get('ID') or item.get('name') or f"train_{len(all_trains)}"),
                                        'lat': float(lat),
                                        'lon': float(lon),
                                        'heading': float(item.get('heading') or item.get('Heading') or 0),
                                        'speed': float(item.get('speed') or item.get('Speed') or 0),
                                        'operator': item.get('operator') or item.get('Operator') or '',
                                        'service': item.get('service') or item.get('Service') or item.get('trainNumber') or ''
                                    }
                                    if train['id'] not in train_ids:
                                        train_ids.add(train['id'])
                                        all_trains.append(train)
        
        print(f"\n✅ Extracted {len(all_trains)} trains from network responses")
        
        # Save the found endpoints to a file for future use
        with open('found_endpoints.json', 'w') as f:
            json.dump(api_calls, f, indent=2)
        print("📝 Saved found endpoints to found_endpoints.json")
        
        return all_trains, f"ok - {len(all_trains)} trains from network"
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return [], f"Error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()
            print("\n✅ Browser closed")

def main():
    print("=" * 60)
    print("🚂🚂🚂 RAILOPS - NETWORK CAPTURE 🚂🚂🚂")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = login_and_capture_network()
    write_output(trains, note)
    
    print("\n" + "=" * 60)
    print(f"🏁 Complete: {len(trains)} trains")
    print(f"📝 Status: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
