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
    """PRODUCTION VERSION - Extracts ALL trains from ALL layers"""
    
    print("=" * 60)
    print("🚂 RAILOPS PRODUCTION SCRAPER - DEBUG MODE")
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
        
        # STEP 2: DEBUG - DUMP ALL LAYER INFORMATION
        print("\n🔍 DEBUG: Dumping all map layers...")
        
        debug_script = """
        var debug = {
            layers: [],
            globalVars: []
        };
        
        // Check map object
        if (window.map) {
            debug.mapExists = true;
            debug.mapView = window.map.getView ? window.map.getView().getZoom() : 'unknown';
            debug.mapProjection = window.map.getView ? window.map.getView().getProjection().getCode() : 'unknown';
            
            window.map.getLayers().forEach(function(layer, index) {
                var layerInfo = {
                    index: index,
                    type: layer.constructor.name,
                    visible: layer.getVisible ? layer.getVisible() : 'unknown',
                    zIndex: layer.getZIndex ? layer.getZIndex() : 'unknown',
                    hasSource: !!layer.getSource,
                    className: layer.className_ || layer.getClassName ? layer.getClassName() : 'none',
                    title: layer.get('title') || layer.get('name') || 'none',
                };
                
                // Try to get source info
                if (layer.getSource) {
                    var source = layer.getSource();
                    layerInfo.sourceType = source.constructor.name;
                    layerInfo.sourceUrl = source.getUrl ? source.getUrl() : 'none';
                    
                    // Try to get features
                    if (source.getFeatures) {
                        try {
                            var features = source.getFeatures();
                            layerInfo.featureCount = features.length;
                            
                            // Sample first feature
                            if (features.length > 0) {
                                var f = features[0];
                                var props = f.getProperties();
                                var geom = f.getGeometry();
                                layerInfo.sampleProps = Object.keys(props).slice(0, 10);
                                layerInfo.geomType = geom ? geom.getType() : 'none';
                                
                                if (geom && geom.getType() === 'Point') {
                                    var coords = geom.getCoordinates();
                                    layerInfo.sampleCoords = [coords[0], coords[1]];
                                }
                            }
                        } catch(e) {
                            layerInfo.featureError = e.toString();
                        }
                    }
                }
                
                // Check for sublayers
                if (layer.getLayers) {
                    var subLayers = layer.getLayers();
                    layerInfo.subLayerCount = subLayers.getLength ? subLayers.getLength() : 'unknown';
                    layerInfo.subLayers = [];
                    
                    subLayers.forEach(function(subLayer, subIndex) {
                        var subInfo = {
                            index: subIndex,
                            type: subLayer.constructor.name,
                            visible: subLayer.getVisible ? subLayer.getVisible() : 'unknown',
                            title: subLayer.get('title') || subLayer.get('name') || 'none'
                        };
                        
                        if (subLayer.getSource && subLayer.getSource().getFeatures) {
                            try {
                                var features = subLayer.getSource().getFeatures();
                                subInfo.featureCount = features.length;
                            } catch(e) {}
                        }
                        
                        layerInfo.subLayers.push(subInfo);
                    });
                }
                
                debug.layers.push(layerInfo);
            });
        } else {
            debug.mapExists = false;
        }
        
        // Check global variables
        var trainVars = [];
        for (var key in window) {
            if (key.toLowerCase().includes('train') || 
                key.toLowerCase().includes('marker') || 
                key.toLowerCase().includes('loco') ||
                key.toLowerCase().includes('vehicle')) {
                try {
                    var val = window[key];
                    if (val && typeof val === 'object') {
                        trainVars.push({
                            name: key,
                            type: Array.isArray(val) ? 'array' : 'object',
                            length: Array.isArray(val) ? val.length : Object.keys(val).length
                        });
                    }
                } catch(e) {}
            }
        }
        debug.globalVars = trainVars;
        
        return debug;
        """
        
        debug_info = driver.execute_script(debug_script)
        
        print(f"\n📊 Map Debug Information:")
        print(f"   Map exists: {debug_info.get('mapExists', False)}")
        print(f"   Zoom level: {debug_info.get('mapView', 'unknown')}")
        print(f"   Projection: {debug_info.get('mapProjection', 'unknown')}")
        print(f"\n   Found {len(debug_info.get('layers', []))} layers:")
        
        for layer in debug_info.get('layers', []):
            print(f"\n   📍 Layer {layer['index']}: {layer['type']}")
            print(f"      Title: {layer.get('title', 'none')}")
            print(f"      Visible: {layer.get('visible', 'unknown')}")
            print(f"      Z-Index: {layer.get('zIndex', 'unknown')}")
            print(f"      Has Source: {layer.get('hasSource', False)}")
            
            if 'sourceType' in layer:
                print(f"      Source Type: {layer['sourceType']}")
                print(f"      Feature Count: {layer.get('featureCount', 0)}")
                
                if layer.get('featureCount', 0) > 0:
                    print(f"      Sample Props: {layer.get('sampleProps', [])}")
                    print(f"      Geometry Type: {layer.get('geomType', 'none')}")
                    if 'sampleCoords' in layer:
                        lat, lon = webmercator_to_latlon(layer['sampleCoords'][0], layer['sampleCoords'][1])
                        print(f"      Sample Location: {lat:.4f}, {lon:.4f}")
            
            if 'subLayerCount' in layer:
                print(f"      Sub-layers: {layer['subLayerCount']}")
                for sub in layer.get('subLayers', []):
                    print(f"         - {sub['type']}: {sub.get('featureCount', 0)} features")
        
        print(f"\n📊 Global train-related variables:")
        for var in debug_info.get('globalVars', []):
            print(f"   - {var['name']}: {var['type']} with {var.get('length', 0)} items")
        
        # STEP 3: NOW EXTRACT ALL FEATURES FROM EVERY LAYER
        print("\n🔍 Extracting ALL features from ALL layers...")
        
        extract_script = """
        var allFeatures = [];
        
        function extractFromSource(source, layerInfo) {
            if (!source || !source.getFeatures) return;
            try {
                var features = source.getFeatures();
                features.forEach(function(f) {
                    var props = f.getProperties();
                    var geom = f.getGeometry();
                    
                    if (geom && geom.getType() === 'Point') {
                        var coords = geom.getCoordinates();
                        allFeatures.push({
                            id: props.id || props.ID || props.name || props.NAME || 'unknown',
                            x: coords[0],
                            y: coords[1],
                            heading: props.heading || props.Heading || props.rotation || 0,
                            speed: props.speed || props.Speed || 0,
                            operator: props.operator || props.Operator || props.railway || '',
                            service: props.service || props.Service || props.trainNumber || '',
                            layer: layerInfo
                        });
                    }
                });
            } catch(e) {}
        }
        
        if (window.map) {
            window.map.getLayers().forEach(function(layer) {
                var layerName = layer.get('title') || layer.get('name') || layer.constructor.name;
                
                // Main layer source
                if (layer.getSource) {
                    extractFromSource(layer.getSource(), layerName + ' (main)');
                }
                
                // Sub-layers
                if (layer.getLayers) {
                    var subLayers = layer.getLayers();
                    subLayers.forEach(function(subLayer, idx) {
                        var subName = subLayer.get('title') || subLayer.get('name') || subLayer.constructor.name;
                        if (subLayer.getSource) {
                            extractFromSource(subLayer.getSource(), layerName + ' > ' + subName);
                        }
                    });
                }
            });
        }
        
        return allFeatures;
        """
        
        features = driver.execute_script(extract_script)
        print(f"\n✅ Found {len(features)} total features on map")
        
        # Group features by layer
        layer_counts = {}
        for f in features:
            layer = f.get('layer', 'unknown')
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
        
        print("\n📊 Features by layer:")
        for layer, count in sorted(layer_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {layer}: {count} features")
        
        # Convert coordinates and build train list
        trains = []
        train_ids = set()
        
        for feature in features:
            lat, lon = webmercator_to_latlon(feature['x'], feature['y'])
            
            if lat and lon and -90 <= lat <= 90 and -180 <= lon <= 180:
                train_id = str(feature.get('id', 'unknown'))
                
                if train_id not in train_ids:
                    train_ids.add(train_id)
                    
                    train = {
                        "id": train_id,
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "heading": round(to_float(feature.get('heading', 0)), 1),
                        "speed": round(to_float(feature.get('speed', 0)), 1),
                        "operator": feature.get('operator', '')[:50],
                        "service": feature.get('service', '')[:50]
                    }
                    trains.append(train)
        
        print(f"\n📊 Extracted {len(trains)} unique trains with valid coordinates")
        
        if trains:
            print("\n📋 Sample trains by region:")
            aus_trains = [t for t in trains if 110 <= t['lon'] <= 155 and -45 <= t['lat'] <= -10]
            us_trains = [t for t in trains if -130 <= t['lon'] <= -60 and 25 <= t['lat'] <= 50]
            
            print(f"\n   Australian trains: {len(aus_trains)}")
            print(f"   US trains: {len(us_trains)}")
            print(f"   Other: {len(trains) - len(aus_trains) - len(us_trains)}")
            
            print("\n📋 First 5 trains:")
            for i, sample in enumerate(trains[:5]):
                print(f"\n   Train {i+1}:")
                print(f"     ID: {sample['id']}")
                print(f"     Location: {sample['lat']}, {sample['lon']}")
                print(f"     Heading: {sample['heading']}°")
                print(f"     Speed: {sample['speed']}")
                print(f"     Operator: {sample['operator']}")
        
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
    print("🚂🚂🚂 RAILOPS - DEBUG MODE - FIND ALL LAYERS 🚂🚂🚂")
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
