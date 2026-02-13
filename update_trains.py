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

def to_float(x):
    try: return float(x) if x is not None else None
    except: return None

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
    """DEBUG VERSION - Show ALL properties of train features"""
    
    print("=" * 60)
    print("🚂 RAILOPS - DEBUG MODE - SHOW ALL PROPERTIES")
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
        
        # STEP 2: ZOOM TO AUSTRALIA
        print("\n🌏 Zooming to Australia...")
        
        zoom_script = """
        if (window.map) {
            var australiaExtent = [112, -44, 154, -10];
            var proj = window.map.getView().getProjection();
            var extent = ol.proj.transformExtent(australiaExtent, 'EPSG:4326', proj);
            window.map.getView().fit(extent, {
                duration: 1000,
                padding: [50, 50, 50, 50],
                maxZoom: 10
            });
            return 'Zoomed to Australia';
        }
        return 'Map not found';
        """
        
        zoom_result = driver.execute_script(zoom_script)
        print(f"✅ {zoom_result}")
        
        # Wait for Australian trains to load
        print("\n⏳ Loading Australian trains...")
        time.sleep(12)
        
        # STEP 3: DEBUG - GET FIRST FEW FEATURES AND SHOW ALL PROPERTIES
        print("\n🔍 DEBUG: Getting first 5 features and ALL their properties...")
        
        debug_script = """
        var debug = [];
        var count = 0;
        
        function inspectSource(source, sourceName) {
            if (!source) return;
            
            try {
                var features = null;
                if (source.getFeatures) {
                    features = source.getFeatures();
                }
                
                if (features && features.length) {
                    for (var i = 0; i < Math.min(features.length, 5); i++) {
                        var f = features[i];
                        var props = f.getProperties ? f.getProperties() : {};
                        var geom = f.getGeometry ? f.getGeometry() : null;
                        
                        var propNames = [];
                        for (var key in props) {
                            var value = props[key];
                            // Don't include complex objects, just primitives
                            if (typeof value !== 'object' || value === null) {
                                propNames.push(key + ': ' + value);
                            } else {
                                propNames.push(key + ': [object]');
                            }
                        }
                        
                        var coords = geom ? geom.getCoordinates() : [];
                        
                        debug.push({
                            source: sourceName,
                            feature_index: i,
                            properties: propNames,
                            property_keys: Object.keys(props),
                            geometry_type: geom ? geom.getType() : 'none',
                            coordinates: coords.length >= 2 ? [coords[0], coords[1]] : [],
                            has_loco: props.loco !== undefined,
                            has_unit: props.unit !== undefined,
                            has_name: props.name !== undefined,
                            has_id: props.id !== undefined,
                            has_label: props.label !== undefined,
                            has_title: props.title !== undefined
                        });
                        
                        count++;
                        if (count >= 5) break;
                    }
                }
            } catch(e) {}
        }
        
        // Check arrowMarkersSource first (has the train IDs in your screenshot)
        inspectSource(window.arrowMarkersSource, 'arrowMarkersSource');
        if (window.arrowMarkersLayer) {
            inspectSource(window.arrowMarkersLayer.getSource(), 'arrowMarkersLayer_source');
        }
        
        return debug;
        """
        
        debug_info = driver.execute_script(debug_script)
        
        print("\n📊 DEBUG RESULTS:")
        print("=" * 60)
        for i, item in enumerate(debug_info):
            print(f"\n🔍 Feature {i+1} from {item['source']}:")
            print(f"   Geometry: {item['geometry_type']}")
            print(f"   Coordinates: {item['coordinates']}")
            print(f"   Has loco: {item['has_loco']}")
            print(f"   Has unit: {item['has_unit']}")
            print(f"   Has name: {item['has_name']}")
            print(f"   Has id: {item['has_id']}")
            print(f"   Has label: {item['has_label']}")
            print(f"   Has title: {item['has_title']}")
            print(f"\n   ALL property keys: {item['property_keys']}")
            print(f"\n   ALL property values:")
            for prop in item['properties'][:20]:  # Show first 20 properties
                print(f"      {prop}")
        
        # STEP 4: Now extract ALL trains with ALL properties
        print("\n🔍 Extracting ALL trains with ALL properties...")
        
        extract_script = """
        var allTrains = [];
        var seenIds = new Set();
        
        function extractFromSource(source, sourceName) {
            if (!source) return;
            
            try {
                var features = null;
                if (source.getFeatures) {
                    features = source.getFeatures();
                }
                
                if (features && features.length) {
                    features.forEach(function(f) {
                        try {
                            var props = f.getProperties ? f.getProperties() : {};
                            var geom = f.getGeometry ? f.getGeometry() : null;
                            
                            if (geom && geom.getType() === 'Point') {
                                var coords = geom.getCoordinates();
                                
                                // Look for ANY property that might contain the train ID
                                var possibleId = null;
                                
                                // Check ALL possible ID fields
                                var idFields = [
                                    'loco', 'Loco', 'unit', 'Unit', 'id', 'ID', 
                                    'name', 'NAME', 'label', 'Label', 'title', 'Title',
                                    'trainId', 'TrainId', 'vehicle', 'Vehicle',
                                    'locoid', 'locoId', 'LocoId', 'unitid', 'UnitId'
                                ];
                                
                                for (var i = 0; i < idFields.length; i++) {
                                    var field = idFields[i];
                                    if (props[field] !== undefined && props[field] !== null) {
                                        possibleId = String(props[field]).trim();
                                        if (possibleId && possibleId !== 'undefined' && possibleId !== 'null') {
                                            break;
                                        }
                                    }
                                }
                                
                                // If we found an ID, use it, otherwise generate one
                                var trainId = possibleId || sourceName + '_' + allTrains.length;
                                
                                if (!seenIds.has(trainId)) {
                                    seenIds.add(trainId);
                                    
                                    // Store ALL properties for debugging
                                    var allProps = {};
                                    for (var key in props) {
                                        var val = props[key];
                                        if (typeof val !== 'object' || val === null) {
                                            allProps[key] = val;
                                        }
                                    }
                                    
                                    allTrains.push({
                                        'id': trainId,
                                        'all_properties': allProps,
                                        'lat': coords[1],
                                        'lon': coords[0],
                                        'x': coords[0],
                                        'y': coords[1],
                                        'heading': Number(props.heading || props.Heading || 0),
                                        'speed': Number(props.speed || props.Speed || 0),
                                        'source': sourceName
                                    });
                                }
                            }
                        } catch(e) {}
                    });
                }
            } catch(e) {}
        }
        
        // Check all sources
        var sources = [
            'arrowMarkersSource', 'arrowMarkersLayer',
            'regTrainsSource', 'regTrainsLayer',
            'unregTrainsSource', 'unregTrainsLayer',
            'markerSource', 'markerLayer'
        ];
        
        sources.forEach(function(name) {
            var obj = window[name];
            if (obj) {
                extractFromSource(obj, name);
                if (obj.getSource) {
                    extractFromSource(obj.getSource(), name + '_source');
                }
            }
        });
        
        return allTrains;
        """
        
        train_features = driver.execute_script(extract_script)
        print(f"\n✅ Found {len(train_features)} trains with ALL properties")
        
        # Show sample of what IDs we actually got
        if train_features:
            print("\n📋 Sample of extracted IDs:")
            for i, train in enumerate(train_features[:10]):
                train_id = str(train.get('id', 'unknown'))
                print(f"   {i+1}. {train_id}")
            
            # Show the first train's ALL properties
            print("\n📋 ALL properties of first train:")
            first_train = train_features[0]
            all_props = first_train.get('all_properties', {})
            for key, value in list(all_props.items())[:30]:  # Show first 30 properties
                print(f"   {key}: {value}")
        
        # Convert coordinates and build final train list
        trains = []
        for feature in train_features:
            lat, lon = webmercator_to_latlon(feature['x'], feature['y'])
            if lat and lon:
                train = {
                    'id': str(feature.get('id', 'unknown')),
                    'lat': round(lat, 6),
                    'lon': round(lon, 6),
                    'heading': round(to_float(feature.get('heading', 0)), 1),
                    'speed': round(to_float(feature.get('speed', 0)), 1),
                    'source': feature.get('source', '')
                }
                trains.append(train)
        
        print(f"\n📊 Total trains saved: {len(trains)}")
        
        # Save screenshot
        driver.save_screenshot("australia_trains.png")
        print("\n📸 Australia map screenshot saved")
        
        return trains, f"ok - {len(trains)} trains"
        
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
    print("🚂🚂🚂 RAILOPS - DEBUG MODE 🚂🚂🚂")
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
