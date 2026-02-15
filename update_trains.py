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
    
    def find_all_train_variables(self):
        """Search through all global variables to find train data"""
        print("\n🔍 Searching all global variables for train data...")
        
        script = """
        var results = {
            'variables_with_train_data': [],
            'train_arrays': [],
            'train_objects': {},
            'sample_data': {}
        };
        
        // Function to check if an object looks like train data
        function looksLikeTrainData(obj) {
            if (!obj || typeof obj !== 'object') return false;
            
            // Check for common train property patterns
            var hasLocation = (obj.lat !== undefined || obj.latitude !== undefined || 
                              (obj.coords && Array.isArray(obj.coords)) ||
                              (obj.geometry && obj.geometry.coordinates));
            
            var hasId = (obj.id !== undefined || obj.ID !== undefined || 
                        obj.trainId !== undefined || obj.unit !== undefined);
            
            return hasLocation || hasId;
        }
        
        // Check all global variables
        for (var key in window) {
            try {
                var value = window[key];
                
                // Skip null, undefined, and built-in objects
                if (!value || typeof value !== 'object' || key.startsWith('_')) continue;
                
                // Check if it's an array
                if (Array.isArray(value) && value.length > 0) {
                    // Check first few items
                    var trainCount = 0;
                    var sampleItem = null;
                    
                    for (var i = 0; i < Math.min(value.length, 5); i++) {
                        if (value[i] && looksLikeTrainData(value[i])) {
                            trainCount++;
                            if (!sampleItem) sampleItem = value[i];
                        }
                    }
                    
                    if (trainCount > 0) {
                        results.train_arrays.push({
                            'name': key,
                            'length': value.length,
                            'train_like_items': trainCount,
                            'sample': sampleItem
                        });
                    }
                }
                // Check if it's an object with train-like properties
                else if (looksLikeTrainData(value)) {
                    results.variables_with_train_data.push(key);
                    results.sample_data[key] = value;
                }
                // Check if it's an object containing train arrays
                else {
                    for (var subkey in value) {
                        if (Array.isArray(value[subkey]) && value[subkey].length > 0) {
                            for (var i = 0; i < Math.min(value[subkey].length, 3); i++) {
                                if (value[subkey][i] && looksLikeTrainData(value[subkey][i])) {
                                    results.train_objects[key + '.' + subkey] = {
                                        'length': value[subkey].length,
                                        'sample': value[subkey][i]
                                    };
                                    break;
                                }
                            }
                        }
                    }
                }
            } catch(e) {
                // Skip variables that cause errors when accessed
            }
        }
        
        return results;
        """
        
        try:
            results = self.driver.execute_script(script)
            
            print(f"\n📊 Found {len(results['train_arrays'])} arrays with train-like data:")
            for arr in results['train_arrays']:
                print(f"   - {arr['name']}: {arr['length']} items ({arr['train_like_items']} train-like)")
                if arr.get('sample'):
                    print(f"     Sample: {json.dumps(arr['sample'], indent=2)[:200]}...")
            
            if results['variables_with_train_data']:
                print(f"\n📊 Found {len(results['variables_with_train_data'])} variables with train data:")
                for var in results['variables_with_train_data']:
                    print(f"   - {var}")
            
            if results['train_objects']:
                print(f"\n📊 Found train data in nested objects:")
                for path, info in results['train_objects'].items():
                    print(f"   - {path}: {info['length']} items")
            
            return results
        except Exception as e:
            print(f"❌ Error searching for train variables: {e}")
            return None
    
    def extract_trains_from_variable(self, var_name, var_path=None):
        """Extract trains from a specific variable"""
        script = f"""
        function extractFromData(data) {{
            var trains = [];
            
            if (Array.isArray(data)) {{
                data.forEach(function(item, index) {{
                    try {{
                        var lat = null, lon = null;
                        
                        // Try different coordinate formats
                        if (item.lat !== undefined && item.lon !== undefined) {{
                            lat = item.lat;
                            lon = item.lon;
                        }} else if (item.latitude !== undefined && item.longitude !== undefined) {{
                            lat = item.latitude;
                            lon = item.longitude;
                        }} else if (item.coords && Array.isArray(item.coords)) {{
                            lon = item.coords[0];
                            lat = item.coords[1];
                        }} else if (item.geometry && item.geometry.coordinates) {{
                            lon = item.geometry.coordinates[0];
                            lat = item.geometry.coordinates[1];
                        }}
                        
                        if (lat !== null && lon !== null) {{
                            var id = item.id || item.ID || item.trainId || item.unit || 
                                    item.loco || 'train_' + index;
                            var trainNumber = item.service || item.trainNumber || item.name || 
                                             item.number || item.train_number || '';
                            
                            trains.push({{
                                'id': String(id).trim(),
                                'train_number': String(trainNumber).trim() || String(id).trim(),
                                'x': parseFloat(lon),
                                'y': parseFloat(lat),
                                'heading': parseFloat(item.heading || item.direction || 0),
                                'speed': parseFloat(item.speed || item.velocity || 0)
                            }});
                        }}
                    }} catch(e) {{}}
                }});
            }}
            
            return trains;
        }}
        
        var data = window.{var_name};
        return extractFromData(data);
        """
        
        try:
            trains = self.driver.execute_script(script)
            print(f"   Extracted {len(trains)} trains from {var_name}")
            return trains
        except Exception as e:
            print(f"   Error extracting from {var_name}: {e}")
            return []
    
    def wait_for_trains(self, max_wait=30):
        """Wait for trains to appear in any variable"""
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains to load...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            # Check if any trains have appeared
            results = self.find_all_train_variables()
            
            total_trains = 0
            for arr in results.get('train_arrays', []):
                if arr.get('train_like_items', 0) > 0:
                    total_trains += arr['train_like_items']
            
            if total_trains > 0:
                print(f"\n✅ Found {total_trains} trains across {len(results['train_arrays'])} variables")
                return True
            
            time.sleep(2)
            print(".", end="", flush=True)
        
        print("\n⚠️ Timeout waiting for trains")
        return False
    
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
            
            # Wait for trains to load
            trains_loaded = self.wait_for_trains(max_wait=45)
            
            # Find all possible train variables
            train_vars = self.find_all_train_variables()
            
            # Extract from all found sources
            all_raw_trains = []
            
            # Extract from arrays
            for arr in train_vars.get('train_arrays', []):
                var_name = arr['name']
                trains = self.extract_trains_from_variable(var_name)
                all_raw_trains.extend(trains)
            
            # Filter to Australia
            australian_trains = self.filter_australian_trains(all_raw_trains)
            
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
