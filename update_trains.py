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
    print("🚂 RAILOPS - ULTRA PATIENT VERSION")
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
        
        # Wait for map to fully initialize
        print("\n⏳ Waiting 30 seconds for map to stabilize...")
        time.sleep(30)
        
        # Zoom to Australia multiple times
        print("🌏 Zooming to Australia (slowly)...")
        driver.execute_script("""
            if (window.map) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 3000, maxZoom: 8 });
            }
        """)
        
        # Wait a LONG time for trains to load
        print("⏳ Waiting 60 seconds for Australian trains to load...")
        time.sleep(60)
        
        # Extract trains
        print("\n🔍 Extracting trains...")
        
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
                            
                            // Convert to lat/lon for Australia check
                            var x = coords[0];
                            var y = coords[1];
                            var lon = (x / 20037508.34) * 180;
                            var lat = (y / 20037508.34) * 180;
                            lat = 180 / 3.14159 * (2 * Math.atan(Math.exp(lat * 3.14159 / 180)) - 3.14159 / 2);
                            
                            // Australia bounds (expanded slightly)
                            if (lat >= -45 && lat <= -5 && lon >= 110 && lon <= 160) {
                                
                                var id = props.id || props.ID || 
                                        props.name || props.NAME ||
                                        props.loco || props.Loco ||
                                        props.unit || props.Unit ||
                                        props.trainId || props.TrainId ||
                                        sourceName + '_' + index;
                                
                                id = String(id).trim();
                                
                                if (!seenIds.has(id)) {
                                    seenIds.add(id);
                                    allTrains.push({
                                        'id': id,
                                        'train_id': String(props.trainId || props.TrainId || props.trainNumber || ''),
                                        'service': String(props.service || props.Service || ''),
                                        'operator': String(props.operator || props.Operator || ''),
                                        'lat': lat,
                                        'lon': lon,
                                        'heading': Number(props.heading || props.Heading || 0),
                                        'speed': Number(props.speed || props.Speed || 0),
                                        'destination': String(props.destination || props.Destination || ''),
                                        'timestamp': String(props.timestamp || props.Timestamp || '')
                                    });
                                }
                            }
                        }
                    } catch(e) {}
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
        
        if trains:
            print(f"\n📋 Sample train:")
            t = trains[0]
            print(f"   ID: {t['id']}")
            print(f"   Location: {t['lat']:.4f}, {t['lon']:.4f}")
        
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
