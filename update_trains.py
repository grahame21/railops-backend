import os
import json
import datetime
import time
import re
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

def to_float(x):
    try: return float(x) if x is not None else None
    except: return None

def extract_trains_from_page_source(html):
    """Extract train data from the page HTML using regex patterns"""
    trains = []
    
    # Pattern 1: Look for JavaScript array of trains
    patterns = [
        r'trains\s*=\s*(\[.*?\]);',
        r'markers\s*=\s*(\[.*?\]);',
        r'var\s+trainData\s*=\s*(\[.*?\]);',
        r'var\s+data\s*=\s*({.*?"trains".*?});',
        r'JSON\.parse\([\'"](.+?)[\'"]\)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html, re.DOTALL)
        for match in matches:
            try:
                # Clean up the match
                clean_match = match.replace('\\"', '"').replace("\\'", "'")
                data = json.loads(clean_match)
                
                # Handle different data structures
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        train = {
                            "id": str(item.get("id") or item.get("ID") or item.get("trainId") or f"train_{i}"),
                            "lat": to_float(item.get("lat") or item.get("latitude") or item.get("Lat")),
                            "lon": to_float(item.get("lon") or item.get("longitude") or item.get("Lon")),
                            "operator": item.get("operator") or item.get("Operator") or "",
                            "heading": to_float(item.get("heading") or item.get("Heading") or 0),
                            "speed": to_float(item.get("speed") or item.get("Speed") or 0)
                        }
                        if train["lat"] and train["lon"]:
                            trains.append(train)
                elif isinstance(data, dict):
                    train_list = data.get("trains") or data.get("Trains") or data.get("markers") or data.get("Markers") or []
                    for i, item in enumerate(train_list):
                        train = {
                            "id": str(item.get("id") or item.get("ID") or f"train_{i}"),
                            "lat": to_float(item.get("lat") or item.get("latitude") or item.get("Lat")),
                            "lon": to_float(item.get("lon") or item.get("longitude") or item.get("Lon")),
                            "operator": item.get("operator") or item.get("Operator") or "",
                            "heading": to_float(item.get("heading") or item.get("Heading") or 0),
                            "speed": to_float(item.get("speed") or item.get("Speed") or 0)
                        }
                        if train["lat"] and train["lon"]:
                            trains.append(train)
            except:
                continue
    
    return trains

def login_and_extract_trains():
    """Login and extract train data directly from the page"""
    
    print("=" * 60)
    print("🚂 EXTRACTING TRAINS FROM PAGE SOURCE")
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
        
        # Wait for map to load completely
        print("\n⏳ Waiting for map to load and trains to appear...")
        time.sleep(15)
        
        # STEP 2: EXTRACT TRAIN DATA FROM PAGE
        print("\n🔍 Extracting train data from page source...")
        
        # Method 1: Look for JavaScript variables
        page_source = driver.page_source
        trains = extract_trains_from_page_source(page_source)
        
        if trains:
            print(f"✅ Found {len(trains)} trains in page source!")
        else:
            print("⚠️ No trains found in page source, trying JavaScript execution...")
            
            # Method 2: Execute JavaScript to get train data
            script = """
            // Try to find train data in various global variables
            var trainData = null;
            
            if (window.trainData) trainData = window.trainData;
            else if (window.trains) trainData = window.trains;
            else if (window.markers) trainData = window.markers;
            else if (window.TrainTracker) trainData = window.TrainTracker;
            
            // Try to find by searching through all global variables
            if (!trainData) {
                for (var key in window) {
                    try {
                        if (key.toLowerCase().includes('train') || key.toLowerCase().includes('marker')) {
                            var val = window[key];
                            if (val && typeof val === 'object') {
                                trainData = val;
                                break;
                            }
                        }
                    } catch(e) {}
                }
            }
            
            return trainData ? JSON.stringify(trainData) : null;
            """
            
            result = driver.execute_script(script)
            if result:
                try:
                    data = json.loads(result)
                    if isinstance(data, list):
                        for i, item in enumerate(data):
                            train = {
                                "id": str(item.get("id") or item.get("ID") or f"train_{i}"),
                                "lat": to_float(item.get("lat") or item.get("latitude")),
                                "lon": to_float(item.get("lon") or item.get("longitude")),
                                "operator": item.get("operator") or "",
                                "heading": to_float(item.get("heading") or 0),
                                "speed": to_float(item.get("speed") or 0)
                            }
                            if train["lat"] and train["lon"]:
                                trains.append(train)
                except:
                    pass
        
        # Method 3: Check if there's a map and get features
        if not trains:
            print("⚠️ Still no trains, checking OpenLayers map...")
            script = """
            if (map) {
                var features = [];
                map.getLayers().forEach(function(layer) {
                    if (layer.getSource && layer.getSource().getFeatures) {
                        var source = layer.getSource();
                        if (source.getFeatures) {
                            features = features.concat(source.getFeatures());
                        }
                    }
                });
                return features.map(function(f) {
                    var props = f.getProperties();
                    var geom = f.getGeometry();
                    var coords = geom ? geom.getCoordinates() : null;
                    return {
                        id: props.id || props.name || 'unknown',
                        lat: coords ? coords[1] : null,
                        lon: coords ? coords[0] : null,
                        heading: props.heading || 0,
                        speed: props.speed || 0,
                        operator: props.operator || ''
                    };
                });
            }
            return [];
            """
            features = driver.execute_script(script)
            for i, feature in enumerate(features):
                train = {
                    "id": str(feature.get("id") or f"train_{i}"),
                    "lat": to_float(feature.get("lat")),
                    "lon": to_float(feature.get("lon")),
                    "operator": feature.get("operator") or "",
                    "heading": to_float(feature.get("heading") or 0),
                    "speed": to_float(feature.get("speed") or 0)
                }
                if train["lat"] and train["lon"]:
                    trains.append(train)
        
        print(f"\n📊 Found {len(trains)} trains on the map!")
        
        if trains:
            print("\n📋 Sample train:")
            sample = trains[0]
            print(f"   ID: {sample['id']}")
            print(f"   Location: {sample['lat']}, {sample['lon']}")
            print(f"   Heading: {sample['heading']}")
            print(f"   Speed: {sample['speed']}")
        
        # Save screenshot
        driver.save_screenshot("map_with_trains.png")
        print("\n📸 Map screenshot saved")
        
        return trains, f"ok - {len(trains)} trains extracted from page"
        
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
    print("🚂🚂🚂 RAILOPS - PAGE EXTRACTION METHOD 🚂🚂🚂")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = login_and_extract_trains()
    write_output(trains, note)
    
    print("\n" + "=" * 60)
    print(f"🏁 Complete: {len(trains)} trains")
    print(f"📝 Status: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
