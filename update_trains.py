import os
import json
import datetime
import time
import math
import pickle
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

class TrainScraper:
    def __init__(self):
        self.driver = None
        
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        
        # Enable performance logging
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
        
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def save_cookies(self):
        with open(COOKIE_FILE, "wb") as f:
            pickle.dump(self.driver.get_cookies(), f)
        print("✅ Cookies saved")
    
    def load_cookies(self):
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "rb") as f:
                    cookies = pickle.load(f)
                self.driver.get("https://trainfinder.otenko.com")
                time.sleep(2)
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except:
                        pass
                print("✅ Cookies loaded")
                return True
            except:
                pass
        return False
    
    def random_delay(self, min_sec=0.5, max_sec=2):
        time.sleep(random.uniform(min_sec, max_sec))
    
    def check_session_valid(self):
        try:
            self.driver.get(TF_LOGIN_URL)
            self.random_delay(2, 3)
            if "login" in self.driver.current_url.lower():
                print("⚠️ Session expired")
                return False
            print("✅ Session valid")
            return True
        except:
            return False
    
    def force_fresh_login(self):
        print("\n🔐 Performing fresh login...")
        
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            print("🗑️ Removed old cookies")
        
        self.driver.delete_all_cookies()
        self.driver.get(TF_LOGIN_URL)
        self.random_delay(2, 4)
        
        try:
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            username.clear()
            for char in TF_USERNAME:
                username.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            print("✅ Username entered")
            
            self.random_delay(0.5, 1.5)
            
            password = self.driver.find_element(By.ID, "pasS_word")
            password.clear()
            for char in TF_PASSWORD:
                password.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            print("✅ Password entered")
            
            self.random_delay(1, 2)
            
            self.driver.execute_script("""
                var tables = document.getElementsByClassName('popup_table');
                for(var i = 0; i < tables.length; i++) {
                    if(tables[i].className.includes('login')) {
                        var elements = tables[i].getElementsByTagName('*');
                        for(var j = 0; j < elements.length; j++) {
                            if(elements[j].textContent.trim() === 'Log In') {
                                elements[j].click();
                                return true;
                            }
                        }
                    }
                }
                return false;
            """)
            print("✅ Login button clicked")
            
            time.sleep(5)
            
            self.driver.execute_script("""
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
            
            time.sleep(5)
            
            self.save_cookies()
            return True
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def login(self):
        if self.load_cookies():
            self.driver.get(TF_LOGIN_URL)
            self.random_delay(3, 5)
            if self.check_session_valid():
                print("✅ Session valid")
                return True
            else:
                print("⚠️ Saved session invalid, doing fresh login")
                return self.force_fresh_login()
        else:
            return self.force_fresh_login()
    
    def zoom_to_australia(self):
        self.random_delay(2, 4)
        self.driver.execute_script("""
            if (window.map) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 3000, maxZoom: 8 });
            }
        """)
        print("🌏 Zoomed to Australia")
    
    def find_all_sources(self):
        """Find ALL possible sources that might contain train data"""
        print("\n🔍 Searching for train data sources...")
        
        script = """
        var results = {
            'sources': [],
            'window_props': [],
            'map_layers': [],
            'data_vars': [],
            'feature_counts': {}
        };
        
        // 1. Check all OpenLayers sources
        var sourceNames = [
            'regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource',
            'trainSource', 'trainsSource', 'locomotiveSource', 'vehicleSource',
            'railSource', 'railTrainsSource', 'liveTrainsSource', 'trainLayerSource',
            'vectorSource', 'pointSource', 'featureSource', 'trainVectorSource',
            'trainMarkers', 'trainPoints', 'trainFeatures', 'allTrains',
            'positionSource', 'locationsSource', 'trackingSource'
        ];
        
        sourceNames.forEach(function(name) {
            if (window[name]) {
                results.sources.push(name);
                try {
                    if (window[name].getFeatures) {
                        var count = window[name].getFeatures().length;
                        results.feature_counts[name] = count;
                    } else if (window[name].length !== undefined) {
                        results.feature_counts[name] = window[name].length;
                    }
                } catch(e) {}
            }
        });
        
        // 2. Check all window properties for train-related data
        for (var key in window) {
            if (key.toLowerCase().includes('train') || key.toLowerCase().includes('loco') || 
                key.toLowerCase().includes('rail') || key.toLowerCase().includes('engine') ||
                key.toLowerCase().includes('locomotive') || key.toLowerCase().includes('service')) {
                try {
                    var value = window[key];
                    results.window_props.push(key);
                    if (value && typeof value === 'object') {
                        if (Array.isArray(value)) {
                            results.feature_counts['window.' + key] = value.length;
                        } else if (value.length !== undefined) {
                            results.feature_counts['window.' + key] = value.length;
                        }
                    }
                } catch(e) {}
            }
        }
        
        // 3. Check map layers
        if (window.map && window.map.getLayers) {
            try {
                var layers = window.map.getLayers();
                layers.forEach(function(layer, index) {
                    try {
                        var layerName = layer.get('name') || 'layer_' + index;
                        results.map_layers.push(layerName);
                        var source = layer.getSource();
                        if (source && source.getFeatures) {
                            var count = source.getFeatures().length;
                            results.feature_counts['map.' + layerName] = count;
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        }
        
        // 4. Look for any global data objects
        var commonDataVars = [
            'trainData', 'trains', 'locomotives', 'positions', 'trainPositions',
            'liveTrains', 'trainList', 'trainArray', 'railTrains', 'currentTrains',
            'allTrains', 'trainCollection', 'locomotiveData', 'serviceData',
            'trainInfo', 'trainDetails', 'locomotiveList'
        ];
        
        commonDataVars.forEach(function(name) {
            if (window[name]) {
                results.data_vars.push(name);
                if (Array.isArray(window[name])) {
                    results.feature_counts['data.' + name] = window[name].length;
                } else if (window[name] && typeof window[name] === 'object') {
                    // Count properties if it's an object
                    var count = 0;
                    for (var prop in window[name]) count++;
                    results.feature_counts['data.' + name + '_props'] = count;
                }
            }
        });
        
        // 5. Look for any script tags with JSON data
        var scripts = document.querySelectorAll('script[type="application/json"], script:not([src])');
        scripts.forEach(function(script, index) {
            try {
                var content = script.textContent;
                if (content && (content.includes('train') || content.includes('loco') || 
                    content.includes('position') || content.includes('track'))) {
                    results.feature_counts['script_' + index + '_length'] = content.length;
                }
            } catch(e) {}
        });
        
        return results;
        """
        
        try:
            sources = self.driver.execute_script(script)
            
            print(f"\n📊 Source Analysis:")
            print(f"   OpenLayers sources found: {len(sources.get('sources', []))}")
            for src in sources.get('sources', []):
                count = sources.get('feature_counts', {}).get(src, 'unknown')
                print(f"      - {src}: {count} features")
            
            if sources.get('window_props'):
                print(f"\n   Train-related window properties: {len(sources.get('window_props', []))}")
                for prop in sources.get('window_props', [])[:10]:  # Show first 10
                    count = sources.get('feature_counts', {}).get('window.' + prop, 'unknown')
                    print(f"      - window.{prop}: {count}")
            
            if sources.get('map_layers'):
                print(f"\n   Map layers: {len(sources.get('map_layers', []))}")
                for layer in sources.get('map_layers', [])[:5]:
                    count = sources.get('feature_counts', {}).get('map.' + layer, 'unknown')
                    print(f"      - {layer}: {count}")
            
            if sources.get('data_vars'):
                print(f"\n   Data variables: {len(sources.get('data_vars', []))}")
                for var in sources.get('data_vars', []):
                    count = sources.get('feature_counts', {}).get('data.' + var, 
                           sources.get('feature_counts', {}).get('data.' + var + '_props', 'unknown'))
                    print(f"      - {var}: {count}")
            
            return sources
        except Exception as e:
            print(f"❌ Error finding sources: {e}")
            return {}
    
    def extract_from_source(self, source_name):
        """Extract data from a specific source"""
        script = f"""
        var trains = [];
        var source = window.{source_name};
        
        if (!source) return trains;
        
        try {{
            // Handle different source types
            var features = [];
            if (source.getFeatures) {{
                features = source.getFeatures();
            }} else if (Array.isArray(source)) {{
                features = source;
            }} else if (source.features) {{
                features = source.features;
            }}
            
            features.forEach(function(item, index) {{
                try {{
                    var props = item.getProperties ? item.getProperties() : item;
                    var coords = null;
                    
                    // Get coordinates
                    if (item.getGeometry) {{
                        var geom = item.getGeometry();
                        if (geom && geom.getType() === 'Point') {{
                            coords = geom.getCoordinates();
                        }}
                    }} else if (item.lat !== undefined && item.lon !== undefined) {{
                        coords = [item.lon, item.lat];
                    }} else if (item.latitude !== undefined && item.longitude !== undefined) {{
                        coords = [item.longitude, item.latitude];
                    }}
                    
                    if (coords) {{
                        var trainData = {{
                            'id': props.id || props.ID || props.loco || props.Loco || 
                                   props.unit || props.Unit || props.train_number || 
                                   props.service || source_name + '_' + index,
                            'train_number': props.train_number || props.service || props.name || '',
                            'loco': props.loco || props.Loco || props.unit || props.Unit || '',
                            'operator': props.operator || props.Operator || '',
                            'origin': props.origin || props.Origin || props.from || props.From || '',
                            'destination': props.destination || props.Destination || props.to || props.To || '',
                            'speed': props.speed || props.Speed || 0,
                            'heading': props.heading || props.Heading || props.direction || 0,
                            'eta': props.eta || props.ETA || '',
                            'status': props.status || props.Status || '',
                            'type': props.type || props.Type || '',
                            'cars': props.cars || props.Cars || props.carriages || 0,
                            'length': props.length || props.Length || '',
                            'weight': props.weight || props.Weight || '',
                            'line': props.line || props.Line || props.route || '',
                            'track': props.track || props.Track || props.platform || '',
                            'next_stop': props.next_stop || props.NextStop || '',
                            'x': coords[0],
                            'y': coords[1]
                        }};
                        trains.push(trainData);
                    }}
                }} catch(e) {{}}
            }});
        }} catch(e) {{}}
        
        return trains;
        """
        
        try:
            return self.driver.execute_script(script)
        except:
            return []
    
    def webmercator_to_latlon(self, x, y):
        try:
            x = float(x)
            y = float(y)
            lon = (x / 20037508.34) * 180
            lat = (y / 20037508.34) * 180
            lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
            return round(lat, 6), round(lon, 6)
        except:
            return None, None
    
    def filter_australian_trains(self, raw_trains):
        australian_trains = []
        seen_ids = set()
        
        for t in raw_trains:
            lat, lon = self.webmercator_to_latlon(t.get('x', 0), t.get('y', 0))
            if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
                train_id = t.get('id', 'unknown')
                if train_id not in seen_ids:
                    seen_ids.add(train_id)
                    australian_trains.append({
                        'id': train_id,
                        'train_number': t.get('train_number', ''),
                        'loco': t.get('loco', ''),
                        'operator': t.get('operator', ''),
                        'origin': t.get('origin', ''),
                        'destination': t.get('destination', ''),
                        'speed': round(float(t.get('speed', 0)), 1),
                        'heading': round(float(t.get('heading', 0)), 1),
                        'eta': t.get('eta', ''),
                        'status': t.get('status', ''),
                        'type': t.get('type', ''),
                        'cars': t.get('cars', 0),
                        'length': t.get('length', ''),
                        'weight': t.get('weight', ''),
                        'line': t.get('line', ''),
                        'track': t.get('track', ''),
                        'next_stop': t.get('next_stop', ''),
                        'lat': lat,
                        'lon': lon
                    })
        
        return australian_trains
    
    def run(self):
        print("=" * 60)
        print("🚂 RAILOPS - TRAIN SCRAPER")
        print(f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        if not TF_USERNAME or not TF_PASSWORD:
            print("❌ Missing credentials")
            return [], "Missing credentials"
        
        try:
            self.setup_driver()
            
            if not self.login():
                return [], "Login failed"
            
            print("\n⏳ Waiting 30 seconds for map to stabilize...")
            time.sleep(30)
            
            self.zoom_to_australia()
            
            print("⏳ Waiting 60 seconds for trains to load...")
            time.sleep(60)
            
            # Find all possible data sources
            sources = self.find_all_sources()
            
            # Extract from each source that has data
            all_raw_trains = []
            
            # Check OpenLayers sources
            for source in sources.get('sources', []):
                count = sources.get('feature_counts', {}).get(source, 0)
                if count and count > 0:
                    print(f"\n📦 Extracting from {source} ({count} features)...")
                    trains = self.extract_from_source(source)
                    all_raw_trains.extend(trains)
                    print(f"   → Extracted {len(trains)} trains")
            
            # Check data variables
            for var in sources.get('data_vars', []):
                count = sources.get('feature_counts', {}).get('data.' + var, 0)
                if count and count > 0:
                    print(f"\n📦 Extracting from window.{var} ({count} items)...")
                    trains = self.extract_from_source(var)
                    all_raw_trains.extend(trains)
                    print(f"   → Extracted {len(trains)} trains")
            
            print(f"\n✅ Total raw positions extracted: {len(all_raw_trains)}")
            
            australian_trains = self.filter_australian_trains(all_raw_trains)
            
            print(f"\n✅ Australian trains: {len(australian_trains)}")
            
            if australian_trains:
                print(f"\n📋 Sample real train data:")
                sample = australian_trains[0]
                print(f"   ID: {sample['id']}")
                print(f"   Train Number: {sample['train_number']}")
                print(f"   Loco: {sample['loco']}")
                print(f"   Operator: {sample['operator']}")
                print(f"   Origin: {sample['origin']}")
                print(f"   Destination: {sample['destination']}")
                print(f"   Speed: {sample['speed']} km/h")
                print(f"   Heading: {sample['heading']}°")
                print(f"   ETA: {sample['eta']}")
                print(f"   Status: {sample['status']}")
                print(f"   Type: {sample['type']}")
                print(f"   Cars: {sample['cars']}")
                print(f"   Location: {sample['lat']:.4f}, {sample['lon']:.4f}")
            
            return australian_trains, f"ok - {len(australian_trains)} trains"
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return [], f"error: {type(e).__name__}"
        finally:
            if self.driver:
                self.random_delay(1, 2)
                self.driver.quit()
                print("👋 Browser closed")

def write_output(trains, note=""):
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains or []
    }
    
    if os.path.exists(OUT_FILE):
        backup_name = f"trains_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(OUT_FILE, 'r') as src:
                with open(backup_name, 'w') as dst:
                    dst.write(src.read())
            print(f"💾 Backup created: {backup_name}")
        except:
            pass
    
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"📝 Output: {len(trains or [])} trains, status: {note}")
    
    backups = sorted([f for f in os.listdir('.') if f.startswith('trains_backup_')])
    for old_backup in backups[:-5]:
        try:
            os.remove(old_backup)
        except:
            pass

def main():
    scraper = TrainScraper()
    trains, note = scraper.run()
    write_output(trains, note)
    
    if "error" in note:
        exit(1)
    else:
        exit(0)

if __name__ == "__main__":
    main()
