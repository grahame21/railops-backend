import os
import json
import datetime
import time
import math
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, JavascriptException

OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

class TrainScraper:
    def __init__(self):
        self.driver = None
        self.trains = []
        
    def setup_driver(self):
        """Configure Chrome driver for optimal performance"""
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Add these for faster loading
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--disable-extensions')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Hide webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def save_cookies(self):
        """Save cookies for future sessions"""
        if self.driver:
            with open(COOKIE_FILE, "wb") as f:
                pickle.dump(self.driver.get_cookies(), f)
            print("✅ Cookies saved")
    
    def load_cookies(self):
        """Load saved cookies to skip login"""
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "rb") as f:
                    cookies = pickle.load(f)
                
                # First navigate to domain
                self.driver.get("https://trainfinder.otenko.com")
                time.sleep(2)
                
                # Add cookies
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except:
                        pass
                
                print("✅ Cookies loaded")
                return True
            except Exception as e:
                print(f"⚠️ Couldn't load cookies: {e}")
        return False
    
    def login(self):
        """Handle login with retry logic"""
        print("\n📌 Attempting login...")
        
        try:
            self.driver.get(TF_LOGIN_URL)
            time.sleep(3)
            
            # Check if already logged in
            if "home/nextlevel" in self.driver.current_url and "login" not in self.driver.current_url.lower():
                print("✅ Already logged in")
                return True
            
            # Find and fill login form
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            username.clear()
            username.send_keys(TF_USERNAME)
            
            password = self.driver.find_element(By.ID, "pasS_word")
            password.clear()
            password.send_keys(TF_PASSWORD)
            
            # Click login button via JavaScript (more reliable)
            self.driver.execute_script("""
                var buttons = document.querySelectorAll('input[type="button"], button');
                for(var i = 0; i < buttons.length; i++) {
                    if(buttons[i].value === 'Log In' || buttons[i].textContent.includes('Log In')) {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
            """)
            
            time.sleep(5)
            
            # Check login success
            if "home/nextlevel" in self.driver.current_url:
                print("✅ Login successful")
                self.save_cookies()
                return True
            else:
                print("❌ Login failed")
                return False
                
        except TimeoutException:
            print("❌ Login timeout")
            return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def close_warning(self):
        """Close any warning popups"""
        try:
            self.driver.execute_script("""
                // Try multiple methods to close warning
                var closeButtons = document.querySelectorAll('button[aria-label="Close"], .close-button, .modal-close, .popup-close');
                for(var i = 0; i < closeButtons.length; i++) {
                    closeButtons[i].click();
                }
                
                // Try the path method from your original code
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
            print("✅ Warning popups closed")
            time.sleep(2)
        except:
            pass  # No warning to close
    
    def zoom_to_australia(self):
        """Zoom map to show all Australian trains"""
        try:
            self.driver.execute_script("""
                if (window.map) {
                    var australia = [112, -44, 154, -10];
                    try {
                        var proj = window.map.getView().getProjection();
                        var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                        window.map.getView().fit(extent, { duration: 1000, maxZoom: 8 });
                        return true;
                    } catch(e) {
                        console.log('Map zoom error:', e);
                        return false;
                    }
                }
                return false;
            """)
            print("🌏 Zoomed to Australia")
            time.sleep(5)
        except:
            print("⚠️ Couldn't zoom map")
    
    def trigger_train_load(self):
        """Try to trigger train loading via various methods"""
        print("\n🔄 Attempting to trigger train loading...")
        
        script = """
        var results = [];
        
        // Method 1: Check for any refresh/update buttons
        var refreshButtons = document.querySelectorAll('button[title*="Refresh"], button[aria-label*="Refresh"], .refresh-button, .update-button');
        refreshButtons.forEach(function(btn) {
            results.push('Found refresh button');
            btn.click();
        });
        
        // Method 2: Try to trigger any train update functions
        if (typeof updateTrains === 'function') {
            updateTrains();
            results.push('Called updateTrains()');
        }
        if (typeof loadTrains === 'function') {
            loadTrains();
            results.push('Called loadTrains()');
        }
        if (typeof refreshTrains === 'function') {
            refreshTrains();
            results.push('Called refreshTrains()');
        }
        
        // Method 3: Try to trigger via map events
        if (window.map) {
            window.map.dispatchEvent('moveend');
            results.push('Dispatched moveend event');
        }
        
        return results;
        """
        
        try:
            results = self.driver.execute_script(script)
            if results:
                print(f"   Triggered: {', '.join(results)}")
            else:
                print("   No train loading triggers found")
        except Exception as e:
            print(f"   Error triggering train load: {e}")
    
    def debug_map_features(self):
        """Debug what features are actually in the map sources"""
        print("\n🔍 Debugging map features...")
        
        script = """
        var debug = {
            'regTrainsSource': [],
            'unregTrainsSource': [],
            'markerSource': [],
            'arrowMarkersSource': []
        };
        
        function inspectSource(source, sourceName) {
            if (!source || typeof source.getFeatures !== 'function') return [];
            
            var features = [];
            try {
                var feats = source.getFeatures();
                feats.forEach(function(feature, index) {
                    try {
                        var props = feature.getProperties();
                        var geom = feature.getGeometry();
                        var featureInfo = {
                            'index': index,
                            'type': geom ? geom.getType() : 'unknown',
                            'props': {}
                        };
                        
                        if (geom && geom.getType() === 'Point') {
                            featureInfo.coords = geom.getCoordinates();
                        }
                        
                        // Get a few key properties
                        var propNames = ['id', 'ID', 'loco', 'Loco', 'unit', 'Unit', 
                                       'name', 'NAME', 'service', 'Service'];
                        propNames.forEach(function(name) {
                            if (props[name] !== undefined) {
                                featureInfo.props[name] = props[name];
                            }
                        });
                        
                        features.push(featureInfo);
                    } catch(e) {
                        features.push({'error': String(e)});
                    }
                });
            } catch(e) {}
            return features;
        }
        
        debug.regTrainsSource = inspectSource(window.regTrainsSource, 'regTrainsSource');
        debug.unregTrainsSource = inspectSource(window.unregTrainsSource, 'unregTrainsSource');
        debug.markerSource = inspectSource(window.markerSource, 'markerSource');
        debug.arrowMarkersSource = inspectSource(window.arrowMarkersSource, 'arrowMarkersSource');
        
        return debug;
        """
        
        try:
            debug_info = self.driver.execute_script(script)
            
            total_features = 0
            for source_name, features in debug_info.items():
                if features:
                    print(f"\n   {source_name}: {len(features)} features")
                    for feat in features[:3]:  # Show first 3 features
                        print(f"      - Type: {feat.get('type', 'unknown')}")
                        if 'coords' in feat:
                            # Convert to lat/lon for easier understanding
                            x, y = feat['coords']
                            lon = (x / 20037508.34) * 180
                            print(f"        Coords (Web Mercator): {feat['coords']}")
                            print(f"        Approx lat/lon: ({y:.2f}°, {lon:.2f}°)")
                        if feat.get('props'):
                            print(f"        Props: {feat['props']}")
                    total_features += len(features)
            
            print(f"\n   Total features: {total_features}")
            return debug_info
        except Exception as e:
            print(f"❌ Error debugging features: {e}")
            return None
    
    def wait_for_trains_simple(self, max_wait=60):
        """Wait for trains to appear, with periodic triggering"""
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains to load...")
        
        start_time = time.time()
        last_trigger = 0
        
        while time.time() - start_time < max_wait:
            try:
                # Check map features count
                script = """
                var total = 0;
                var sources = ['regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource'];
                sources.forEach(function(name) {
                    if (window[name] && window[name].getFeatures) {
                        total += window[name].getFeatures().length;
                    }
                });
                return total;
                """
                
                feature_count = self.driver.execute_script(script)
                
                # If we have more than 1 feature, we likely have trains
                if feature_count > 1:
                    print(f"\n✅ Map has {feature_count} features loaded")
                    return True
                
                # Try to trigger train loading every 10 seconds
                if time.time() - last_trigger > 10:
                    self.trigger_train_load()
                    last_trigger = time.time()
                
            except (StaleElementReferenceException, JavascriptException):
                pass  # Ignore and retry
            
            time.sleep(2)
            print(".", end="", flush=True)
        
        print("\n⚠️ Timeout waiting for trains")
        return False
    
    def extract_trains_from_map_features(self):
        """Extract from OpenLayers sources"""
        print("\n🔍 Extracting trains from map features...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        function extractFromSource(source, sourceName) {
            if (!source || typeof source.getFeatures !== 'function') return [];
            
            var trains = [];
            try {
                var features = source.getFeatures();
                features.forEach(function(feature, index) {
                    try {
                        var props = feature.getProperties();
                        var geom = feature.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            // Skip if this looks like the South America point we saw
                            var x = coords[0];
                            var y = coords[1];
                            
                            // Rough Web Mercator bounds for Australia
                            // Australia in Web Mercator: x ~11500000 to 17000000, y ~-5500000 to -1100000
                            if (x > 11000000 && x < 17500000 && y < -1000000 && y > -6000000) {
                                var id = props.id || props.ID || props.loco || props.Loco || 
                                        props.unit || props.Unit || props.name || props.NAME ||
                                        sourceName + '_' + index;
                                
                                if (!seenIds.has(id)) {
                                    seenIds.add(id);
                                    
                                    var trainNumber = props.service || props.Service || 
                                                     props.trainNumber || props.train_number || '';
                                    
                                    trains.push({
                                        'id': String(id).trim(),
                                        'train_number': String(trainNumber).trim() || String(id).trim(),
                                        'x': coords[0],
                                        'y': coords[1],
                                        'heading': props.heading || props.Heading || 0,
                                        'speed': props.speed || props.Speed || 0
                                    });
                                }
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
            return trains;
        }
        
        var sourceNames = ['regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource'];
        sourceNames.forEach(function(name) {
            try {
                if (window[name]) {
                    var trains = extractFromSource(window[name], name);
                    allTrains = allTrains.concat(trains);
                }
            } catch(e) {}
        });
        
        return allTrains;
        """
        
        try:
            all_trains = self.driver.execute_script(script)
            print(f"✅ Extracted {len(all_trains)} trains from map features")
            return all_trains
        except Exception as e:
            print(f"❌ Error extracting map features: {e}")
            return []
    
    def extract_trains_from_currentTrains(self):
        """Extract train data from the currentTrains global variable"""
        print("\n🔍 Extracting trains from currentTrains variable...")
        
        script = """
        var trains = [];
        
        try {
            if (window.currentTrains) {
                console.log('currentTrains type:', typeof window.currentTrains);
                
                // Handle if it's an array
                if (Array.isArray(window.currentTrains)) {
                    window.currentTrains.forEach(function(item, index) {
                        try {
                            var lat = item.lat || item.latitude || (item.coords && item.coords[1]);
                            var lon = item.lon || item.longitude || (item.coords && item.coords[0]);
                            
                            if (lat && lon) {
                                var id = item.id || item.ID || item.trainId || item.unit || 
                                        item.loco || 'train_' + index;
                                var trainNumber = item.service || item.trainNumber || item.name || 
                                                 item.number || item.train_number || '';
                                
                                trains.push({
                                    'id': String(id).trim(),
                                    'train_number': String(trainNumber).trim() || String(id).trim(),
                                    'x': parseFloat(lon),
                                    'y': parseFloat(lat),
                                    'heading': parseFloat(item.heading || item.direction || 0),
                                    'speed': parseFloat(item.speed || item.velocity || 0)
                                });
                            }
                        } catch(e) {}
                    });
                }
                // Handle if it's an object with train IDs as keys
                else if (typeof window.currentTrains === 'object') {
                    for (var key in window.currentTrains) {
                        try {
                            var item = window.currentTrains[key];
                            var lat = item.lat || item.latitude || (item.coords && item.coords[1]);
                            var lon = item.lon || item.longitude || (item.coords && item.coords[0]);
                            
                            if (lat && lon) {
                                var id = item.id || item.ID || key;
                                var trainNumber = item.service || item.trainNumber || item.name || '';
                                
                                trains.push({
                                    'id': String(id).trim(),
                                    'train_number': String(trainNumber).trim() || String(id).trim(),
                                    'x': parseFloat(lon),
                                    'y': parseFloat(lat),
                                    'heading': parseFloat(item.heading || item.direction || 0),
                                    'speed': parseFloat(item.speed || item.velocity || 0)
                                });
                            }
                        } catch(e) {}
                    }
                }
            }
        } catch(e) {}
        
        return trains;
        """
        
        try:
            trains = self.driver.execute_script(script)
            print(f"✅ Found {len(trains)} trains in currentTrains")
            return trains
        except Exception as e:
            print(f"❌ Error extracting from currentTrains: {e}")
            return []
    
    def webmercator_to_latlon(self, x, y):
        """Convert Web Mercator coordinates to lat/lon"""
        try:
            x = float(x)
            y = float(y)
            lon = (x / 20037508.34) * 180
            lat = (y / 20037508.34) * 180
            lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
            return round(lat, 6), round(lon, 6)
        except (ValueError, TypeError):
            return None, None
    
    def filter_australian_trains(self, raw_trains):
        """Filter trains to Australia and convert coordinates"""
        australian_trains = []
        seen_ids = set()
        
        print("\n🔍 Filtering trains to Australia...")
        
        for i, t in enumerate(raw_trains):
            x = t.get('x')
            y = t.get('y')
            
            if x is None or y is None:
                print(f"   Train {i}: Missing coordinates")
                continue
            
            # Check if coordinates are likely Web Mercator (large numbers)
            if abs(x) > 180 or abs(y) > 90:
                lat, lon = self.webmercator_to_latlon(x, y)
                coord_type = "Web Mercator"
            else:
                # Already in lat/lon
                lat, lon = float(y), float(x)
                coord_type = "Lat/Lon"
            
            if lat and lon:
                in_australia = -45 <= lat <= -9 and 110 <= lon <= 155
                print(f"   Train {i}: {coord_type} -> ({lat:.4f}, {lon:.4f}) - {'IN' if in_australia else 'OUT'} Australia")
                
                if in_australia:
                    train_id = t.get('id', 'unknown')
                    
                    if train_id not in seen_ids:
                        seen_ids.add(train_id)
                        australian_trains.append({
                            'id': train_id,
                            'train_number': t.get('train_number', train_id),
                            'lat': lat,
                            'lon': lon,
                            'heading': round(float(t.get('heading', 0)), 1),
                            'speed': round(float(t.get('speed', 0)), 1)
                        })
            else:
                print(f"   Train {i}: Invalid coordinates ({x}, {y})")
        
        return australian_trains
    
    def run(self):
        """Main execution method"""
        print("=" * 60)
        print("🚂 RAILOPS - TRAIN SCRAPER")
        print(f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        if not TF_USERNAME or not TF_PASSWORD:
            print("❌ Missing credentials in environment")
            return [], "error: missing credentials"
        
        try:
            # Setup
            self.setup_driver()
            
            # Try cookie login first
            cookie_login = self.load_cookies()
            
            if cookie_login:
                self.driver.get(TF_LOGIN_URL)
                time.sleep(3)
                
                if "login" in self.driver.current_url.lower():
                    print("⚠️ Cookies expired, doing full login")
                    if not self.login():
                        return [], "error: login failed"
            else:
                if not self.login():
                    return [], "error: login failed"
            
            # Close any warning popups
            self.close_warning()
            
            # Wait for map to initialize
            print("\n⏳ Waiting for map to load...")
            time.sleep(5)
            
            # Zoom to Australia
            self.zoom_to_australia()
            
            # Debug what's in the map sources
            self.debug_map_features()
            
            # Wait for trains to load (with triggering)
            self.wait_for_trains_simple(max_wait=60)
            
            # Debug again after waiting
            self.debug_map_features()
            
            # Try both extraction methods
            raw_trains = []
            
            # First try currentTrains
            trains_from_js = self.extract_trains_from_currentTrains()
            raw_trains.extend(trains_from_js)
            
            # Then try map features
            trains_from_map = self.extract_trains_from_map_features()
            raw_trains.extend(trains_from_map)
            
            # Filter to Australia with detailed logging
            australian_trains = self.filter_australian_trains(raw_trains)
            
            print(f"\n✅ Australian trains: {len(australian_trains)}")
            
            # Return results
            note = f"ok - {len(australian_trains)} trains"
            return australian_trains, note
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return [], f"error: {type(e).__name__}"
        
        finally:
            if self.driver:
                self.driver.quit()
                print("👋 Browser closed")

def write_output(trains, note=""):
    """Write trains to JSON file"""
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains or []
    }
    
    # Create backup if file exists
    if os.path.exists(OUT_FILE):
        backup_name = f"trains_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(OUT_FILE, 'r') as src:
                with open(backup_name, 'w') as dst:
                    dst.write(src.read())
            print(f"💾 Backup created: {backup_name}")
        except:
            pass
    
    # Write new data
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    
    print(f"📝 Output: {len(trains or [])} trains, status: {note}")
    
    # Clean up old backups (keep last 5)
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
    
    # Exit with appropriate code
    if "error" in note:
        exit(1)
    else:
        exit(0)

if __name__ == "__main__":
    main()
