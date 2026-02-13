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
    """FINAL VERSION - Get ALL trains with ALL properties"""
    
    print("=" * 60)
    print("🚂 RAILOPS - FULL DETAIL EXTRACTION")
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
        
        # STEP 3: EXTRACT ALL FEATURES WITH ALL PROPERTIES
        print("\n🔍 Extracting ALL train details...")
        
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
                            var props = f.getProperties ? f.getProperties() : 
                                      f.values_ || f.properties_ || f.attributes || {};
                            
                            var geom = f.getGeometry ? f.getGeometry() : 
                                     f.geometry_ || f.geom;
                            
                            if (geom) {
                                var coords = geom.getCoordinates ? geom.getCoordinates() :
                                           geom.coordinates_ || geom.coords || [];
                                
                                if (coords.length >= 2) {
                                    // Get ALL possible train identifiers
                                    var id = String(props.id || props.ID || 
                                                  props.locoId || props.LocoId ||
                                                  props.loco || props.Loco ||
                                                  props.unit || props.Unit ||
                                                  props.name || props.NAME ||
                                                  props.vehicle || props.Vehicle ||
                                                  sourceName + '_' + allTrains.length);
                                    
                                    if (!seenIds.has(id)) {
                                        seenIds.add(id);
                                        
                                        // Extract EVERY property we can find
                                        allTrains.push({
                                            // Core identifiers
                                            'id': id,
                                            'train_id': String(props.train_id || props.TrainId || props.trainId || ''),
                                            'loco': String(props.loco || props.Loco || props.locomotive || props.Locomotive || ''),
                                            'unit': String(props.unit || props.Unit || ''),
                                            'service': String(props.service || props.Service || props.trainNumber || props.TrainNumber || ''),
                                            'operator': String(props.operator || props.Operator || props.railway || props.Railway || ''),
                                            
                                            // Position
                                            'lat': coords[1],
                                            'lon': coords[0],
                                            'x': coords[0],
                                            'y': coords[1],
                                            
                                            // Movement
                                            'heading': Number(props.heading || props.Heading || props.rotation || props.Rotation || props.bearing || props.Bearing || 0),
                                            'speed': Number(props.speed || props.Speed || props.velocity || props.Velocity || 0),
                                            'direction': String(props.direction || props.Direction || ''),
                                            
                                            // Timing
                                            'timestamp': String(props.timestamp || props.Timestamp || props.time || props.Time || props.lastSeen || props.LastSeen || ''),
                                            'updated': String(props.updated || props.Updated || ''),
                                            
                                            // Additional details
                                            'type': String(props.type || props.Type || props.vehicleType || props.VehicleType || ''),
                                            'status': String(props.status || props.Status || ''),
                                            'line': String(props.line || props.Line || props.route || props.Route || ''),
                                            'destination': String(props.destination || props.Destination || props.to || props.To || ''),
                                            
                                            // Metadata
                                            'source': sourceName,
                                            'feature_id': String(f.id_ || f.id || '')
                                        });
                                    }
                                }
                            }
                        } catch(e) {}
                    });
                }
            } catch(e) {}
        }
        
        // Check all sources
        var sourceNames = [
            'regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource',
            'regTrainsLayer', 'unregTrainsLayer', 'markerLayer', 'arrowMarkersLayer'
        ];
        
        sourceNames.forEach(function(name) {
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
        print(f"\n✅ Found {len(train_features)} trains with full details")
        
        # Convert coordinates and clean up data
        trains = []
        
        for feature in train_features:
            lat, lon = webmercator_to_latlon(feature['x'], feature['y'])
            
            if lat and lon:
                train = {
                    "id": feature.get('id', 'unknown'),
                    "train_id": feature.get('train_id', ''),
                    "loco": feature.get('loco', ''),
                    "unit": feature.get('unit', ''),
                    "service": feature.get('service', ''),
                    "operator": feature.get('operator', ''),
                    
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    
                    "heading": round(to_float(feature.get('heading', 0)), 1),
                    "speed": round(to_float(feature.get('speed', 0)), 1),
                    "direction": feature.get('direction', ''),
                    
                    "timestamp": feature.get('timestamp', ''),
                    "updated": feature.get('updated', ''),
                    
                    "type": feature.get('type', ''),
                    "status": feature.get('status', ''),
                    "line": feature.get('line', ''),
                    "destination": feature.get('destination', ''),
                    
                    "source": feature.get('source', '')
                }
                trains.append(train)
        
        print(f"\n📊 Total trains with details: {len(trains)}")
        
        # Show sample with all fields
        if trains:
            print("\n📋 Sample train (full details):")
            sample = trains[0]
            for key, value in sample.items():
                if value:  # Only show non-empty values
                    print(f"   {key}: {value}")
        
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
    print("🚂🚂🚂 RAILOPS - FULL DETAIL EXTRACTION 🚂🚂🚂")
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
