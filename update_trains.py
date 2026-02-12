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
        "id": str(item.get("id") or item.get("ID") or item.get("trainId") or f"train_{i}"),
        "lat": to_float(item.get("lat") or item.get("latitude") or item.get("Lat")),
        "lon": to_float(item.get("lon") or item.get("longitude") or item.get("Lon")),
        "operator": item.get("operator") or item.get("Operator") or "",
        "heading": to_float(item.get("heading") or item.get("Heading") or 0),
        "speed": to_float(item.get("speed") or item.get("Speed") or 0)
    }

def capture_real_api_endpoint():
    """Capture the ACTUAL API endpoint the website uses"""
    
    print("=" * 60)
    print("🔍 CAPTURING REAL API ENDPOINT")
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
        
        # Login
        print("\n📌 Logging in...")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Fill credentials
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.send_keys(TF_USERNAME)
        
        password = driver.find_element(By.ID, "pasS_word")
        password.send_keys(TF_PASSWORD)
        
        # Click login
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
        
        time.sleep(8)
        
        # Close warning
        driver.execute_script("""
            var paths = document.getElementsByTagName('path');
            for(var i = 0; i < paths.length; i++) {
                var d = paths[i].getAttribute('d') || '';
                if(d.includes('M13.7,11l6.1-6.1')) {
                    var parent = paths[i].parentElement;
                    while(parent && parent.tagName !== 'BUTTON' && parent.tagName !== 'DIV' && parent.tagName !== 'A') {
                        parent = parent.parentElement;
                    }
                    if(parent) parent.click();
                }
            }
        """)
        
        time.sleep(5)
        
        # Clear logs before capturing
        driver.get_log('performance')
        
        # Refresh the page to trigger all network requests
        print("\n🔄 Refreshing page to capture network requests...")
        driver.refresh()
        time.sleep(10)
        
        # Get all network logs
        print("\n📡 Capturing network requests...")
        logs = driver.get_log('performance')
        
        api_calls = []
        json_calls = []
        
        for log in logs:
            try:
                message = json.loads(log['message'])['message']
                
                # Look for XHR/fetch requests
                if message['method'] == 'Network.responseReceived':
                    url = message['params']['response']['url']
                    
                    # Filter for relevant endpoints
                    if 'train' in url.lower() or 'marker' in url.lower() or 'get' in url.lower():
                        api_calls.append(url)
                        print(f"\n   🔗 Found: {url}")
                        
                    # Check if it returned JSON
                    content_type = message['params']['response'].get('mimeType', '')
                    if 'json' in content_type.lower():
                        json_calls.append(url)
                        print(f"   ✅ JSON endpoint: {url}")
                        
            except:
                continue
        
        # Try all found endpoints
        print("\n🔍 Testing found endpoints...")
        
        for endpoint in list(dict.fromkeys(api_calls))[:10]:  # Unique URLs, limit to 10
            print(f"\n   Testing: {endpoint}")
            
            script = f"""
            return fetch('{endpoint}', {{
                method: 'GET',
                headers: {{
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }},
                credentials: 'include'
            }})
            .then(response => response.text())
            .then(text => {{
                try {{
                    var data = JSON.parse(text);
                    var count = Array.isArray(data) ? data.length : 
                               (data.trains ? data.trains.length : 
                               (data.features ? data.features.length : 0));
                    return {{success: true, url: '{endpoint}', count: count, preview: text.substring(0, 100)}};
                }} catch(e) {{
                    return {{success: false, url: '{endpoint}'}};
                }}
            }})
            .catch(error => {{
                return {{success: false, url: '{endpoint}', error: error.toString()}};
            }});
            """
            
            result = driver.execute_script(script)
            
            if result.get('success'):
                print(f"   ✅ WORKS! Found {result.get('count', 0)} items")
                print(f"   📊 Preview: {result.get('preview', '')}")
                
                # If this endpoint has trains, save them!
                if result.get('count', 0) > 0:
                    print(f"\n🎉 SUCCESS! Found endpoint with {result['count']} trains!")
                    try:
                        data = json.loads(result['preview']) if result['count'] > 0 else {}
                        # Actually fetch the full data
                        full_data = driver.execute_script(f"""
                            return fetch('{endpoint}').then(r => r.text());
                        """)
                        data = json.loads(full_data)
                        raw_list = extract_list(data)
                        trains = []
                        for i, item in enumerate(raw_list):
                            train = norm_item(item, i)
                            if train and train.get("lat") and train.get("lon"):
                                trains.append(train)
                        return trains, f"ok - {endpoint}"
                    except:
                        pass
            else:
                print(f"   ❌ Failed")
        
        return [], "No working endpoint found"
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        return [], f"Error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()
            print("\n✅ Browser closed")

def main():
    print("=" * 60)
    print("🚂 FINDING THE REAL TRAIN API")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = capture_real_api_endpoint()
    write_output(trains, note)
    
    print("\n" + "=" * 60)
    print(f"🏁 Complete: {len(trains)} trains")
    print(f"📝 API Endpoint: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
