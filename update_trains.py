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
                print("✅ Loaded saved cookies")
                return True
            except:
                pass
        return False
    
    def random_delay(self, min_sec=0.5, max_sec=2):
        time.sleep(random.uniform(min_sec, max_sec))
    
    def verify_logged_in(self):
        """Verify we're actually logged in and seeing the map with trains"""
        print("\n🔍 Verifying login status...")
        
        # Check if we're on the login page
        current_url = self.driver.current_url
        page_source = self.driver.page_source.lower()
        
        if "login" in current_url.lower() or "login" in page_source and "password" in page_source:
            print("❌ On login page - not logged in")
            return False
        
        # Check if map exists
        map_exists = self.driver.execute_script("return typeof window.map !== 'undefined'")
        if not map_exists:
            print("❌ Map not found - not fully loaded")
            return False
        
        # Check if train sources exist and have data
        script = """
        var hasTrains = false;
        var sources = ['regTrainsSource', 'unregTrainsSource'];
        var counts = {};
        
        sources.forEach(function(name) {
            if (window[name] && window[name].getFeatures) {
                counts[name] = window[name].getFeatures().length;
                if (counts[name] > 0) hasTrains = true;
            } else {
                counts[name] = 'not found';
            }
        });
        
        return {
            hasTrains: hasTrains,
            counts: counts,
            mapExists: typeof window.map !== 'undefined'
        };
        """
        
        try:
            result = self.driver.execute_script(script)
            print(f"   Map exists: {result['mapExists']}")
            print(f"   Train sources: {result['counts']}")
            
            if result['hasTrains']:
                print("✅ Verified: trains are loading!")
                return True
            else:
                print("⚠️ Logged in but no trains yet - might need more time")
                return True  # Still logged in, just waiting for trains
        except:
            pass
        
        return True  # Assume logged in if we passed previous checks
    
    def force_fresh_login(self):
        """Delete old cookies and do a completely fresh login"""
        print("\n🔐 Performing fresh login...")
        
        # Delete old cookie file if it exists
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            print("🗑️ Removed old cookies")
        
        # Clear browser cookies
        self.driver.delete_all_cookies()
        
        # Go to login page
        self.driver.get(TF_LOGIN_URL)
        self.random_delay(2, 4)
        
        try:
            # Wait for login form
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            username.clear()
            username.send_keys(TF_USERNAME)
            print("✅ Username entered")
            
            self.random_delay(0.5, 1.5)
            
            password = self.driver.find_element(By.ID, "pasS_word")
            password.clear()
            password.send_keys(TF_PASSWORD)
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
            
            # Wait for login to process
            time.sleep(5)
            
            # Close warning if it appears
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
            
            # Wait for map to load
            time.sleep(5)
            
            # Verify login worked
            if self.verify_logged_in():
                print("✅ Fresh login successful!")
                self.save_cookies()
                return True
            else:
                print("❌ Fresh login failed")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def login(self):
        """Main login method with verification"""
        # First try with existing cookies
        if self.load_cookies():
            self.driver.get(TF_LOGIN_URL)
            self.random_delay(3, 5)
            
            if self.verify_logged_in():
                print("✅ Session valid")
                return True
            else:
                print("⚠️ Saved session invalid, doing fresh login")
                return self.force_fresh_login()
        else:
            # No saved cookies, do fresh login
            return self.force_fresh_login()
    
    def zoom_to_australia(self):
        self.random_delay(2, 4)
        
        self.driver.execute_script("""
            if (window.map) {
                try {
                    var australia = [112, -44, 154, -10];
                    var proj = window.map.getView().getProjection();
                    var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                    window.map.getView().fit(extent, { duration: 3000, maxZoom: 8 });
                    return true;
                } catch(e) {}
            }
            return false;
        """)
        print("🌏 Zoomed to Australia")
    
    def extract_trains(self):
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        var sources = ['regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource'];
        
        sources.forEach(function(sourceName) {
            var source = window[sourceName];
            if (!source || typeof source.getFeatures !== 'function') return;
            
            try {
                var features = source.getFeatures();
                
                features.forEach(function(feature, index) {
                    try {
                        var props = feature.getProperties();
                        var geom = feature.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            var id = props.id || props.ID || props.loco || props.Loco || 
                                    props.unit || props.Unit || sourceName + '_' + index;
                            
                            var trainNumber = props.service || props.Service || 
                                             props.trainNumber || props.train_number || id;
                            
                            if (!seenIds.has(id)) {
                                seenIds.add(id);
                                allTrains.push({
                                    'id': String(id).trim(),
                                    'train_number': String(trainNumber).trim(),
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
        });
        
        return allTrains;
        """
        
        return self.driver.execute_script(script)
    
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
            lat, lon = self.webmercator_to_latlon(t['x'], t['y'])
            if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
                train_id = t['id']
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
        print("=" * 60)
        print("🚂 RAILOPS - TRAIN SCRAPER")
        print(f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        if not TF_USERNAME or not TF_PASSWORD:
            print("❌ Missing credentials")
            return [], "Missing credentials"
        
        try:
            self.setup_driver()
            
            # Login with verification
            if not self.login():
                return [], "Login failed"
            
            # Verify we're actually logged in and seeing the map
            if not self.verify_logged_in():
                print("⚠️ Login verification failed, retrying...")
                if not self.force_fresh_login():
                    return [], "Login failed"
            
            print("\n⏳ Waiting 30 seconds for map to stabilize...")
            time.sleep(30)
            
            self.zoom_to_australia()
            
            print("⏳ Waiting 60 seconds for trains to load...")
            time.sleep(60)
            
            print("\n🔍 Extracting trains...")
            raw_trains = self.extract_trains()
            print(f"✅ Extracted {len(raw_trains)} raw positions")
            
            australian_trains = self.filter_australian_trains(raw_trains)
            
            print(f"\n✅ Australian trains: {len(australian_trains)}")
            
            if australian_trains:
                print(f"\n📋 Sample train:")
                print(f"   ID: {australian_trains[0]['id']}")
                print(f"   Location: {australian_trains[0]['lat']:.4f}, {australian_trains[0]['lon']:.4f}")
            
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
