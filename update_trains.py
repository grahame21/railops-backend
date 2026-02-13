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
        lon = (x / 20037508.34) * 180
        lat = (y / 20037508.34) * 180
        lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
        return lat, lon
    except:
        return None, None

def login_and_get_trains():
    """FINAL VERSION - Get ALL trains from ALL sources"""
    
    print("=" * 60)
    print("🚂 RAILOPS - FINAL: GET ALL 92+ TRAINS")
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
        
        # STEP 2: GET ALL TRAINS FROM THE MAP OBJECT DIRECTLY
        print("\n🔍 Getting ALL trains from map object...")
        
        extract_script = """
        var allFeatures = [];
        var seenIds = new Set();
        
        // Try to get the TrainTracker or map object
        if (window.TrainTracker) {
            console.log('Found TrainTracker');
        }
        
        // Check all known source objects
        var sourceNames = [
            'regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource',
            'regTrainsLayer', 'unregTrainsLayer', 'markerLayer', 'arrowMarkersLayer'
        ];
        
        sourceNames.forEach(function(name) {
            var obj = window[name];
            if (!obj) return;
            
            // Try to get features directly from the object
            try {
                // If it's a layer, get its source
                if (obj.getSource) {
                    obj = obj.getSource();
                }
                
                // Try all possible methods to get features
                var features = null;
                
                if (obj.getFeatures) {
                    features = obj.getFeatures();
                } else if (obj.getFeaturesArray) {
                    features = obj.getFeaturesArray();
                } else if (obj.features) {
                    features = obj.features;
                } else if (obj.features_) {
                    features = obj.features_;
                } else if (obj.A) {
                    features = obj.A;
                } else if (obj.array_) {
                    features = obj.array_;
                }
                
                if (features && features.length) {
                    console.log(name + ' has ' + features.length + ' features');
                    
                    features.forEach(function(f) {
                        try {
                            // Get properties
                            var props = {};
                            if (f.getProperties) {
                                props = f.getProperties();
                            } else if (f.values_) {
                                props = f.values_;
                            } else if (f.properties_) {
                                props = f.properties_;
                            } else if (f.attributes) {
                                props = f.attributes;
                            }
                            
                            // Get geometry
                            var geom = null;
                            if (f.getGeometry) {
                                geom = f.getGeometry();
                            } else if (f.geometry_) {
                                geom = f.geometry_;
                            } else if (f.geom) {
                                geom = f.geom;
                            }
                            
                            if (geom) {
                                // Get coordinates
                                var coords = null;
                                if (geom.getCoordinates) {
                                    coords = geom.getCoordinates();
                                } else if (geom.coordinates_) {
                                    coords = geom.coordinates_;
                                } else if (geom.coords) {
                                    coords = geom.coords;
                                }
                                
                                if (coords && coords.length >= 2) {
                                    var id = String(props.id || props.ID || props.name || 
                                                  props.NAME || props.unit || props.Unit || 
                                                  props.loco || props.Loco || name + '_' + allFeatures.length);
                                    
                                    if (!seenIds.has(id)) {
                                        seenIds.add(id);
                                        allFeatures.push({
                                            id: id,
                                            x: coords[0],
                                            y: coords[1],
                                            heading: Number(props.heading || props.Heading || 0),
                                            speed: Number(props.speed || props.Speed || 0),
                                            operator: String(props.operator || props.Operator || ''),
                                            service: String(props.service || props.Service || props.trainNumber || '')
                                        });
                                    }
                                }
                            }
                        } catch(e) {}
                    });
                }
            } catch(e) {
                console.log('Error with ' + name + ': ' + e);
            }
        });
        
        return allFeatures;
        """
        
        train_features = driver.execute_script(extract_script)
        print(f"\n✅ Found {len(train_features)} train features from all sources")
        
        # Convert coordinates and build train list
        trains = []
        
        for feature in train_features:
            lat, lon = webmercator_to_latlon(feature['x'], feature['y'])
            
            if lat and lon and -90 <= lat <= 90 and -180 <= lon <= 180:
                train = {
                    "id": str(feature.get('id', 'unknown')),
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "heading": round(to_float(feature.get('heading', 0)), 1),
                    "speed": round(to_float(feature.get('speed', 0)), 1),
                    "operator": feature.get('operator', '')[:50],
                    "service": feature.get('service', '')[:50]
                }
                trains.append(train)
        
        print(f"\n📊 Total unique trains extracted: {len(trains)}")
        
        # Categorize by region
        aus_trains = [t for t in trains if 110 <= t['lon'] <= 155 and -45 <= t['lat'] <= -10]
        us_trains = [t for t in trains if -130 <= t['lon'] <= -60 and 25 <= t['lat'] <= 50]
        
        print(f"\n📍 Australian trains: {len(aus_trains)}")
        print(f"📍 US trains: {len(us_trains)}")
        print(f"📍 Other: {len(trains) - len(aus_trains) - len(us_trains)}")
        
        if trains:
            print("\n📋 First 10 trains:")
            for i, sample in enumerate(trains[:10]):
                region = "AUS" if 110 <= sample['lon'] <= 155 and -45 <= sample['lat'] <= -10 else "USA" if -130 <= sample['lon'] <= -60 and 25 <= sample['lat'] <= 50 else "Other"
                print(f"\n   Train {i+1} [{region}]:")
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
    print("🚂🚂🚂 RAILOPS - FINAL VERSION 🚂🚂🚂")
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
