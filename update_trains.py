import os
import sys
import json
import datetime
import time
import math
import pickle
import random
import traceback
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

print("=" * 60)
print("🚂 RAILOPS - TRAIN SCRAPER WITH PROXY")
print("=" * 60)
print(f"Python version: {sys.version}")
print(f"Current time: {datetime.datetime.now()}")
print("=" * 60)

OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

# Free proxy list - these are examples, you'll need fresh ones
# Get fresh proxies from: https://free-proxy-list.net/
PROXIES = [
    # Format: "ip:port"
    # You MUST replace these with working proxies
    # Example: "123.45.67.89:8080"
]

print(f"\n🔑 Credentials:")
print(f"   Username set: {'Yes' if TF_USERNAME else 'No'}")
print(f"   Password set: {'Yes' if TF_PASSWORD else 'No'}")
print(f"   Proxies configured: {len(PROXIES)}")

def test_proxy(proxy):
    """Test if a proxy is working"""
    try:
        test_url = "http://httpbin.org/ip"
        proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
        response = requests.get(test_url, proxies=proxies, timeout=10)
        if response.status_code == 200:
            print(f"   ✅ Proxy {proxy} is working")
            return True
    except:
        pass
    return False

class TrainScraper:
    def __init__(self):
        self.driver = None
        print("✅ TrainScraper initialized")
        
    def setup_driver_with_proxy(self, proxy=None):
        print("\n🔧 Setting up Chrome driver...")
        try:
            chrome_options = Options()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--headless=new')
            
            # Add proxy if provided
            if proxy:
                chrome_options.add_argument(f'--proxy-server=http://{proxy}')
                print(f"   Using proxy: {proxy}")
            
            # Rotate user agents
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]
            chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')
            
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            print("✅ Chrome driver setup successful")
            return True
        except Exception as e:
            print(f"❌ Failed to setup Chrome driver: {e}")
            return False
    
    def save_cookies(self):
        try:
            with open(COOKIE_FILE, "wb") as f:
                pickle.dump(self.driver.get_cookies(), f)
            print("✅ Cookies saved")
        except Exception as e:
            print(f"❌ Failed to save cookies: {e}")
    
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
            except Exception as e:
                print(f"⚠️ Could not load cookies: {e}")
        return False
    
    def random_delay(self, min_sec=1, max_sec=3):
        time.sleep(random.uniform(min_sec, max_sec))
    
    def check_login_success(self):
        """Check if we're logged in and seeing trains"""
        try:
            current_url = self.driver.current_url.lower()
            
            if "login" in current_url:
                return False
            
            # Check if map exists and has train sources
            script = """
            var result = {
                'map_exists': typeof window.map !== 'undefined',
                'train_sources': {}
            };
            var sources = ['regTrainsSource', 'unregTrainsSource'];
            sources.forEach(function(name) {
                if (window[name] && window[name].getFeatures) {
                    result.train_sources[name] = window[name].getFeatures().length;
                } else {
                    result.train_sources[name] = 0;
                }
            });
            return result;
            """
            
            result = self.driver.execute_script(script)
            total_trains = sum(result['train_sources'].values())
            
            print(f"   Map exists: {result['map_exists']}")
            print(f"   Train sources: {result['train_sources']}")
            
            return total_trains > 5
        except Exception as e:
            print(f"   Login check error: {e}")
            return False
    
    def force_fresh_login(self):
        print("\n🔐 Performing fresh login...")
        
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
        
        self.driver.delete_all_cookies()
        self.driver.get(TF_LOGIN_URL)
        self.random_delay(2, 4)
        
        try:
            # Find and fill username
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            username.clear()
            username.send_keys(TF_USERNAME)
            print("✅ Username entered")
            
            self.random_delay(1, 2)
            
            # Find and fill password
            password = self.driver.find_element(By.ID, "pasS_word")
            password.clear()
            password.send_keys(TF_PASSWORD)
            print("✅ Password entered")
            
            self.random_delay(1, 2)
            
            # Click login
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
            print("✅ Login button clicked")
            
            time.sleep(5)
            
            # Close warning
            try:
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
            except:
                pass
            
            time.sleep(3)
            
            if self.check_login_success():
                self.save_cookies()
                return True
            else:
                print("❌ Login verification failed - no trains visible")
                return False
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def login_with_proxy_rotation(self):
        """Try multiple proxies until one works"""
        
        # First try without proxy (maybe it works)
        print("\n🔄 Attempt 1: Direct connection (no proxy)")
        if self.setup_driver_with_proxy(None):
            if self.load_cookies():
                self.driver.get(TF_LOGIN_URL)
                self.random_delay(3, 5)
                if self.check_login_success():
                    print("✅ Success with direct connection")
                    return True
            
            if self.force_fresh_login():
                return True
            self.driver.quit()
        
        # Try each proxy
        for i, proxy in enumerate(PROXIES):
            print(f"\n🔄 Attempt {i+2}: Testing proxy {proxy}")
            
            # Test proxy first
            if not test_proxy(proxy):
                print(f"   ⚠️ Proxy {proxy} failed test, skipping")
                continue
            
            if self.setup_driver_with_proxy(proxy):
                if self.load_cookies():
                    self.driver.get(TF_LOGIN_URL)
                    self.random_delay(3, 5)
                    if self.check_login_success():
                        print(f"✅ Success with proxy {proxy}")
                        return True
                
                if self.force_fresh_login():
                    print(f"✅ Success with proxy {proxy}")
                    return True
                
                self.driver.quit()
                time.sleep(5)
        
        print("❌ All proxy attempts failed")
        return False
    
    def zoom_to_australia(self):
        try:
            self.driver.execute_script("""
                if (window.map) {
                    var australia = [112, -44, 154, -10];
                    var proj = window.map.getView().getProjection();
                    var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                    window.map.getView().fit(extent, { duration: 2000, maxZoom: 8 });
                }
            """)
            print("🌏 Zoomed to Australia")
            time.sleep(3)
        except:
            print("⚠️ Could not zoom")
    
    def get_train_count(self):
        script = """
        var total = 0;
        var sources = ['regTrainsSource', 'unregTrainsSource'];
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
    
    def wait_for_trains(self, max_wait=60):
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains...")
        
        for i in range(max_wait // 5):
            count = self.get_train_count()
            if count > 5:
                print(f"   ✅ Found {count} trains after {i*5}s")
                return True
            print(f"   ... {count} trains so far")
            time.sleep(5)
        
        print(f"   ⚠️ Only found {self.get_train_count()} trains")
        return False
    
    def extract_trains(self):
        print("\n🔍 Extracting trains...")
        
        script = """
        var trains = [];
        var seenIds = new Set();
        
        var sources = ['regTrainsSource', 'unregTrainsSource'];
        
        sources.forEach(function(sourceName) {
            var source = window[sourceName];
            if (!source || !source.getFeatures) return;
            
            var features = source.getFeatures();
            
            features.forEach(function(feature) {
                try {
                    var props = feature.getProperties();
                    var geom = feature.getGeometry();
                    
                    if (!geom || geom.getType() !== 'Point') return;
                    
                    var coords = geom.getCoordinates();
                    
                    // Get train identifiers
                    var trainNumber = props.trainNumber || '';
                    var trainName = props.trainName || '';
                    var origin = props.serviceFrom || '';
                    var destination = props.serviceTo || '';
                    
                    // Skip if no data
                    if (!trainNumber && !trainName && !origin && !destination) return;
                    
                    // Get speed
                    var speed = 0;
                    if (props.trainSpeed) {
                        var match = String(props.trainSpeed).match(/(\\d+)/);
                        if (match) speed = parseInt(match[0]);
                    }
                    
                    var id = trainName || trainNumber || sourceName + '_' + features.indexOf(feature);
                    
                    if (!seenIds.has(id)) {
                        seenIds.add(id);
                        trains.push({
                            'id': id,
                            'train_number': trainNumber,
                            'train_name': trainName,
                            'speed': speed,
                            'origin': origin,
                            'destination': destination,
                            'description': props.serviceDesc || '',
                            'km': props.trainKM || '',
                            'time': props.trainTime || '',
                            'x': coords[0],
                            'y': coords[1]
                        });
                    }
                } catch(e) {}
            });
        });
        
        return trains;
        """
        
        try:
            trains = self.driver.execute_script(script)
            print(f"   ✅ Extracted {len(trains)} trains")
            return trains
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return []
    
    def webmercator_to_latlon(self, x, y):
        try:
            lon = (x / 20037508.34) * 180
            lat = (y / 20037508.34) * 180
            lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
            return round(lat, 6), round(lon, 6)
        except:
            return None, None
    
    def filter_australian(self, trains):
        result = []
        seen = set()
        
        for t in trains:
            x = t.get('x', 0)
            y = t.get('y', 0)
            
            if abs(x) > 180 or abs(y) > 90:
                lat, lon = self.webmercator_to_latlon(x, y)
            else:
                lat, lon = y, x
            
            if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
                if t['id'] not in seen:
                    seen.add(t['id'])
                    t['lat'] = lat
                    t['lon'] = lon
                    del t['x']
                    del t['y']
                    result.append(t)
        
        print(f"\n📊 Found {len(result)} Australian trains")
        return result
    
    def run(self):
        print("\n🚀 Starting scraper run...")
        
        if not TF_USERNAME or not TF_PASSWORD:
            return [], "Missing credentials"
        
        if not self.login_with_proxy_rotation():
            return [], "Login failed after proxy rotation"
        
        try:
            time.sleep(10)
            self.zoom_to_australia()
            self.wait_for_trains(max_wait=45)
            
            trains = self.extract_trains()
            australian = self.filter_australian(trains)
            
            return australian, f"ok - {len(australian)} trains"
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return [], f"error: {type(e).__name__}"
        finally:
            if self.driver:
                self.driver.quit()

def write_output(trains, note):
    if trains:
        payload = {
            "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
            "note": note,
            "trains": trains
        }
        with open(OUT_FILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"✅ Wrote {len(trains)} trains")
    else:
        print("⚠️ No trains to write - keeping existing data")

def main():
    scraper = TrainScraper()
    trains, note = scraper.run()
    write_output(trains, note)

if __name__ == "__main__":
    main()
