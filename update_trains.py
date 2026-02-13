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
    print("🚂 RAILOPS - TRAIN SCRAPER")
    print("=" * 60)
    
    chrome_options = Options()
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
        
        # Wait for map
        print("\n⏳ Waiting for map to load...")
        time.sleep(10)
        
        # Zoom to Australia
        print("🌏 Zooming to Australia...")
        driver.execute_script("""
            if (window.map) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 2000, maxZoom: 10 });
            }
        """)
        
        print("⏳ Waiting for Australian trains to load...")
        time.sleep(15)
        
        # Extract all trains
        print("\n🔍 Extracting trains...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        function extractFromSource(src, sourceName) {
            if (!src || !src.getFeatures) return;
            
            try {
                var features = src.getFeatures();
                
                features.forEach(function(f, index) {
                    try {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            var id = props.id || props.ID || 
                                    props.name || props.NAME ||
                                    props.loco || props.Loco ||
                                    props.unit || props.Unit ||
                                    props.trainName || props.trainNumber ||
                                    sourceName + '_' + index;
                            
                            id = String(id).trim();
                            
                            if (!seenIds.has(id)) {
                                seenIds.add(id);
                                allTrains.push({
                                    'id': id,
                                    'loco': props.loco || props.Loco || props.unit || props.Unit || '',
                                    'service': props.service || props.Service || props.trainNumber || '',
                                    'operator': props.operator || props.Operator || '',
                                    'x': coords[0],
                                    'y': coords[1],
                                    'heading': props.heading || props.Heading || 0,
                                    'speed': props.speed || props.Speed || 0,
                                    'destination': props.destination || props.Destination || '',
                                    'source': sourceName
                                });
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        }
        
        extractFromSource(window.regTrainsSource, 'reg');
        extractFromSource(window.unregTrainsSource, 'unreg');
        extractFromSource(window.markerSource, 'marker');
        extractFromSource(window.arrowMarkersSource, 'arrow');
        
        return allTrains;
        """
        
        all_trains = driver.execute_script(script)
        print(f"\n✅ Extracted {len(all_trains)} total trains")
        
        # Convert coordinates and filter to Australia
        trains = []
        for t in all_trains:
            lat, lon = webmercator_to_latlon(t['x'], t['y'])
            if lat and lon:
                if -45 <= lat <= -10 and 110 <= lon <= 155:
                    trains.append({
                        'id': t['id'],
                        'train_number': t['service'] or t['loco'] or t['id'],
                        'lat': round(lat, 6),
                        'lon': round(lon, 6),
                        'heading': round(float(t['heading']), 1),
                        'speed': round(float(t['speed']), 1)
                    })
        
        print(f"✅ Australian trains: {len(trains)}")
        return trains, f"ok - {len(trains)} trains"
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
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
