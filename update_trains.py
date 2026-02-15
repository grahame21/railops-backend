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
        """Configure Chrome driver with anti-detection measures"""
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        
        # Random user agent to avoid detection
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        ]
        chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Speed optimizations
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--disable-extensions')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Hide webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def save_cookies(self):
        """Save session cookies for next run"""
        with open(COOKIE_FILE, "wb") as f:
            pickle.dump(self.driver.get_cookies(), f)
        print("✅ Cookies saved for next run")
    
    def load_cookies(self):
        """Load saved cookies to skip login"""
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
                print("✅ Loaded saved session")
                return True
            except:
                pass
        return False
    
    def random_delay(self, min_sec=0.5, max_sec=2):
        """Add random delays to simulate human behavior"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def check_session_valid(self):
        """Verify we're still logged in"""
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
        """Perform a completely fresh login"""
        print("\n🔐 Performing fresh login...")
        
        # Remove old cookie file
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            print("🗑️ Removed old cookies")
        
        # Clear browser cookies
        self.driver.delete_all_cookies()
        
        # Go to login page
        self.driver.get(TF_LOGIN_URL)
        self.random_delay(2, 4)
        
        try:
            # Find username field and type like a human
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            username.clear()
            for char in TF_USERNAME:
                username.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            print("✅ Username entered")
            
            self.random_delay(0.5, 1.5)
            
            # Find password field and type like a human
            password = self.driver.find_element(By.ID, "pasS_word")
            password.clear()
            for char in TF_PASSWORD:
                password.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            print("✅ Password entered")
            
            self.random_delay(1, 2)
            
            # Click login button
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
            
            # Close warning popup
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
            
            # Save cookies for next run
            self.save_cookies()
            return True
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def login(self):
        """Main login method with session checking"""
        # Try with saved cookies first
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
        """Zoom map to show all Australian trains"""
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
    
    def extract_trains(self):
        """Extract ALL train data from OpenLayers sources with detailed properties"""
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        // Only look at real train sources, IGNORE arrowMarkersSource
        var sources = ['regTrainsSource', 'unregTrainsSource'];
        
        sources.forEach(function(sourceName) {
            var source = window[sourceName];
            if (!source || !source.getFeatures) return;
            
            try {
                var features = source.getFeatures();
                
                features.forEach(function(feature, index) {
                    try {
                        var props = feature.getProperties();
                        var geom = feature.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            // Collect ALL available properties from the feature
                            var trainData = {
                                // Basic identifiers
                                'id': props.id || '',
                                'loco': props.loco || props.Loco || '',
                                'unit': props.unit || props.Unit || '',
                                'train_number': props.train_number || props.trainNumber || props.service || props.Service || '',
                                'name': props.name || props.NAME || '',
                                
                                // Operations data
                                'operator': props.operator || props.Operator || '',
                                'origin': props.origin || props.Origin || props.from || props.From || '',
                                'destination': props.destination || props.Destination || props.to || props.To || '',
                                
                                // Movement data
                                'speed': props.speed || props.Speed || 0,
                                'heading': props.heading || props.Heading || props.direction || props.Direction || 0,
                                
                                // Timing data
                                'eta': props.eta || props.ETA || '',
                                'departure': props.departure || props.Departure || '',
                                'arrival': props.arrival || props.Arrival || '',
                                
                                // Train composition
                                'service': props.service_code || props.serviceNumber || props.trainNumber || '',
                                'consist': props.consist || props.Consist || '',
                                'length': props.length || props.Length || '',
                                'weight': props.weight || props.Weight || '',
                                'cars': props.cars || props.Cars || '',
                                
                                // Additional metadata
                                'type': props.type || props.Type || props.train_type || props.TrainType || '',
                                'status': props.status || props.Status || '',
                                'line': props.line || props.Line || props.route || props.Route || '',
                                
                                // Source and coordinates
                                'source': sourceName,
                                'x': coords[0],
                                'y': coords[1]
                            };
                            
                            // Clean up empty values
                            for (var key in trainData) {
                                if (trainData[key] === undefined || trainData[key] === null) {
                                    trainData[key] = '';
                                }
                            }
                            
                            // Create a unique ID from available data (prioritize real identifiers)
                            var uniqueId = trainData.loco || trainData.unit || trainData.train_number || trainData.id;
                            
                            // If still no ID, use source + index but mark as generic
                            var isGeneric = false;
                            if (!uniqueId) {
                                uniqueId = sourceName + '_' + index;
                                isGeneric = true;
                            }
                            
                            // Skip arrow markers and generic sources if they don't have real data
                            if (uniqueId.toString().toLowerCase().includes('arrow')) {
                                return;
                            }
                            
                            if (!seenIds.has(uniqueId)) {
                                seenIds.add(uniqueId);
                                trainData.display_id = uniqueId;
                                trainData.is_generic = isGeneric;
                                allTrains.push(trainData);
                            }
                        }
                    } catch(e) {
                        console.log('Error processing feature:', e);
                    }
                });
            } catch(e) {}
        });
        
        return allTrains;
        """
        
        return self.driver.execute_script(script)
    
    def webmercator_to_latlon(self, x, y):
        """Convert Web Mercator coordinates to latitude/longitude"""
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
        """Filter trains to Australia only and convert coordinates"""
        australian_trains = []
        seen_ids = set()
        
        generic_count = 0
        real_count = 0
        
        for t in raw_trains:
            # Skip if this is clearly an arrow marker or generic source
            train_id = t.get('display_id', '').lower()
            if 'arrow' in train_id or 'marker' in train_id:
                continue
            
            # Convert coordinates
            lat, lon = self.webmercator_to_latlon(t['x'], t['y'])
            
            # Check if in Australia
            if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
                # Create a clean ID - prefer real identifiers
                clean_id = t.get('loco') or t.get('unit') or t.get('train_number') or t.get('display_id')
                
                # Skip if it's still generic
                if clean_id and ('source' in clean_id.lower() or 'arrow' in clean_id.lower()):
                    continue
                
                if clean_id not in seen_ids:
                    seen_ids.add(clean_id)
                    
                    # Count real vs generic
                    if t.get('is_generic'):
                        generic_count += 1
                    else:
                        real_count += 1
                    
                    # Build comprehensive train object
                    train = {
                        'id': clean_id,
                        'loco': t.get('loco', ''),
                        'unit': t.get('unit', ''),
                        'train_number': t.get('train_number', ''),
                        'name': t.get('name', ''),
                        'operator': t.get('operator', ''),
                        'origin': t.get('origin', ''),
                        'destination': t.get('destination', ''),
                        'speed': round(float(t.get('speed', 0)), 1),
                        'heading': round(float(t.get('heading', 0)), 1),
                        'eta': t.get('eta', ''),
                        'departure': t.get('departure', ''),
                        'arrival': t.get('arrival', ''),
                        'service': t.get('service', ''),
                        'consist': t.get('consist', ''),
                        'length': t.get('length', ''),
                        'weight': t.get('weight', ''),
                        'cars': t.get('cars', ''),
                        'type': t.get('type', ''),
                        'status': t.get('status', ''),
                        'line': t.get('line', ''),
                        'lat': lat,
                        'lon': lon,
                        'is_generic': t.get('is_generic', False)
                    }
                    australian_trains.append(train)
        
        print(f"\n📊 Train Statistics:")
        print(f"   Real train IDs: {real_count}")
        print(f"   Generic IDs (filtered out): {generic_count}")
        
        return australian_trains
    
    def run(self):
        """Main execution method"""
        print("=" * 60)
        print("🚂 RAILOPS - TRAIN SCRAPER")
        print(f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        if not TF_USERNAME or not TF_PASSWORD:
            print("❌ Missing credentials")
            return [], "Missing credentials"
        
        try:
            # Setup browser
            self.setup_driver()
            
            # Login with session checking
            if not self.login():
                return [], "Login failed"
            
            # Wait for map to stabilize
            print("\n⏳ Waiting 30 seconds for map to stabilize...")
            time.sleep(30)
            
            # Zoom to Australia
            self.zoom_to_australia()
            
            # Wait for trains to load
            print("⏳ Waiting 60 seconds for trains to load...")
            time.sleep(60)
            
            # Extract all train data
            print("\n🔍 Extracting trains...")
            raw_trains = self.extract_trains()
            print(f"✅ Extracted {len(raw_trains)} raw positions")
            
            # Filter to Australian trains only
            australian_trains = self.filter_australian_trains(raw_trains)
            
            print(f"\n✅ Australian trains: {len(australian_trains)}")
            
            # Show sample of real trains
            real_trains = [t for t in australian_trains if not t.get('is_generic')]
            if real_trains:
                print(f"\n📋 Sample real train:")
                sample = real_trains[0]
                print(f"   ID: {sample['id']}")
                print(f"   Operator: {sample['operator']}")
                print(f"   Origin: {sample['origin']}")
                print(f"   Destination: {sample['destination']}")
                print(f"   Speed: {sample['speed']} km/h")
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
    
    if "error" in note:
        exit(1)
    else:
        exit(0)

if __name__ == "__main__":
    main()
