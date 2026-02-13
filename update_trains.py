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
    """FIXED VERSION - Extract train ID from feature ID, not properties"""
    
    print("=" * 60)
    print("🚂 RAILOPS - FEATURE ID EXTRACTION")
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
        
        # STEP 3: EXTRACT TRAINS USING FEATURE ID
        print("\n🔍 Extracting trains using FEATURE ID...")
        
        extract_script = """
        var allTrains = [];
        var seenIds = new Set();
        
        function extractFromSource(source, sourceName) {
            if (!source) return;
            
            try {
                var features = null;
                if (source.getFeatures) {
                    features = source.getFeatures();
                } else if (source.A) {
                    features = source.A;
                } else if (source.features) {
                    features = source.features;
                } else if (source.features_) {
                    features = source.features_;
                }
                
                if (features && features.length) {
                    features.forEach(function(f) {
                        try {
                            var geom = f.getGeometry ? f.getGeometry() : 
                                     f.geometry_ || f.geom;
                            
                            if (geom && geom.getType() === 'Point') {
                                var coords = geom.getCoordinates();
                                
                                // CRITICAL: Get the feature ID from the feature itself
                                // This is where "ice13802", "ice33799" etc. are stored
                                var featureId = null;
                                
                                // Try all possible feature ID locations
                                if (f.getId) {
                                    featureId = f.getId();
                                } else if (f.id_) {
                                    featureId = f.id_;
                                } else if (f.id) {
                                    featureId = f.id;
                                } else if (f.ol_uid) {
                                    featureId = f.ol_uid;
                                }
                                
                                // Convert to string and clean up
                                if (featureId !== null && featureId !== undefined) {
                                    featureId = String(featureId).trim();
                                } else {
                                    featureId = sourceName + '_' + allTrains.length;
                                }
                                
                                // Get properties (minimal, but include heading if available)
                                var props = f.getProperties ? f.getProperties() : {};
                                var heading = Number(props.heading || props.Heading || 0);
                                var speed = Number(props.speed || props.Speed || 0);
                                
                                if (!seenIds.has(featureId)) {
                                    seenIds.add(featureId);
                                    
                                    allTrains.push({
                                        'id': featureId,
                                        'loco': featureId,  // Use the feature ID as the loco number
                                        'feature_id': featureId,
                                        'lat': coords[1],
                                        'lon': coords[0],
                                        'x': coords[0],
                                        'y': coords[1],
                                        'heading': heading,
                                        'speed': speed,
                                        'source': sourceName
                                    });
                                }
                            }
                        } catch(e) {}
                    });
                }
            } catch(e) {}
        }
        
        // Check all sources - PRIORITIZE arrowMarkersSource (has the train IDs in your screenshot)
        var sourcePriority = [
            'arrowMarkersSource', 'arrowMarkersLayer',
            'regTrainsSource', 'regTrainsLayer',
            'unregTrainsSource', 'unregTrainsLayer',
            'markerSource', 'markerLayer'
        ];
        
        sourcePriority.forEach(function(name) {
            var obj = window[name];
            if (obj) {
                extractFromSource(obj, name);
                if (obj.getSource) {
                    extractFromSource(obj.getSource(), name + '_source');
                }
            }
        });
        
        // Also check all map layers
        if (window.map) {
            window.map.getLayers().forEach(function(layer, index) {
                if (layer.getSource) {
                    extractFromSource(layer.getSource(), 'layer_' + index);
                }
            });
        }
        
        return allTrains;
        """
        
        train_features = driver.execute_script(extract_script)
        print(f"\n✅ Found {len(train_features)} trains with FEATURE IDs")
        
        # Show sample of what IDs we actually got
        if train_features:
            print("\n📋 Sample of extracted train IDs (should be like 'ice13802', 'ice33799'):")
            real_id_count = 0
            for i, train in enumerate(train_features[:20]):
                train_id = str(train.get('id', 'unknown'))
                print(f"   {i+1}. {train_id}")
                if train_id and not train_id.startswith(('arrow', 'layer', 'marker', 'unknown', 'reg', 'unreg')):
                    real_id_count += 1
            
            print(f"\n✅ Real train IDs in sample: {real_id_count}/{min(20, len(train_features))}")
        
        # Convert coordinates and build final train list
        trains = []
        for feature in train_features:
            lat, lon = webmercator_to_latlon(feature['x'], feature['y'])
            if lat and lon:
                train = {
                    'id': str(feature.get('id', 'unknown')),
                    'loco': str(feature.get('loco', feature.get('id', 'unknown'))),
                    'lat': round(lat, 6),
                    'lon': round(lon, 6),
                    'heading': round(to_float(feature.get('heading', 0)), 1),
                    'speed': round(to_float(feature.get('speed', 0)), 1),
                    'source': str(feature.get('source', ''))
                }
                trains.append(train)
        
        print(f"\n📊 Total trains saved: {len(trains)}")
        
        # Final check - count trains with real-looking IDs
        if trains:
            real_ids = [t for t in trains if t['id'] and 
                       not str(t['id']).startswith(('arrow', 'layer', 'marker', 'unknown', 'reg', 'unreg')) and
                       len(str(t['id'])) > 3]  # IDs like "ice13802" are longer
            print(f"\n✅ Trains with REAL IDs: {len(real_ids)} out of {len(trains)}")
        
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
    print("🚂🚂🚂 RAILOPS - FEATURE ID EXTRACTION 🚂🚂🚂")
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
