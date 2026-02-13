import os
import json
import datetime
import time
import math
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
    print("🚂 RAILOPS - DEBUG TRAIN PROPERTIES")
    print("=" * 60)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
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
        
        # Zoom to Australia
        print("\n🌏 Zooming to Australia...")
        driver.execute_script("""
            if (window.map) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 2000, maxZoom: 10 });
            }
        """)
        print("⏳ Waiting for trains to load...")
        time.sleep(15)
        
        # DEBUG: Get ALL properties of the first train
        print("\n🔍 DEBUG: Dumping ALL properties of first train...")
        
        debug_script = """
        var debug = {
            sources: {},
            firstTrain: null,
            allPropertyNames: new Set()
        };
        
        function inspectSource(src, name) {
            if (!src || !src.getFeatures) return;
            
            try {
                var features = src.getFeatures();
                debug.sources[name] = features.length;
                
                if (features.length > 0 && !debug.firstTrain) {
                    var f = features[0];
                    var props = f.getProperties();
                    var geom = f.getGeometry();
                    var coords = geom ? geom.getCoordinates() : null;
                    
                    debug.firstTrain = {
                        id: f.getId ? f.getId() : null,
                        geometry: coords,
                        properties: {}
                    };
                    
                    // Get ALL property names and values
                    for (var key in props) {
                        if (props.hasOwnProperty(key)) {
                            var value = props[key];
                            var type = typeof value;
                            var display = value;
                            
                            // Truncate long strings
                            if (type === 'string' && value.length > 50) {
                                display = value.substring(0, 50) + '...';
                            }
                            
                            debug.firstTrain.properties[key] = {
                                type: type,
                                value: display
                            };
                            debug.allPropertyNames.add(key);
                        }
                    }
                }
            } catch(e) {}
        }
        
        // Check all sources
        inspectSource(window.regTrainsSource, 'regTrainsSource');
        inspectSource(window.unregTrainsSource, 'unregTrainsSource');
        if (window.regTrainsLayer) inspectSource(window.regTrainsLayer.getSource(), 'regTrainsLayer');
        if (window.unregTrainsLayer) inspectSource(window.unregTrainsLayer.getSource(), 'unregTrainsLayer');
        
        debug.allPropertyNames = Array.from(debug.allPropertyNames).sort();
        return debug;
        """
        
        debug_info = driver.execute_script(debug_script)
        
        print("\n" + "="*60)
        print("📊 SOURCE FEATURE COUNTS:")
        print("="*60)
        for source, count in debug_info.get('sources', {}).items():
            print(f"   {source}: {count} features")
        
        if debug_info.get('firstTrain'):
            print("\n" + "="*60)
            print("🚂 FIRST TRAIN - ALL PROPERTIES:")
            print("="*60)
            first = debug_info['firstTrain']
            print(f"\n📌 Feature ID: {first.get('id')}")
            print(f"📍 Coordinates: {first.get('geometry')}")
            print("\n📋 Property Names and Values:")
            print("-"*60)
            for key, prop in first.get('properties', {}).items():
                print(f"   {key}: [{prop['type']}] = {prop['value']}")
        else:
            print("\n❌ No trains found in any source!")
            return [], "No trains found"
        
        # NOW extract ALL trains with the CORRECT ID field
        print("\n" + "="*60)
        print("🔍 EXTRACTING ALL TRAINS WITH REAL IDs")
        print("="*60)
        
        extract_script = """
        var trains = [];
        var seenIds = new Set();
        
        function extractFromSource(src, sourceName) {
            if (!src || !src.getFeatures) return;
            
            try {
                var features = src.getFeatures();
                features.forEach(function(f) {
                    try {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            // TRY EVERY POSSIBLE ID FIELD
                            var id = null;
                            
                            // Check all common ID field names
                            var idFields = [
                                'id', 'ID', 'Id',
                                'loco', 'Loco', 'LOCO',
                                'unit', 'Unit', 'UNIT',
                                'name', 'Name', 'NAME',
                                'trainId', 'TrainId', 'TRAINID',
                                'train_id', 'Train_ID',
                                'locoid', 'LocoId', 'LOCOID',
                                'locomotive', 'Locomotive',
                                'vehicle', 'Vehicle',
                                'number', 'Number',
                                'service', 'Service',
                                'run', 'Run',
                                'consist', 'Consist',
                                'identifier', 'Identifier'
                            ];
                            
                            for (var i = 0; i < idFields.length; i++) {
                                var field = idFields[i];
                                if (props[field] && typeof props[field] === 'string' && props[field].length > 0) {
                                    id = props[field];
                                    break;
                                }
                            }
                            
                            // If still no ID, try feature ID
                            if (!id) {
                                id = f.getId ? f.getId() : null;
                            }
                            
                            // Last resort - generate one
                            if (!id) {
                                id = sourceName + '_' + trains.length;
                            }
                            
                            id = String(id).trim();
                            
                            // Only add if we haven't seen this ID before
                            if (!seenIds.has(id)) {
                                seenIds.add(id);
                                trains.push({
                                    'id': id,
                                    'loco': id,  // Use the same ID for loco
                                    'lat': coords[1],
                                    'lon': coords[0],
                                    'heading': Number(props.heading || props.Heading || props.rotation || 0),
                                    'speed': Number(props.speed || props.Speed || props.velocity || 0),
                                    'operator': String(props.operator || props.Operator || props.railway || ''),
                                    'service': String(props.service || props.Service || props.trainNumber || ''),
                                    'destination': String(props.destination || props.Destination || props.to || ''),
                                    'source': sourceName
                                });
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        }
        
        extractFromSource(window.regTrainsSource, 'reg');
        extractFromSource(window.unregTrainsSource, 'unreg');
        if (window.regTrainsLayer) extractFromSource(window.regTrainsLayer.getSource(), 'reg_layer');
        if (window.unregTrainsLayer) extractFromSource(window.unregTrainsLayer.getSource(), 'unreg_layer');
        
        return trains;
        """
        
        all_trains = driver.execute_script(extract_script)
        print(f"\n✅ Extracted {len(all_trains)} trains with IDs")
        
        # Convert coordinates
        trains = []
        for t in all_trains:
            lat, lon = webmercator_to_latlon(t['lon'], t['lat'])
            if lat and lon and -45 <= lat <= -10 and 110 <= lon <= 155:
                trains.append({
                    'id': t['id'],
                    'loco': t['loco'],
                    'lat': round(lat, 6),
                    'lon': round(lon, 6),
                    'heading': round(float(t['heading']), 1),
                    'speed': round(float(t['speed']), 1),
                    'operator': t['operator'],
                    'service': t['service'],
                    'destination': t['destination']
                })
        
        print(f"✅ Found {len(trains)} Australian trains with real IDs")
        
        if trains:
            print("\n📋 Sample trains with REAL IDs:")
            for i, t in enumerate(trains[:5]):
                print(f"\n   Train {i+1}:")
                print(f"     ID: {t['id']}")
                print(f"     Loco: {t['loco']}")
                print(f"     Location: {t['lat']}, {t['lon']}")
                print(f"     Heading: {t['heading']}°")
                print(f"     Speed: {t['speed']} km/h")
                print(f"     Operator: {t['operator']}")
                print(f"     Service: {t['service']}")
                print(f"     Destination: {t['destination']}")
        
        return trains, f"ok - {len(trains)} trains"
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
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
