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
    print("🚂 RAILOPS - SCAN ALL POSSIBLE SOURCES")
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
        time.sleep(20)  # Extra long wait
        
        # SCAN EVERY POSSIBLE SOURCE
        print("\n🔍 SCANNING ALL POSSIBLE TRAIN SOURCES...")
        
        scan_script = """
        var results = {
            sources: {},
            layers: {},
            mapLayers: [],
            globalVars: []
        };
        
        // Check all known source names
        var sourceNames = [
            'regTrainsSource', 'unregTrainsSource',
            'markerSource', 'arrowMarkersSource',
            'trainSource', 'trainsSource',
            'vehicleSource', 'vehiclesSource',
            'locosSource', 'locomotivesSource',
            'pointSource', 'featureSource'
        ];
        
        sourceNames.forEach(function(name) {
            if (window[name]) {
                var src = window[name];
                results.sources[name] = {
                    exists: true,
                    type: src.constructor ? src.constructor.name : typeof src,
                    hasGetFeatures: typeof src.getFeatures === 'function',
                    featureCount: src.getFeatures ? src.getFeatures().length : 0
                };
            }
        });
        
        // Check all known layer names
        var layerNames = [
            'regTrainsLayer', 'unregTrainsLayer',
            'markerLayer', 'arrowMarkersLayer',
            'trainLayer', 'trainsLayer',
            'vehicleLayer', 'vehiclesLayer',
            'locoLayer', 'locomotivesLayer'
        ];
        
        layerNames.forEach(function(name) {
            if (window[name]) {
                var layer = window[name];
                results.layers[name] = {
                    exists: true,
                    type: layer.constructor ? layer.constructor.name : typeof layer,
                    hasSource: typeof layer.getSource === 'function'
                };
                if (layer.getSource) {
                    var src = layer.getSource();
                    results.layers[name + '_source'] = {
                        exists: true,
                        type: src.constructor ? src.constructor.name : typeof src,
                        hasGetFeatures: typeof src.getFeatures === 'function',
                        featureCount: src.getFeatures ? src.getFeatures().length : 0
                    };
                }
            }
        });
        
        // Check all map layers
        if (window.map) {
            window.map.getLayers().forEach(function(layer, index) {
                var layerInfo = {
                    index: index,
                    type: layer.constructor.name,
                    title: layer.get('title') || layer.get('name') || 'unknown'
                };
                
                if (layer.getSource) {
                    var src = layer.getSource();
                    layerInfo.hasSource = true;
                    layerInfo.sourceType = src.constructor.name;
                    layerInfo.featureCount = src.getFeatures ? src.getFeatures().length : 0;
                    
                    // Sample first feature
                    if (src.getFeatures && src.getFeatures().length > 0) {
                        var f = src.getFeatures()[0];
                        var props = f.getProperties();
                        layerInfo.sampleProps = Object.keys(props).slice(0, 10);
                    }
                }
                
                results.mapLayers.push(layerInfo);
            });
        }
        
        // Check global variables for anything train-related
        for (var key in window) {
            if (key.toLowerCase().includes('train') || 
                key.toLowerCase().includes('loco') || 
                key.toLowerCase().includes('vehicle') ||
                key.toLowerCase().includes('rail')) {
                try {
                    var val = window[key];
                    if (val && typeof val === 'object') {
                        results.globalVars.push({
                            name: key,
                            type: val.constructor ? val.constructor.name : typeof val,
                            length: val.length !== undefined ? val.length : 
                                   (val.getFeatures ? '(source)' : 'unknown')
                        });
                    }
                } catch(e) {}
            }
        }
        
        return results;
        """
        
        scan_results = driver.execute_script(scan_script)
        
        print("\n" + "="*60)
        print("📊 SOURCE SCAN RESULTS")
        print("="*60)
        
        print("\n🔹 NAMED SOURCES:")
        for name, info in scan_results.get('sources', {}).items():
            if info.get('exists'):
                print(f"   ✅ {name}: {info.get('featureCount', 0)} features")
            else:
                print(f"   ❌ {name}: not found")
        
        print("\n🔹 NAMED LAYERS:")
        for name, info in scan_results.get('layers', {}).items():
            if info.get('exists'):
                if 'featureCount' in info:
                    print(f"   ✅ {name}: {info.get('featureCount', 0)} features")
                else:
                    print(f"   ✅ {name}: exists")
        
        print("\n🔹 MAP LAYERS:")
        for layer in scan_results.get('mapLayers', []):
            print(f"   📍 Layer {layer.get('index')}: {layer.get('type')}")
            print(f"      Title: {layer.get('title')}")
            print(f"      Features: {layer.get('featureCount', 0)}")
            if layer.get('sampleProps'):
                print(f"      Sample props: {layer.get('sampleProps')}")
        
        print("\n🔹 TRAIN-RELATED GLOBAL VARIABLES:")
        for var in scan_results.get('globalVars', []):
            print(f"   🔸 {var.get('name')}: {var.get('type')} ({var.get('length')})")
        
        # Now try to extract from ANY source that has features
        print("\n" + "="*60)
        print("🔍 EXTRACTING FROM ALL SOURCES WITH FEATURES")
        print("="*60)
        
        extract_script = """
        var allTrains = [];
        var seenIds = new Set();
        
        function extractFromSource(src, sourceName) {
            if (!src) return;
            try {
                var features = src.getFeatures ? src.getFeatures() : [];
                console.log(sourceName + ' has ' + features.length + ' features');
                
                features.forEach(function(f) {
                    try {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            // Get ID from any property
                            var id = props.id || props.ID || 
                                    props.name || props.NAME ||
                                    props.loco || props.Loco ||
                                    props.unit || props.Unit ||
                                    props.trainId || props.TrainId ||
                                    f.getId ? f.getId() : null;
                            
                            if (!id) {
                                id = sourceName + '_' + allTrains.length;
                            }
                            
                            id = String(id).trim();
                            
                            // Australia bounds (in Web Mercator)
                            var x = coords[0];
                            var y = coords[1];
                            var lon = (x / 20037508.34) * 180;
                            var lat = (y / 20037508.34) * 180;
                            lat = 180 / 3.14159 * (2 * Math.atan(Math.exp(lat * 3.14159 / 180)) - 3.14159 / 2);
                            
                            if (lat >= -45 && lat <= -10 && lon >= 110 && lon <= 155) {
                                if (!seenIds.has(id)) {
                                    seenIds.add(id);
                                    allTrains.push({
                                        'id': id,
                                        'lat': coords[1],
                                        'lon': coords[0],
                                        'heading': Number(props.heading || props.Heading || 0),
                                        'speed': Number(props.speed || props.Speed || 0)
                                    });
                                }
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        }
        
        // Check all possible sources
        var sourceList = [
            window.regTrainsSource,
            window.unregTrainsSource,
            window.markerSource,
            window.arrowMarkersSource,
            window.regTrainsLayer ? window.regTrainsLayer.getSource() : null,
            window.unregTrainsLayer ? window.unregTrainsLayer.getSource() : null,
            window.markerLayer ? window.markerLayer.getSource() : null,
            window.arrowMarkersLayer ? window.arrowMarkersLayer.getSource() : null
        ];
        
        var sourceNames = [
            'regTrainsSource', 'unregTrainsSource',
            'markerSource', 'arrowMarkersSource',
            'regTrainsLayer', 'unregTrainsLayer',
            'markerLayer', 'arrowMarkersLayer'
        ];
        
        for (var i = 0; i < sourceList.length; i++) {
            extractFromSource(sourceList[i], sourceNames[i]);
        }
        
        return allTrains;
        """
        
        all_trains = driver.execute_script(extract_script)
        print(f"\n✅ Extracted {len(all_trains)} Australian trains")
        
        # Convert coordinates
        trains = []
        for t in all_trains:
            lat, lon = webmercator_to_latlon(t['lon'], t['lat'])
            if lat and lon:
                trains.append({
                    'id': t['id'],
                    'lat': round(lat, 6),
                    'lon': round(lon, 6),
                    'heading': round(float(t['heading']), 1),
                    'speed': round(float(t['speed']), 1)
                })
        
        print(f"✅ Processed {len(trains)} trains with coordinates")
        
        if trains:
            print(f"\n📋 First train: ID={trains[0]['id']} at {trains[0]['lat']}, {trains[0]['lon']}")
        
        return trains, f"ok - {len(trains)} trains"
        
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
