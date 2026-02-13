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
    print("🚂 RAILOPS - FIXED COORDINATE CONVERSION")
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
        
        # Take screenshot to verify we can see trains
        driver.save_screenshot('trainfinder_debug.png')
        print("✅ Screenshot saved as trainfinder_debug.png")
        
        # Extract all trains with proper coordinate conversion
        print("\n🔍 Extracting trains...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        function webMercatorToLatLon(x, y) {
            try {
                x = parseFloat(x);
                y = parseFloat(y);
                // Web Mercator to Lat/Lon conversion
                var lon = (x / 20037508.34) * 180;
                var lat = (y / 20037508.34) * 180;
                lat = 180 / Math.PI * (2 * Math.atan(Math.exp(lat * Math.PI / 180)) - Math.PI / 2);
                return [lat, lon];
            } catch(e) {
                return [null, null];
            }
        }
        
        function extractFromSource(src, sourceName) {
            if (!src || !src.getFeatures) {
                console.log(sourceName + ' source not found');
                return;
            }
            
            try {
                var features = src.getFeatures();
                console.log(sourceName + ' has ' + features.length + ' features');
                
                features.forEach(function(f, index) {
                    try {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            // CONVERT Web Mercator to Lat/Lon HERE
                            var latLon = webMercatorToLatLon(coords[0], coords[1]);
                            var lat = latLon[0];
                            var lon = latLon[1];
                            
                            // Skip if conversion failed
                            if (lat === null || lon === null) return;
                            
                            // Only include Australian trains
                            if (lat < -45 || lat > -10 || lon < 110 || lon > 155) return;
                            
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
                                    'lat': lat,           // NOW it's actual latitude
                                    'lon': lon,           // NOW it's actual longitude
                                    'heading': props.heading || props.Heading || 0,
                                    'speed': props.speed || props.Speed || 0,
                                    'destination': props.destination || props.Destination || '',
                                    'source': sourceName
                                });
                            }
                        }
                    } catch(e) {
                        console.log('Error processing feature:', e);
                    }
                });
            } catch(e) {
                console.log('Error accessing source:', e);
            }
        }
        
        // Debug - check if sources exist
        console.log('=== SOURCE CHECK ===');
        console.log('regTrainsSource exists:', !!window.regTrainsSource);
        console.log('unregTrainsSource exists:', !!window.unregTrainsSource);
        console.log('markerSource exists:', !!window.markerSource);
        console.log('arrowMarkersSource exists:', !!window.arrowMarkersSource);
        console.log('===================');
        
        extractFromSource(window.regTrainsSource, 'reg');
        extractFromSource(window.unregTrainsSource, 'unreg');
        extractFromSource(window.markerSource, 'marker');
        extractFromSource(window.arrowMarkersSource, 'arrow');
        
        return allTrains;
        """
        
        all_trains = driver.execute_script(script)
        print(f"\n✅ Extracted {len(all_trains)} total trains")
        
        # Debug - print first few raw trains
        if all_trains and len(all_trains) > 0:
            print("\n📋 First 5 trains (post-conversion):")
            for i, t in enumerate(all_trains[:5]):
                print(f"   Train {i+1}: ID={t.get('id', 'N/A')}")
                print(f"      Location: {t.get('lat', 'N/A'):.6f}, {t.get('lon', 'N/A'):.6f}")
                print(f"      Heading: {t.get('heading', 0)}°, Speed: {t.get('speed', 0)} km/h")
                if t.get('service'):
                    print(f"      Service: {t.get('service')}")
        else:
            print("⚠️ No trains extracted!")
            # Try to get page source for debugging
            html = driver.page_source
            with open('debug_page.html', 'w', encoding='utf-8') as f:
                f.write(html)
            print("📄 Page source saved to debug_page.html for inspection")
        
        # No need for further filtering since we already filtered in JavaScript
        trains = all_trains
        
        print(f"\n✅ Australian trains: {len(trains)}")
        
        if trains:
            print(f"\n📋 Sample Australian train:")
            t = trains[0]
            print(f"   ID: {t['id']}")
            print(f"   Loco: {t.get('loco', 'N/A')}")
            print(f"   Location: {t['lat']:.6f}, {t['lon']:.6f}")
            print(f"   Speed: {t.get('speed', 0)} km/h")
            print(f"   Heading: {t.get('heading', 0)}°")
            if t.get('service'):
                print(f"   Service: {t['service']}")
            if t.get('operator'):
                print(f"   Operator: {t['operator']}")
            if t.get('destination'):
                print(f"   Destination: {t['destination']}")
        
        return trains, f"ok - {len(trains)} trains"
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        # Save screenshot on error
        if driver:
            driver.save_screenshot('error_debug.png')
            print("📸 Error screenshot saved as error_debug.png")
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
