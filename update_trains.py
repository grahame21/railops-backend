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
        
        # Web Mercator to longitude
        lon = (x / 20037508.34) * 180
        
        # Web Mercator to latitude
        lat = (y / 20037508.34) * 180
        lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
        
        return lat, lon
    except:
        return None, None

def login_and_get_trains():
    """PRODUCTION VERSION - Extracts ALL trains from the map"""
    
    print("=" * 60)
    print("🚂 RAILOPS PRODUCTION SCRAPER - ALL TRAINS")
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
        
        # STEP 2: EXTRACT ALL TRAINS FROM ALL LAYERS
        print("\n🔍 Extracting ALL trains from map...")
        
        extract_script = """
        var allTrains = [];
        
        function extractFeatures(source) {
            if (!source || !source.getFeatures) return [];
            try {
                return source.getFeatures();
            } catch(e) {
                return [];
            }
        }
        
        if (window.map) {
            window.map.getLayers().forEach(function(layer) {
                // Check if layer has a source
                if (layer.getSource) {
                    var source = layer.getSource();
                    var features = extractFeatures(source);
                    
                    features.forEach(function(f) {
                        var props = f.getProperties();
                        var geom = f.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            // Try to find train identifiers
                            var id = props.id || 
                                    props.ID || 
                                    props.trainId || 
                                    props.TrainId || 
                                    props.unit || 
                                    props.Unit || 
                                    props.loco || 
                                    props.Loco || 
                                    props.name || 
                                    props.Name || 
                                    props.vehicle || 
                                    props.Vehicle || 
                                    'unknown';
                            
                            var heading = props.heading || 
                                        props.Heading || 
                                        props.rotation || 
                                        props.Rotation || 
                                        props.bearing || 
                                        props.Bearing || 
                                        props.direction || 
                                        props.Direction || 
                                        0;
                            
                            var speed = props.speed || 
                                      props.Speed || 
                                      props.velocity || 
                                      props.Velocity || 
                                      0;
                            
                            var operator = props.operator || 
                                         props.Operator || 
                                         props.company || 
                                         props.Company || 
                                         props.railway || 
                                         props.Railway || 
                                         '';
                            
                            var service = props.service || 
                                        props.Service || 
                                        props.trainNumber || 
                                        props.TrainNumber || 
                                        props.line || 
                                        props.Line || 
                                        '';
                            
                            allTrains.push({
                                id: String(id),
                                x: coords[0],
                                y: coords[1],
                                heading: heading,
                                speed: speed,
                                operator: operator,
                                service: service
                            });
                        }
                    });
                }
                
                // Check if layer has multiple sources (Group layers)
                if (layer.getLayers) {
                    var subLayers = layer.getLayers();
                    if (subLayers && subLayers.forEach) {
                        subLayers.forEach(function(subLayer) {
                            if (subLayer.getSource) {
                                var source = subLayer.getSource();
                                var features = extractFeatures(source);
                                
                                features.forEach(function(f) {
                                    var props = f.getProperties();
                                    var geom = f.getGeometry();
                                    
                                    if (geom && geom.getType() === 'Point') {
                                        var coords = geom.getCoordinates();
                                        var id = props.id || props.ID || props.unit || props.Unit || props.loco || props.Loco || props.name || props.Name || 'unknown';
                                        var heading = props.heading || props.Heading || props.rotation || props.Rotation || 0;
                                        var speed = props.speed || props.Speed || 0;
                                        var operator = props.operator || props.Operator || '';
                                        var service = props.service || props.Service || '';
                                        
                                        allTrains.push({
                                            id: String(id),
                                            x: coords[0],
                                            y: coords[1],
                                            heading: heading,
                                            speed: speed,
                                            operator: operator,
                                            service: service
                                        });
                                    }
                                });
                            }
                        });
                    }
                }
            });
        }
        
        // Also check for any global train data arrays
        if (window.trainData) {
            try {
                allTrains = allTrains.concat(window.trainData);
            } catch(e) {}
        }
        if (window.trains) {
            try {
                allTrains = allTrains.concat(window.trains);
            } catch(e) {}
        }
        if (window.markers) {
            try {
                allTrains = allTrains.concat(window.markers);
            } catch(e) {}
        }
        
        return allTrains;
        """
        
        features = driver.execute_script(extract_script)
        print(f"\n✅ Found {len(features)} total features on map")
        
        # Convert coordinates and build train list
        trains = []
        train_ids = set()  # Avoid duplicates
        
        for feature in features:
            # Convert coordinates from EPSG:3857 to lat/lon
            lat, lon = webmercator_to_latlon(feature['x'], feature['y'])
            
            if lat and lon and -90 <= lat <= 90 and -180 <= lon <= 180:
                train_id = str(feature.get('id', 'unknown'))
                
                # Avoid duplicates with same ID
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
            print("\n📋 Sample trains (first 5):")
            for i, sample in enumerate(trains[:5]):
                print(f"\n   Train {i+1}:")
                print(f"     ID: {sample['id']}")
                print(f"     Location: {sample['lat']}, {sample['lon']}")
                print(f"     Heading: {sample['heading']}°")
                print(f"     Speed: {sample['speed']}")
                print(f"     Operator: {sample['operator']}")
                print(f"     Service: {sample['service']}")
        
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
    print("🚂🚂🚂 RAILOPS - FINAL PRODUCTION VERSION 🚂🚂🚂")
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
