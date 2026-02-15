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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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
    
    def wait_for_trains(self, max_wait=30):
        """Wait for trains to appear in currentTrains variable"""
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains to load...")
        
        script = """
        function checkTrains() {
            if (window.currentTrains && Array.isArray(window.currentTrains) && window.currentTrains.length > 0) {
                return {
                    'loaded': true,
                    'count': window.currentTrains.length,
                    'sample': window.currentTrains.slice(0, 2)
                };
            }
            
            // Check alternative variables
            var altVars = ['trains', 'trainData', 'trainList', 'locomotives', 'trainPositions'];
            for (var i = 0; i < altVars.length; i++) {
                var name = altVars[i];
                if (window[name] && Array.isArray(window[name]) && window[name].length > 0) {
                    return {
                        'loaded': true,
                        'count': window[name].length,
                        'using': name,
                        'sample': window[name].slice(0, 2)
                    };
                }
            }
            
            return {'loaded': false, 'count': 0};
        }
        return checkTrains();
        """
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            result = self.driver.execute_script(script)
            if result.get('loaded'):
                using = result.get('using', 'currentTrains')
                print(f"✅ Trains loaded! Found {result['count']} trains in {using}")
                if result.get('sample'):
                    print(f"📊 Sample train structure: {json.dumps(result['sample'], indent=2)}")
                return True
            
            # Also check map features as backup
            feature_count = self.check_map_features_count()
            if feature_count > 0:
                print(f"✅ Map has {feature_count} features loaded")
                return True
            
            time.sleep(2)
            print(".", end="", flush=True)
        
        print("\n⚠️ Timeout waiting for trains")
        return False
    
    def check_map_features_count(self):
        """Check how many features are in map sources"""
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
        try:
            return self.driver.execute_script(script)
        except:
            return 0
    
    def inspect_currentTrains_structure(self):
        """Inspect the structure of currentTrains to understand its format"""
        print("\n🔍 Inspecting currentTrains structure...")
        
        script = """
        var info = {
            'exists': false,
            'type': null,
            'length': 0,
            'keys': [],
            'sample': null,
            'first_item_keys': []
        };
        
        if (window.currentTrains !== undefined) {
            info.exists = true;
            info.type = typeof window.currentTrains;
            
            if (Array.isArray(window.currentTrains)) {
                info.length = window.currentTrains.length;
                if (info.length > 0) {
                    info.sample = window.currentTrains[0];
                    info.first_item_keys = Object.keys(window.currentTrains[0]);
                }
            } else if (typeof window.currentTrains === 'object') {
                info.keys = Object.keys(window.currentTrains);
                if (info.keys.length > 0) {
                    info.sample = window.currentTrains[info.keys[0]];
                }
            }
        }
        
        // Also check other possible variables
        var otherVars = {};
        var altNames = ['trains', 'trainData', 'trainList', 'locomotives', 'trainPositions'];
        altNames.forEach(function(name) {
            if (window[name] !== undefined) {
                otherVars[name] = {
                    'type': typeof window[name],
                    'length': Array.isArray(window[name]) ? window[name].length : 'n/a'
                };
            }
        });
        
        return {
            'currentTrains': info,
            'otherVars': otherVars
        };
        """
        
        try:
            result = self.driver.execute_script(script)
            print(f"   currentTrains exists: {result['currentTrains']['exists']}")
            if result['currentTrains']['exists']:
                print(f"   Type: {result['currentTrains']['type']}")
                print(f"   Length: {result['currentTrains']['length']}")
                if result['currentTrains']['first_item_keys']:
                    print(f"   First item keys: {result['currentTrains']['first_item_keys']}")
                if result['currentTrains']['sample']:
                    print(f"   Sample: {json.dumps(result['currentTrains']['sample'], indent=2)}")
            
            if result['otherVars']:
                print(f"\n   Other train variables found:")
                for name, info in result['otherVars'].items():
                    print(f"      {name}: {info}")
            
            return result
        except Exception as e:
            print(f"❌ Error inspecting structure: {e}")
            return None
    
    def extract_trains_from_currentTrains(self):
        """Extract train data from the currentTrains global variable"""
        print("\n🔍 Extracting trains from currentTrains variable...")
        
        script = """
        function extractFromArray(arr, sourceName) {
            var trains = [];
            arr.forEach(function(item, index) {
                try {
                    // Handle different possible structures
                    var lat = null;
                    var lon = null;
                    
                    // Check various possible coordinate locations
                    if (item.lat !== undefined && item.lon !== undefined) {
                        lat = item.lat;
                        lon = item.lon;
                    } else if (item.latitude !== undefined && item.longitude !== undefined) {
                        lat = item.latitude;
                        lon = item.longitude;
                    } else if (item.coords && Array.isArray(item.coords) && item.coords.length >= 2) {
                        lon = item.coords[0];
                        lat = item.coords[1];
                    } else if (item.geometry && item.geometry.coordinates) {
                        lon = item.geometry.coordinates[0];
                        lat = item.geometry.coordinates[1];
                    } else if (item.position && item.position.lat !== undefined) {
                        lat = item.position.lat;
                        lon = item.position.lon;
                    }
                    
                    if (lat !== null && lon !== null) {
                        // Extract ID
                        var id = item.id || item.ID || item.trainId || item.unit || 
                                item.loco || item.train_id || sourceName + '_' + index;
                        
                        // Extract train number
                        var trainNumber = item.service || item.trainNumber || item.name || 
                                         item.number || item.train_number || item.displayName || '';
                        
                        // Extract heading
                        var heading = item.heading || item.direction || item.bearing || 0;
                        
                        // Extract speed
                        var speed = item.speed || item.velocity || 0;
                        
                        trains.push({
                            'id': String(id).trim(),
                            'train_number': String(trainNumber).trim() || String(id).trim(),
                            'x': parseFloat(lon),
                            'y': parseFloat(lat),
                            'heading': parseFloat(heading),
                            'speed': parseFloat(speed)
                        });
                    }
                } catch(e) {
                    console.log('Error processing train item:', e);
                }
            });
            return trains;
        }
        
        var allTrains = [];
        
        // Try currentTrains first
        if (window.currentTrains) {
            if (Array.isArray(window.currentTrains)) {
                allTrains = extractFromArray(window.currentTrains, 'currentTrains');
            } else if (typeof window.currentTrains === 'object') {
                // Might be an object with train IDs as keys
                var trainsArray = [];
                for (var key in window.currentTrains) {
                    if (window.currentTrains.hasOwnProperty(key)) {
                        var item = window.currentTrains[key];
                        if (item && typeof item === 'object') {
                            trainsArray.push(item);
                        }
                    }
                }
                allTrains = extractFromArray(trainsArray, 'currentTrains_obj');
            }
        }
        
        // If still no trains, try other variables
        if (allTrains.length === 0) {
            var altNames = ['trains', 'trainData', 'trainList', 'locomotives', 'trainPositions'];
            altNames.forEach(function(name) {
                if (window[name] && Array.isArray(window[name]) && window[name].length > 0) {
                    var extracted = extractFromArray(window[name], name);
                    allTrains = allTrains.concat(extracted);
                }
            });
        }
        
        return allTrains;
        """
        
        try:
            trains = self.driver.execute_script(script)
            print(f"✅ Found {len(trains)} trains in JavaScript variables")
            return trains
        except Exception as e:
            print(f"❌ Error extracting from currentTrains: {e}")
            return []
    
    def extract_trains_from_map_features(self):
        """Extract from OpenLayers sources"""
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
                    } catch(e) {}
                });
            } catch(e) {}
            return trains;
        }
        
        var sourceNames = ['regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource'];
        sourceNames.forEach(function(name) {
            if (window[name]) {
                var trains = extractFromSource(window[name], name);
                allTrains = allTrains.concat(trains);
            }
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
        
        for t in raw_trains:
            x = t.get('x')
            y = t.get('y')
            
            if x is None or y is None:
                continue
            
            # Check if coordinates are likely Web Mercator (large numbers)
            if abs(x) > 180 or abs(y) > 90:
                lat, lon = self.webmercator_to_latlon(x, y)
            else:
                # Already in lat/lon
                lat, lon = float(y), float(x)
            
            if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
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
            
            # Inspect the structure of currentTrains
            self.inspect_currentTrains_structure()
            
            # Wait for trains to load with timeout
            trains_loaded = self.wait_for_trains(max_wait=30)
            
            if not trains_loaded:
                print("⚠️ Trains didn't load, but will try extraction anyway")
            
            # Try primary method - extract from currentTrains
            raw_trains = self.extract_trains_from_currentTrains()
            
            # If no trains found, try map features as fallback
            if len(raw_trains) == 0:
                print("⚠️ No trains in currentTrains, trying map features...")
                raw_trains = self.extract_trains_from_map_features()
            
            # Filter to Australia
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
