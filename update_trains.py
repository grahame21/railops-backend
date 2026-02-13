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
    print("🚂 DEBUG MODE - SHOW ALL PROPERTIES")
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
        
        password = driver.find_element(By.ID, "pasS_word")
        password.send_keys(TF_PASSWORD)
        
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
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
        print("✅ Login clicked")
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
        print("✅ Warning closed")
        
        # ZOOM TO AUSTRALIA
        print("\n🌏 Zooming to Australia...")
        driver.execute_script("""
            if (window.map) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 1000, maxZoom: 10 });
            }
        """)
        time.sleep(12)
        
        # DEBUG: DUMP ALL PROPERTIES
        print("\n🔍 DEBUG: Dumping properties of first 5 Australian trains...")
        
        script = """
        var debug = [];
        var count = 0;
        
        function dumpProperties(source) {
            if (!source || !source.getFeatures) return;
            
            var features = source.getFeatures();
            features.forEach(function(f) {
                if (count >= 5) return;
                
                try {
                    var props = f.getProperties();
                    var geom = f.getGeometry();
                    
                    if (geom) {
                        var coords = geom.getCoordinates();
                        var lon = coords[0];
                        var lat = coords[1];
                        
                        // Australia only
                        if (lat >= -45 && lat <= -10 && lon >= 110 && lon <= 155) {
                            
                            var propNames = [];
                            for (var key in props) {
                                if (props.hasOwnProperty(key) && typeof props[key] !== 'function') {
                                    propNames.push(key + ': ' + typeof props[key] + ' = ' + JSON.stringify(props[key]).slice(0, 50));
                                }
                            }
                            
                            debug.push({
                                'id': f.getId ? f.getId() : 'no-id',
                                'lat': lat,
                                'lon': lon,
                                'properties': propNames,
                                'raw_props': JSON.stringify(props).slice(0, 500)
                            });
                            count++;
                        }
                    }
                } catch(e) {}
            });
        }
        
        // Check all sources
        var sources = [
            window.regTrainsSource,
            window.unregTrainsSource,
            window.regTrainsLayer ? window.regTrainsLayer.getSource() : null,
            window.unregTrainsLayer ? window.unregTrainsLayer.getSource() : null,
            window.markerSource,
            window.arrowMarkersSource
        ];
        
        sources.forEach(dumpProperties);
        
        return debug;
        """
        
        debug_data = driver.execute_script(script)
        
        print(f"\n✅ Found {len(debug_data)} Australian trains for debugging")
        
        if debug_data:
            print("\n" + "="*60)
            print("🔬 DEBUG: FIRST TRAIN PROPERTIES")
            print("="*60)
            train = debug_data[0]
            print(f"\n📌 Train ID from feature: {train['id']}")
            print(f"📍 Location: {train['lat']}, {train['lon']}")
            print("\n📋 ALL PROPERTIES AVAILABLE:")
            for prop in train['properties']:
                print(f"   • {prop}")
            print("\n📦 RAW JSON:")
            print(train['raw_props'])
            print("="*60)
            
            # NOW extract ALL Australian trains with whatever ID we can get
            print("\n🔄 Extracting ALL Australian trains...")
            
            extract_script = """
            var trains = [];
            var seen = new Set();
            
            function extractAll(source) {
                if (!source || !source.getFeatures) return;
                
                var features = source.getFeatures();
                features.forEach(function(f) {
                    try {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom) {
                            var coords = geom.getCoordinates();
                            var lon = coords[0];
                            var lat = coords[1];
                            
                            // Australia only
                            if (lat >= -45 && lat <= -10 && lon >= 110 && lon <= 155) {
                                
                                // Get ANY identifier
                                var id = f.getId ? f.getId() : 
                                       props.id || props.ID || 
                                       props.name || props.Name ||
                                       props.unit || props.Unit ||
                                       props.loco || props.Loco ||
                                       'train_' + lat + '_' + lon;
                                
                                id = String(id).replace(/[._]source$/, '').replace(/^[^_]+[._]/, '');
                                
                                if (!seen.has(id)) {
                                    seen.add(id);
                                    trains.push({
                                        'id': id,
                                        'loco': id,  // Use whatever ID we found
                                        'lat': lat,
                                        'lon': lon,
                                        'heading': Number(props.heading || props.Heading || props.rotation || 0),
                                        'speed': Number(props.speed || props.Speed || 0),
                                        'operator': String(props.operator || props.Operator || props.railway || ''),
                                        'service': String(props.service || props.Service || props.trainNumber || ''),
                                        'destination': String(props.destination || props.Destination || ''),
                                        'timestamp': String(props.timestamp || props.Timestamp || '')
                                    });
                                }
                            }
                        }
                    } catch(e) {}
                });
            }
            
            var sources = [
                window.regTrainsSource,
                window.unregTrainsSource,
                window.regTrainsLayer ? window.regTrainsLayer.getSource() : null,
                window.unregTrainsLayer ? window.unregTrainsLayer.getSource() : null
            ];
            
            sources.forEach(extractAll);
            return trains;
            """
            
            trains = driver.execute_script(extract_script)
            print(f"\n✅ Extracted {len(trains)} Australian trains")
            
            if trains:
                print("\n📋 Sample train:")
                sample = trains[0]
                for key, value in sample.items():
                    print(f"   {key}: {value}")
            
            return trains, f"ok - {len(trains)} trains"
        else:
            print("\n❌ No Australian trains found! The map might not have loaded properly.")
            return [], "No Australian trains found"
        
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
