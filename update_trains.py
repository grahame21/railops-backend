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
    print("🚂 RAILOPS - DEBUG MODE (NO HEADLESS)")
    print("=" * 60)
    
    chrome_options = Options()
    # 🔴 TEMPORARILY DISABLE HEADLESS TO DEBUG
    # chrome_options.add_argument('--headless=new')
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
        print("\n⏳ Waiting for map to load (30 seconds)...")
        time.sleep(30)
        
        # DEBUG: Check if map exists
        map_exists = driver.execute_script("return typeof window.map !== 'undefined' && window.map !== null;")
        print(f"✅ Map exists: {map_exists}")
        
        if map_exists:
            # DEBUG: Check layers
            layer_count = driver.execute_script("return window.map.getLayers().getLength();")
            print(f"✅ Map has {layer_count} layers")
        
        # DEBUG: Check all possible sources
        print("\n🔍 Checking all train sources...")
        
        debug_script = """
        var sources = {
            'regTrainsSource': window.regTrainsSource,
            'unregTrainsSource': window.unregTrainsSource,
            'markerSource': window.markerSource,
            'arrowMarkersSource': window.arrowMarkersSource,
            'regTrainsLayer': window.regTrainsLayer,
            'unregTrainsLayer': window.unregTrainsLayer,
            'markerLayer': window.markerLayer,
            'arrowMarkersLayer': window.arrowMarkersLayer
        };
        
        var result = {};
        for (var name in sources) {
            var src = sources[name];
            result[name] = {
                exists: src !== null && src !== undefined,
                type: src ? src.constructor.name : 'null',
                hasGetFeatures: src ? typeof src.getFeatures === 'function' : false,
                hasGetSource: src ? typeof src.getSource === 'function' : false
            };
            
            // If it's a layer with source, check that too
            if (src && src.getSource) {
                var source = src.getSource();
                result[name + '_source'] = {
                    exists: source !== null,
                    type: source ? source.constructor.name : 'null',
                    hasGetFeatures: source ? typeof source.getFeatures === 'function' : false
                };
            }
        }
        
        return result;
        """
        
        source_info = driver.execute_script(debug_script)
        print("\n📊 Source Status:")
        for name, info in source_info.items():
            print(f"   {name}: exists={info['exists']}, type={info['type']}, hasGetFeatures={info.get('hasGetFeatures', False)}")
        
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
                            allTrains.push({
                                'id': String(props.id || props.ID || props.name || sourceName + '_' + allTrains.length),
                                'lat': coords[1],
                                'lon': coords[0],
                                'heading': Number(props.heading || props.Heading || 0),
                                'speed': Number(props.speed || props.Speed || 0),
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
            { name: 'arrowMarkersSource', obj: window.arrowMarkersSource }
        ];
        
        sources.forEach(function(s) {
            if (s.obj) {
                extractFeatures(s.obj, s.name);
                if (s.obj.getSource) {
                    extractFeatures(s.obj.getSource(), s.name + '_source');
                }
            }
        });
        
        return allTrains;
        """
        
        all_trains = driver.execute_script(script)
        print(f"\n✅ Extracted {len(all_trains)} total trains")
        
        if all_trains:
            print("\n📋 First train sample:")
            sample = all_trains[0]
            for key, value in sample.items():
                print(f"   {key}: {value}")
        
        return all_trains, f"ok - {len(all_trains)} trains"
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return [], f"error: {type(e).__name__}"
    finally:
        if driver:
            # Keep browser open for debugging if there are errors
            if len(all_trains) == 0:
                print("\n⚠️ No trains found - keeping browser open for 60 seconds for debugging...")
                time.sleep(60)
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
