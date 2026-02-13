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
    print("🚂 RAILOPS - GITHUB ACTIONS READY")
    print("=" * 60)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        # Use ChromeDriver from system PATH (pre-installed on GitHub Actions)
        driver = webdriver.Chrome(options=chrome_options)
        
        print("\n📌 Logging in...")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Login
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.send_keys(TF_USERNAME)
        print("✅ Username entered")
        
        password = driver.find_element(By.ID, "pasS_word")
        password.send_keys(TF_PASSWORD)
        print("✅ Password entered")
        
        # Click login
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
        
        # Close warning
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
        time.sleep(15)
        
        # Extract trains
        print("\n🔍 Extracting trains...")
        
        script = """
        var trains = [];
        
        function getFeatures(src) {
            if (!src) return;
            try {
                var features = src.getFeatures();
                console.log('Found ' + features.length + ' features');
                features.forEach(function(f) {
                    try {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            trains.push({
                                'id': String(props.id || props.ID || props.name || 'train_' + trains.length),
                                'lat': coords[1],
                                'lon': coords[0],
                                'heading': Number(props.heading || props.Heading || 0),
                                'speed': Number(props.speed || props.Speed || 0)
                            });
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        }
        
        getFeatures(window.regTrainsSource);
        getFeatures(window.unregTrainsSource);
        
        return trains;
        """
        
        all_trains = driver.execute_script(script)
        print(f"\n✅ Extracted {len(all_trains)} total trains")
        
        # Filter to Australia
        australian = []
        seen = set()
        
        for t in all_trains:
            lat, lon = webmercator_to_latlon(t['lon'], t['lat'])
            if lat and lon:
                t['lat'] = round(lat, 6)
                t['lon'] = round(lon, 6)
                if -45 <= lat <= -10 and 110 <= lon <= 155:
                    if t['id'] not in seen:
                        seen.add(t['id'])
                        australian.append(t)
        
        print(f"✅ Found {len(australian)} Australian trains")
        
        if australian:
            print(f"\n📋 Sample train at {australian[0]['lat']}, {australian[0]['lon']}")
        
        return australian, f"ok - {len(australian)} trains"
        
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
