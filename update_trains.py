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
from selenium.webdriver.common.action_chains import ActionChains

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
    print("🚂 RAILOPS - ULTIMATE AGGRESSIVE")
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
        
        # Check initial trains
        print("\n🔍 Checking for any trains...")
        initial_count = driver.execute_script("""
            var count = 0;
            if (window.regTrainsSource) count += window.regTrainsSource.getFeatures().length;
            if (window.unregTrainsSource) count += window.unregTrainsSource.getFeatures().length;
            if (window.markerSource) count += window.markerSource.getFeatures().length;
            if (window.arrowMarkersSource) count += window.arrowMarkersSource.getFeatures().length;
            return count;
        """)
        print(f"   Found {initial_count} total trains")
        
        if initial_count == 0:
            print("⚠️ No trains found - trying aggressive reload...")
            
            # Try multiple strategies to get trains
            strategies = [
                "window.location.reload();",
                "if (window.map) { window.map.getView().setZoom(3); }",
                """
                if (window.map) {
                    var australia = [110, -45, 155, -5];
                    var proj = window.map.getView().getProjection();
                    var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                    window.map.getView().fit(extent, { duration: 1000, maxZoom: 10 });
                }
                """,
                """
                var layers = window.map.getLayers().getArray();
                layers.forEach(function(l) {
                    if (l.getSource && l.getSource().getFeatures) {
                        var f = l.getSource().getFeatures();
                        console.log(l.get('name') + ': ' + f.length);
                    }
                });
                """
            ]
            
            for i, strategy in enumerate(strategies):
                print(f"   Strategy {i+1}: {strategy[:50]}...")
                driver.execute_script(strategy)
                time.sleep(5)
                
                new_count = driver.execute_script("return window.regTrainsSource ? window.regTrainsSource.getFeatures().length : 0;")
                if new_count > 0:
                    print(f"✅ Found {new_count} trains after strategy {i+1}")
                    break
        
        # Final extraction
        print("\n🔍 Extracting ALL trains...")
        
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
                            
                            // Get ID from any available field
                            var id = props.id || props.ID || 
                                    props.name || props.NAME ||
                                    props.loco || props.Loco ||
                                    props.unit || props.Unit ||
                                    props.trainName || props.trainNumber ||
                                    props.labelContent ||
                                    sourceName + '_' + index;
                            
                            id = String(id).trim();
                            
                            if (!seenIds.has(id)) {
                                seenIds.add(id);
                                allTrains.push({
                                    'id': id,
                                    'lat': coords[1],
                                    'lon': coords[0],
                                    'heading': props.heading || props.Heading || 0,
                                    'speed': props.speed || props.Speed || 0,
                                    'source': sourceName
                                });
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        }
        
        // Extract from ALL possible sources
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
        print(f"\n✅ Extracted {len(all_trains)} total trains")
        
        # Convert coordinates and show where they are
        trains_by_region = {'australia': 0, 'asia': 0, 'america': 0, 'other': 0}
        
        for t in all_trains:
            lat, lon = webmercator_to_latlon(t['lon'], t['lat'])
            if lat and lon:
                t['lat'] = lat
                t['lon'] = lon
                
                if -45 <= lat <= -10 and 110 <= lon <= 155:
                    trains_by_region['australia'] += 1
                elif 0 <= lat <= 30 and 95 <= lon <= 140:
                    trains_by_region['asia'] += 1
                elif 20 <= lat <= 50 and -130 <= lon <= -60:
                    trains_by_region['america'] += 1
                else:
                    trains_by_region['other'] += 1
        
        print(f"\n📊 Train distribution:")
        print(f"   Australia: {trains_by_region['australia']}")
        print(f"   Asia: {trains_by_region['asia']}")
        print(f"   Americas: {trains_by_region['america']}")
        print(f"   Other: {trains_by_region['other']}")
        
        # Filter to Australia only
        australian_trains = [t for t in all_trains if 
                            -45 <= t['lat'] <= -10 and 
                            110 <= t['lon'] <= 155]
        
        print(f"\n✅ Australian trains: {len(australian_trains)}")
        
        if australian_trains:
            print(f"\n📋 First Australian train:")
            t = australian_trains[0]
            print(f"   ID: {t['id']}")
            print(f"   Location: {t['lat']:.4f}, {t['lon']:.4f}")
            print(f"   Speed: {t['speed']} km/h")
            print(f"   Heading: {t['heading']}°")
            print(f"   Source: {t['source']}")
        
        return australian_trains, f"ok - {len(australian_trains)} trains"
        
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
