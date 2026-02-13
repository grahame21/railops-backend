import os
import json
import datetime
import time
import math
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

def webmercator_to_latlon(x, y):
    """Convert Web Mercator (EPSG:3857) to latitude/longitude (EPSG:4326)"""
    try:
        x = float(x)
        y = float(y)
        lon = (x / 20037508.34) * 180
        lat = (y / 20037508.34) * 180
        lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
        return lat, lon
    except:
        return None, None

def login_and_get_trains():
    print("=" * 60)
    print("🚂 RAILOPS - SIMPLE EXTRACTION")
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
        
        # LOGIN
        print("\n📌 Logging in...")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        
        password = driver.find_element(By.ID, "pasS_word")
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
                print("✅ Remember Me checked")
        except:
            pass
        
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
        print("✅ Login button clicked")
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
        print("✅ Warning page closed")
        
        # Wait for map to load
        print("\n⏳ Waiting for map to load...")
        time.sleep(15)
        
        # EXTRACT ALL TRAINS
        print("\n🔍 Extracting ALL trains...")
        
        script = """
        var allTrains = [];
        
        function extractFeatures(source, sourceName) {
            if (!source || !source.getFeatures) return;
            
            try {
                var features = source.getFeatures();
                console.log(sourceName + ': ' + features.length + ' features');
                
                features.forEach(function(f) {
                    try {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom) {
                            var coords = geom.getCoordinates();
                            
                            // Get the ID - use whatever is available
                            var id = props.id || props.ID || 
                                    props.name || props.Name ||
                                    props.unit || props.Unit ||
                                    props.loco || props.Loco ||
                                    f.getId() || 
                                    sourceName + '_' + allTrains.length;
                            
                            allTrains.push({
                                'id': String(id),
                                'loco': String(props.loco || props.Loco || props.unit || props.Unit || ''),
                                'lat': coords[1],
                                'lon': coords[0],
                                'heading': Number(props.heading || props.Heading || props.rotation || 0),
                                'speed': Number(props.speed || props.Speed || 0),
                                'operator': String(props.operator || props.Operator || ''),
                                'service': String(props.service || props.Service || props.trainNumber || ''),
                                'source': sourceName
                            });
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        }
        
        // Check all possible sources
        var sources = [
            { name: 'regTrainsSource', obj: window.regTrainsSource },
            { name: 'unregTrainsSource', obj: window.unregTrainsSource },
            { name: 'markerSource', obj: window.markerSource },
            { name: 'arrowMarkersSource', obj: window.arrowMarkersSource },
            { name: 'regTrainsLayer', obj: window.regTrainsLayer ? window.regTrainsLayer.getSource() : null },
            { name: 'unregTrainsLayer', obj: window.unregTrainsLayer ? window.unregTrainsLayer.getSource() : null }
        ];
        
        sources.forEach(function(s) {
            if (s.obj) {
                extractFeatures(s.obj, s.name);
            }
        });
        
        return allTrains;
        """
        
        all_trains = driver.execute_script(script)
        print(f"\n✅ Extracted {len(all_trains)} total trains before filtering")
        
        # Convert coordinates and filter to Australia
        australian_trains = []
        seen_ids = set()
        
        for train in all_trains:
            lat, lon = webmercator_to_latlon(train['lon'], train['lat'])
            
            if lat and lon:
                # Store with proper lat/lon
                train['lat'] = round(lat, 6)
                train['lon'] = round(lon, 6)
                
                # Check if in Australia
                if -45 <= lat <= -10 and 110 <= lon <= 155:
                    train_id = train['id']
                    if train_id not in seen_ids:
                        seen_ids.add(train_id)
                        australian_trains.append(train)
        
        print(f"✅ Found {len(australian_trains)} Australian trains")
        
        if australian_trains:
            print("\n📋 Sample Australian train:")
            sample = australian_trains[0]
            for key, value in sample.items():
                if value:
                    print(f"   {key}: {value}")
        
        return australian_trains, f"ok - {len(australian_trains)} trains"
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return [], f"error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()

def main():
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = login_and_get_trains()
    write_output(trains, note)

if __name__ == "__main__":
    main()
