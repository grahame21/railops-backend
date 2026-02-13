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
    print("🚂 RAILOPS - PRODUCTION READY")
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
        
        # Extract trains with REAL IDs
        print("\n🔍 Extracting trains with real IDs...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        // Extract from a source
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
                            
                            // 🚂 REAL TRAIN ID - from the debug output!
                            var trainId = props.trainName || props.trainNumber || 
                                         props.name || props.labelContent || 
                                         props.id || props.ID;
                            
                            // If still no ID, use the source name + index
                            if (!trainId) {
                                trainId = sourceName + '_' + allTrains.length;
                            }
                            
                            trainId = String(trainId).trim();
                            
                            // Australia bounds (convert from Web Mercator)
                            var x = coords[0];
                            var y = coords[1];
                            var lon = (x / 20037508.34) * 180;
                            var lat = (y / 20037508.34) * 180;
                            lat = 180 / 3.14159 * (2 * Math.atan(Math.exp(lat * 3.14159 / 180)) - 3.14159 / 2);
                            
                            if (lat >= -45 && lat <= -10 && lon >= 110 && lon <= 155) {
                                if (!seenIds.has(trainId)) {
                                    seenIds.add(trainId);
                                    allTrains.push({
                                        'id': trainId,
                                        'loco': trainId,
                                        'name': String(props.trainName || ''),
                                        'number': String(props.trainNumber || ''),
                                        'speed': Number(props.trainSpeed || props.speed || 0),
                                        'heading': Number(props.heading || 0),
                                        'lat': coords[1],
                                        'lon': coords[0],
                                        'km': Number(props.trainKM || 0),
                                        'time': String(props.trainTime || ''),
                                        'date': String(props.trainDate || ''),
                                        'source': sourceName
                                    });
                                }
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        }
        
        // Get from all the sources we found
        extractFromSource(window.regTrainsSource, 'reg');
        extractFromSource(window.unregTrainsSource, 'unreg');
        extractFromSource(window.markerSource, 'marker');
        extractFromSource(window.arrowMarkersSource, 'arrow');
        
        if (window.regTrainsLayer) extractFromSource(window.regTrainsLayer.getSource(), 'reg_layer');
        if (window.unregTrainsLayer) extractFromSource(window.unregTrainsLayer.getSource(), 'unreg_layer');
        if (window.markerLayer) extractFromSource(window.markerLayer.getSource(), 'marker_layer');
        if (window.arrowMarkersLayer) extractFromSource(window.arrowMarkersLayer.getSource(), 'arrow_layer');
        
        return allTrains;
        """
        
        all_trains = driver.execute_script(script)
        print(f"\n✅ Extracted {len(all_trains)} Australian trains")
        
        # Convert coordinates and build final train list
        trains = []
        for t in all_trains:
            lat, lon = webmercator_to_latlon(t['lon'], t['lat'])
            if lat and lon:
                trains.append({
                    'id': t['id'],
                    'loco': t['loco'],
                    'name': t['name'],
                    'number': t['number'],
                    'lat': round(lat, 6),
                    'lon': round(lon, 6),
                    'speed': round(t['speed'], 1),
                    'heading': round(t['heading'], 1),
                    'km': round(t['km'], 1),
                    'time': t['time'],
                    'date': t['date']
                })
        
        print(f"✅ Processed {len(trains)} trains with real IDs")
        
        if trains:
            print(f"\n📋 First train details:")
            print(f"   ID: {trains[0]['id']}")
            print(f"   Location: {trains[0]['lat']}, {trains[0]['lon']}")
            print(f"   Speed: {trains[0]['speed']} km/h")
            print(f"   Heading: {trains[0]['heading']}°")
            if trains[0]['name']:
                print(f"   Name: {trains[0]['name']}")
            if trains[0]['number']:
                print(f"   Number: {trains[0]['number']}")
            if trains[0]['km']:
                print(f"   KM: {trains[0]['km']}")
        
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