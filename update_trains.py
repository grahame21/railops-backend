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

def login_and_get_trains():
    print("=" * 60)
    print("🚂 RAILOPS - ENHANCED DATA EXTRACTION")
    print("=" * 60)
    
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
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
        
        # Wait for map
        print("\n⏳ Waiting for map...")
        time.sleep(30)
        
        # Zoom to Australia
        print("🌏 Zooming to Australia...")
        driver.execute_script("""
            if (window.map) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 3000, maxZoom: 8 });
            }
        """)
        
        print("⏳ Waiting for trains to load...")
        time.sleep(60)
        
        # ENHANCED extraction - try to get more details
        print("\n🔍 Extracting train details...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        function extractFromSource(src, sourceName) {
            if (!src || !src.getFeatures) return;
            
            try {
                var features = src.getFeatures();
                console.log(sourceName + ' has ' + features.length + ' features');
                
                features.forEach(function(f, index) {
                    try {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            // Convert to lat/lon
                            var x = coords[0];
                            var y = coords[1];
                            var lon = (x / 20037508.34) * 180;
                            var lat = (y / 20037508.34) * 180;
                            lat = 180 / 3.14159 * (2 * Math.atan(Math.exp(lat * 3.14159 / 180)) - 3.14159 / 2);
                            
                            // Australia bounds
                            if (lat >= -45 && lat <= -5 && lon >= 110 && lon <= 160) {
                                
                                // Try to get a meaningful ID
                                var id = props.id || props.ID || 
                                        props.name || props.NAME ||
                                        props.loco || props.Loco ||
                                        props.unit || props.Unit ||
                                        props.trainId || props.TrainId ||
                                        sourceName + '_' + index;
                                
                                id = String(id).trim();
                                
                                if (!seenIds.has(id)) {
                                    seenIds.add(id);
                                    
                                    // Look for train details in all properties
                                    var train = {
                                        'id': id,
                                        'lat': lat,
                                        'lon': lon,
                                        'speed': Number(props.speed || props.Speed || props.spd || props.Spd || 0),
                                        'heading': Number(props.heading || props.Heading || props.dir || props.Dir || 0)
                                    };
                                    
                                    // Try to find train number (could be in various fields)
                                    if (props.trainNumber || props.TrainNumber) {
                                        train['train_number'] = String(props.trainNumber || props.TrainNumber);
                                    }
                                    if (props.train_id || props.TrainId) {
                                        train['train_id'] = String(props.train_id || props.TrainId);
                                    }
                                    
                                    // Try to find operator
                                    if (props.operator || props.Operator) {
                                        train['operator'] = String(props.operator || props.Operator);
                                    }
                                    if (props.oper || props.Oper) {
                                        train['operator'] = String(props.oper || props.Oper);
                                    }
                                    
                                    // Try to find destination
                                    if (props.destination || props.Destination) {
                                        train['destination'] = String(props.destination || props.Destination);
                                    }
                                    if (props.dest || props.Dest) {
                                        train['destination'] = String(props.dest || props.Dest);
                                    }
                                    
                                    // Try to find timestamp
                                    if (props.timestamp || props.Timestamp) {
                                        train['timestamp'] = String(props.timestamp || props.Timestamp);
                                    }
                                    if (props.time || props.Time) {
                                        train['timestamp'] = String(props.time || props.Time);
                                    }
                                    
                                    // Also look for any other useful fields
                                    if (props.service || props.Service) {
                                        train['service'] = String(props.service || props.Service);
                                    }
                                    if (props.type || props.Type) {
                                        train['type'] = String(props.type || props.Type);
                                    }
                                    if (props.status || props.Status) {
                                        train['status'] = String(props.status || props.Status);
                                    }
                                    
                                    allTrains.push(train);
                                }
                            }
                        }
                    } catch(e) {
                        console.log('Error processing feature:', e);
                    }
                });
            } catch(e) {}
        }
        
        // Extract from all sources
        extractFromSource(window.regTrainsSource, 'reg');
        extractFromSource(window.unregTrainsSource, 'unreg');
        extractFromSource(window.markerSource, 'marker');
        extractFromSource(window.arrowMarkersSource, 'arrow');
        
        return allTrains;
        """
        
        trains = driver.execute_script(script)
        print(f"\n✅ Extracted {len(trains)} Australian trains")
        
        if trains and len(trains) > 0:
            print(f"\n📋 Sample train (first one):")
            t = trains[0]
            print(f"   ID: {t.get('id', 'N/A')}")
            print(f"   Speed: {t.get('speed', 'N/A')} km/h")
            print(f"   Heading: {t.get('heading', 'N/A')}°")
            print(f"   Train number: {t.get('train_number', 'Not found')}")
            print(f"   Train ID: {t.get('train_id', 'Not found')}")
            print(f"   Operator: {t.get('operator', 'Not found')}")
            print(f"   Destination: {t.get('destination', 'Not found')}")
            print(f"   Timestamp: {t.get('timestamp', 'Not found')}")
            print(f"   Location: {t.get('lat', 0):.4f}, {t.get('lon', 0):.4f}")
        
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
