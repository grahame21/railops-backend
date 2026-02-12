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
from pyproj import Transformer

OUT_FILE = "trains.json"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

# Coordinate transformer: EPSG:3857 (Web Mercator) to EPSG:4326 (Lat/Lon)
transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326")

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

def convert_coords(x, y):
    """Convert EPSG:3857 to lat/lon"""
    try:
        lon, lat = transformer.transform(x, y)
        return lat, lon
    except:
        return None, None

def login_and_get_trains():
    """PRODUCTION VERSION - Extracts ALL trains from the map"""
    
    print("=" * 60)
    print("🚂 RAILOPS PRODUCTION SCRAPER - ALL TRAINS")
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
        
        # STEP 2: DEBUG - Check what layers are available
        print("\n🔍 Checking map layers...")
        layer_script = """
        var layers = [];
        if (window.map) {
            window.map.getLayers().forEach(function(layer, index) {
                var layerInfo = {
                    index: index,
                    type: layer.constructor.name,
                    visible: layer.getVisible(),
                    zIndex: layer.getZIndex(),
                    hasSource: !!layer.getSource,
                    hasFeatures: false,
                    featureCount: 0
                };
                
                if (layer.getSource && layer.getSource().getFeatures) {
                    try {
                        var features = layer.getSource().getFeatures();
                        layerInfo.hasFeatures = true;
                        layerInfo.featureCount = features.length;
                        
                        // Get first feature as sample
                        if (features.length > 0) {
                            var f = features[0];
                            var props = f.getProperties();
                            layerInfo.sampleId = props.id || props.name || 'unknown';
                        }
                    } catch(e) {}
                }
                layers.push(layerInfo);
            });
        }
        return layers;
        """
        
        layers = driver.execute_script(layer_script)
        print(f"✅ Found {len(layers)} map layers")
        for layer in layers:
            print(f"   Layer {layer['index']}: {layer['type']}")
            print(f"     Visible: {layer['visible']}, Features: {layer['featureCount']}")
        
        # STEP 3: EXTRACT ALL TRAINS FROM ALL LAYERS
        print("\n🔍 Extracting ALL trains from map...")
        
        extract_script = """
        var allTrains = [];
        
        function extractFeatures(source) {
            if (!source || !source.getFeatures) return [];
            try {
                return source.getFeatures();
            } catch(e) {
                return [];
            }
        }
        
        if (window.map) {
            window.map.getLayers().forEach(function(layer) {
                // Check if layer has a source
                if (layer.getSource) {
                    var source = layer.getSource();
                    var features = extractFeatures(source);
                    
                    features.forEach(function(f) {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom) {
                            var coords = geom.getCoordinates();
                            
                            // Handle different geometry types
                            if (geom.getType() === 'Point') {
                                // Try to find train identifiers
                                var id = props.id || 
                                        props.ID || 
                                        props.trainId || 
                                        props.TrainId || 
                                        props.unit || 
                                        props.Unit || 
                                        props.loco || 
                                        props.Loco || 
                                        props.name || 
                                        props.Name || 
                                        'unknown';
                                
                                var heading = props.heading || 
                                            props.Heading || 
                                            props.rotation || 
                                            props.Rotation || 
                                            props.bearing || 
                                            props.Bearing || 
                                            0;
                                
                                var speed = props.speed || 
                                          props.Speed || 
                                          props.velocity || 
                                          props.Velocity || 
                                          0;
                                
                                var operator = props.operator || 
                                             props.Operator || 
                                             props.company || 
                                             props.Company || 
                                             '';
                                
                                var service = props.service || 
                                            props.Service || 
                                            props.trainNumber || 
                                            props.TrainNumber || 
                                            '';
                                
                                allTrains.push({
                                    id: String(id),
                                    x: coords[0],
                                    y: coords[1],
                                    heading: heading,
                                    speed: speed,
                                    operator: operator,
                                    service: service,
                                    layerIndex: layer.getZIndex ? layer.getZIndex() : 0,
                                    layerType: layer.constructor.name
                                });
                            }
                        }
                    });
                }
                
                // Check if layer has multiple sources (Group layers)
                if (layer.getLayers) {
                    var subLayers = layer.getLayers();
                    if (subLayers && subLayers.forEach) {
                        subLayers.forEach(function(subLayer) {
                            if (subLayer.getSource) {
                                var source = subLayer.getSource();
                                var features = extractFeatures(source);
                                
                                features.forEach(function(f) {
                                    var props = f.getProperties();
                                    var geom = f.getGeometry();
                                    
                                    if (geom && geom.getType() === 'Point') {
                                        var coords = geom.getCoordinates();
                                        var id = props.id || props.ID || props.unit || props.Unit || props.loco || props.Loco || props.name || props.Name || 'unknown';
                                        var heading = props.heading || props.Heading || props.rotation || props.Rotation || 0;
                                        var speed = props.speed || props.Speed || 0;
                                        var operator = props.operator || props.Operator || '';
                                        
                                        allTrains.push({
                                            id: String(id),
                                            x: coords[0],
                                            y: coords[1],
                                            heading: heading,
                                            speed: speed,
                                            operator: operator,
                                            layerIndex: subLayer.getZIndex ? subLayer.getZIndex() : 0,
                                            layerType: subLayer.constructor.name
                                        });
                                    }
                                });
                            }
                        });
                    }
                }
            });
        }
        
        // Also check for any global train data arrays
        if (window.trainData) allTrains = allTrains.concat(window.trainData);
        if (window.trains) allTrains = allTrains.concat(window.trains);
        if (window.markers) allTrains = allTrains.concat(window.markers);
        
        return allTrains;
        """
        
        features = driver.execute_script(extract_script)
        print(f"\n✅ Found {len(features)} total features on map")
        
        # Group by layer to see distribution
        layer_counts = {}
        for f in features:
            layer_type = f.get('layerType', 'unknown')
            layer_counts[layer_type] = layer_counts.get(layer_type, 0) + 1
        
        print("\n📊 Features by layer type:")
        for layer_type, count in layer_counts.items():
            print(f"   {layer_type}: {count} features")
        
        # Convert coordinates and build train list
        trains = []
        train_ids = set()  # Avoid duplicates
        
        for feature in features:
            # Convert coordinates from EPSG:3857 to lat/lon
            lat, lon = convert_coords(feature['x'], feature['y'])
            
            if lat and lon:
                train_id = str(feature.get('id', 'unknown'))
                
                # Avoid duplicates with same ID and similar coordinates
                if train_id not in train_ids:
                    train_ids.add(train_id)
                    
                    train = {
                        "id": train_id,
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "heading": round(to_float(feature.get('heading', 0)), 1),
                        "speed": round(to_float(feature.get('speed', 0)), 1),
                        "operator": feature.get('operator', ''),
                        "service": feature.get('service', '')
                    }
                    trains.append(train)
        
        print(f"\n📊 Extracted {len(trains)} unique trains with coordinates")
        
        if trains:
            print("\n📋 Sample trains:")
            for i, sample in enumerate(trains[:5]):
                print(f"\n   Train {i+1}:")
                print(f"     ID: {sample['id']}")
                print(f"     Location: {sample['lat']}, {sample['lon']}")
                print(f"     Heading: {sample['heading']}°")
                print(f"     Speed: {sample['speed']}")
                print(f"     Operator: {sample['operator']}")
                print(f"     Service: {sample['service']}")
        
        # Save screenshot
        driver.save_screenshot("map_with_trains.png")
        print("\n📸 Map screenshot saved")
        
        return trains, f"ok - {len(trains)} trains"
        
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
