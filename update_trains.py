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

def extract_train_from_source(source_name, source_obj):
    """Extract train data from a source object"""
    trains = []
    if not source_obj or not source_obj.get('getFeatures'):
        return trains
    
    try:
        features = source_obj['getFeatures']()
        for feature in features:
            props = feature.get('properties_', {}) or feature.get('values_', {}) or feature
            geom = feature.get('geometry_', {})
            
            if geom and geom.get('type_') == 'Point':
                coords = geom.get('coordinates_', [])
                if len(coords) >= 2:
                    x, y = coords[0], coords[1]
                    lat, lon = webmercator_to_latlon(x, y)
                    
                    if lat and lon:
                        train = {
                            "id": str(props.get('id') or props.get('ID') or props.get('name') or props.get('NAME') or f"{source_name}_{len(trains)}"),
                            "lat": round(lat, 6),
                            "lon": round(lon, 6),
                            "heading": round(to_float(props.get('heading') or props.get('Heading') or 0), 1),
                            "speed": round(to_float(props.get('speed') or props.get('Speed') or 0), 1),
                            "operator": (props.get('operator') or props.get('Operator') or props.get('railway') or '')[:50],
                            "service": (props.get('service') or props.get('Service') or props.get('trainNumber') or '')[:50],
                            "source": source_name
                        }
                        trains.append(train)
    except Exception as e:
        print(f"      ⚠️ Error extracting from {source_name}: {e}")
    
    return trains

def login_and_get_trains():
    """PRODUCTION VERSION - Extracts ALL trains from global variables"""
    
    print("=" * 60)
    print("🚂 RAILOPS PRODUCTION SCRAPER - EXTRACTING FROM GLOBAL VARS")
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
        print("\n⏳ Loading map and trains...")
        time.sleep(15)
        
        # STEP 2: EXTRACT TRAINS FROM GLOBAL VARIABLES
        print("\n🔍 Extracting trains from global variables...")
        
        extract_script = """
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
            var source = sources[name];
            if (!source) continue;
            
            result[name] = {
                exists: true,
                type: source.constructor ? source.constructor.name : typeof source,
                features: []
            };
            
            // Try to get features from source
            if (source.getFeatures) {
                try {
                    var features = source.getFeatures();
                    result[name].featureCount = features.length;
                    
                    features.forEach(function(f) {
                        try {
                            var props = {};
                            // Try to get properties in different ways
                            if (f.getProperties) {
                                props = f.getProperties();
                            } else if (f.values_) {
                                props = f.values_;
                            } else if (f.properties_) {
                                props = f.properties_;
                            }
                            
                            var geom = null;
                            if (f.getGeometry) {
                                geom = f.getGeometry();
                            } else if (f.geometry_) {
                                geom = f.geometry_;
                            }
                            
                            var featureData = {
                                props: props,
                                geom: geom ? {
                                    type: geom.getType ? geom.getType() : geom.type_,
                                    coords: geom.getCoordinates ? geom.getCoordinates() : geom.coordinates_
                                } : null
                            };
                            result[name].features.push(featureData);
                        } catch(e) {}
                    });
                } catch(e) {
                    result[name].error = e.toString();
                }
            }
            
            // Try to get as array
            if (Array.isArray(source)) {
                result[name].arrayLength = source.length;
                result[name].featureCount = source.length;
            }
        }
        
        // Also try to get any train data arrays
        var trainArrays = ['regTrains', 'unregtrains', 'currentTrains', 'openTrains'];
        trainArrays.forEach(function(name) {
            if (window[name] && Array.isArray(window[name])) {
                result[name] = {
                    exists: true,
                    type: 'array',
                    featureCount: window[name].length,
                    features: window[name].slice(0, 10) // First 10 as sample
                };
            }
        });
        
        return result;
        """
        
        sources_data = driver.execute_script(extract_script)
        
        all_trains = []
        train_ids = set()
        
        print(f"\n📊 Train Sources Found:")
        
        for source_name, source_info in sources_data.items():
            if source_info and source_info.get('exists'):
                feature_count = source_info.get('featureCount', 0)
                print(f"\n   📍 {source_name}: {feature_count} features")
                
                # Extract features from this source
                if 'features' in source_info:
                    for feature_data in source_info['features']:
                        props = feature_data.get('props', {})
                        geom = feature_data.get('geom', {})
                        
                        if geom and geom.get('type') == 'Point':
                            coords = geom.get('coords', [])
                            if len(coords) >= 2:
                                lat, lon = webmercator_to_latlon(coords[0], coords[1])
                                
                                if lat and lon:
                                    train_id = str(props.get('id') or props.get('ID') or 
                                                  props.get('name') or props.get('NAME') or 
                                                  f"{source_name}_{len(all_trains)}")
                                    
                                    if train_id not in train_ids:
                                        train_ids.add(train_id)
                                        
                                        train = {
                                            "id": train_id,
                                            "lat": round(lat, 6),
                                            "lon": round(lon, 6),
                                            "heading": round(to_float(props.get('heading') or props.get('Heading') or 0), 1),
                                            "speed": round(to_float(props.get('speed') or props.get('Speed') or 0), 1),
                                            "operator": (props.get('operator') or props.get('Operator') or '')[:50],
                                            "service": (props.get('service') or props.get('Service') or props.get('trainNumber') or '')[:50],
                                            "source": source_name
                                        }
                                        all_trains.append(train)
        
        print(f"\n📊 Total unique trains extracted: {len(all_trains)}")
        
        # Categorize by region
        aus_trains = [t for t in all_trains if 110 <= t['lon'] <= 155 and -45 <= t['lat'] <= -10]
        us_trains = [t for t in all_trains if -130 <= t['lon'] <= -60 and 25 <= t['lat'] <= 50]
        
        print(f"\n📍 Australian trains: {len(aus_trains)}")
        print(f"📍 US trains: {len(us_trains)}")
        print(f"📍 Other: {len(all_trains) - len(aus_trains) - len(us_trains)}")
        
        if all_trains:
            print("\n📋 Sample trains:")
            for i, sample in enumerate(all_trains[:5]):
                print(f"\n   Train {i+1}:")
                print(f"     ID: {sample['id']}")
                print(f"     Location: {sample['lat']}, {sample['lon']}")
                print(f"     Heading: {sample['heading']}°")
                print(f"     Speed: {sample['speed']}")
                print(f"     Operator: {sample['operator']}")
                print(f"     Service: {sample['service']}")
                print(f"     Source: {sample['source']}")
        
        # Save screenshot
        driver.save_screenshot("map_with_trains.png")
        print("\n📸 Map screenshot saved")
        
        return all_trains, f"ok - {len(all_trains)} trains"
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
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
