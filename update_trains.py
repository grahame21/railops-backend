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
    print(f"📝 Output: {len(trains or [])} trains")

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
    print("🚂 RAILOPS - GETTING REAL TRAIN IDs")
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
        
        # LOGIN
        print("\n📌 Logging in...")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        username = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.send_keys(TF_USERNAME)
        
        password = driver.find_element(By.ID, "pasS_word")
        password.send_keys(TF_PASSWORD)
        
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
        except:
            pass
        
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
        print("✅ Login clicked")
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
        print("✅ Warning closed")
        
        # ZOOM TO AUSTRALIA
        print("\n🌏 Zooming to Australia...")
        driver.execute_script("""
            if (window.map) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 1000, maxZoom: 10 });
            }
        """)
        time.sleep(12)  # Wait for trains to load
        
        # EXTRACT TRAINS
        print("\n🔍 Extracting REAL train data...")
        
        script = """
        var trains = [];
        var seen = new Set();
        
        function getLoco(props, f) {
            // Try every possible field name
            var loco = props.loco || props.Loco || 
                      props.unit || props.Unit ||
                      props.id || props.ID ||
                      props.name || props.Name ||
                      props.trainId || props.TrainId ||
                      props.locomotive || props.Locomotive ||
                      '';
            
            // If still not found, try feature ID
            if (!loco || loco.includes('Source') || loco.includes('Layer')) {
                loco = f.getId ? f.getId() : (f.id_ || f.id || '');
                loco = String(loco).replace(/^[^_]+[._]/, ''); // Remove prefix
            }
            
            return String(loco).trim();
        }
        
        function extractFromSource(source) {
            if (!source || !source.getFeatures) return;
            
            var features = source.getFeatures();
            features.forEach(function(f) {
                try {
                    var props = f.getProperties();
                    var geom = f.getGeometry();
                    
                    if (geom) {
                        var coords = geom.getCoordinates();
                        var lon = coords[0];
                        var lat = coords[1];
                        
                        // Australia only
                        if (lat >= -45 && lat <= -10 && lon >= 110 && lon <= 155) {
                            
                            var loco = getLoco(props, f);
                            
                            // Only add if we have a valid loco number
                            if (loco && !loco.includes('Source') && !loco.includes('Layer') && loco.length > 0) {
                                
                                if (!seen.has(loco)) {
                                    seen.add(loco);
                                    trains.push({
                                        'id': loco,
                                        'loco': loco,
                                        'lat': lat,
                                        'lon': lon,
                                        'heading': Number(props.heading || props.Heading || props.rotation || 0),
                                        'speed': Number(props.speed || props.Speed || 0),
                                        'operator': String(props.operator || props.Operator || props.railway || ''),
                                        'service': String(props.service || props.Service || props.trainNumber || ''),
                                        'destination': String(props.destination || props.Destination || props.to || ''),
                                        'line': String(props.line || props.Line || props.route || ''),
                                        'timestamp': String(props.timestamp || props.Timestamp || props.lastSeen || '')
                                    });
                                }
                            }
                        }
                    }
                } catch(e) {}
            });
        }
        
        // Extract from all sources
        var sources = [
            window.regTrainsSource,
            window.unregTrainsSource,
            window.regTrainsLayer ? window.regTrainsLayer.getSource() : null,
            window.unregTrainsLayer ? window.unregTrainsLayer.getSource() : null
        ];
        
        sources.forEach(extractFromSource);
        
        return trains;
        """
        
        trains = driver.execute_script(script)
        print(f"\n✅ Found {len(trains)} Australian trains with real IDs")
        
        if trains:
            print("\n📋 Sample train:")
            sample = trains[0]
            print(f"   Loco: {sample.get('loco')}")
            print(f"   Heading: {sample.get('heading')}°")
            print(f"   Speed: {sample.get('speed')} km/h")
            print(f"   Operator: {sample.get('operator')}")
            print(f"   Service: {sample.get('service')}")
        
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
