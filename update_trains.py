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
TF_API_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"  # THIS IS THE REAL ONE!

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

def login_and_get_trains():
    """Production version using the REAL API endpoint"""
    
    print("=" * 60)
    print("🚂 PRODUCTION SCRAPER - REAL ENDPOINT")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
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
        
        # Wait for map
        time.sleep(5)
        
        # STEP 2: FETCH TRAIN DATA
        print(f"\n📡 Fetching train data from: {TF_API_URL}")
        
        script = f"""
        return fetch('{TF_API_URL}', {{
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
                var data = JSON.parse(text);
                // Check if data has trains array
                var trains = data.trains || data.Trains || data.markers || data.Markers || data.features || data;
                var count = Array.isArray(trains) ? trains.length : 
                           (trains ? Object.keys(trains).length : 0);
                return {{success: true, data: text, count: count}};
            }} catch(e) {{
                return {{success: false, data: text.substring(0, 200)}};
            }}
        }})
        .catch(error => {{
            return {{success: false, error: error.toString()}};
        }});
        """
        
        result = driver.execute_script(script)
        
        if result.get('success'):
            count = result.get('count', 0)
            print(f"✅ SUCCESS! Received JSON with {count} train records")
            
            try:
                data = json.loads(result['data'])
                raw_list = extract_list(data)
                
                trains = []
                for i, item in enumerate(raw_list):
                    train = norm_item(item, i)
                    if train and train.get("lat") and train.get("lon"):
                        trains.append(train)
                
                print(f"✅ Extracted {len(trains)} valid train positions")
                
                if trains:
                    print(f"\n📊 Sample train:")
                    sample = trains[0]
                    print(f"   ID: {sample.get('id')}")
                    print(f"   Location: {sample.get('lat')}, {sample.get('lon')}")
                    print(f"   Heading: {sample.get('heading')}")
                    print(f"   Speed: {sample.get('speed')}")
                
                return trains, f"ok - {count} trains"
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse error: {e}")
                return [], "JSON parse error"
        else:
            print(f"❌ API request failed")
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
    print("🚂🚂🚂 RAILOPS - FINAL PRODUCTION VERSION 🚂🚂🚂")
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
