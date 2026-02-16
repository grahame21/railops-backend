import os
import sys
import json
import datetime
import time
import math
import pickle
import random
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

print("=" * 60)
print("🚂 RAILOPS - TRAIN SCRAPER")
print("=" * 60)
print(f"Python version: {sys.version}")
print(f"Current time: {datetime.datetime.now()}")
print("=" * 60)

OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

print(f"\n🔑 Credentials:")
print(f"   Username set: {'Yes' if TF_USERNAME else 'No'}")
print(f"   Password set: {'Yes' if TF_PASSWORD else 'No'}")

class TrainScraper:
    def __init__(self):
        self.driver = None
        print("✅ TrainScraper initialized")
        
    def setup_driver(self):
        print("\n🔧 Setting up Chrome driver...")
        try:
            chrome_options = Options()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--headless=new')
            
            # Rotate user agents
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
        """Quick check if we're logged in"""
        try:
            current_url = self.driver.current_url.lower()
            page_source = self.driver.page_source.lower()
            
            if "login" in current_url or ("username" in page_source and "password" in page_source):
                return False
            
            # Check if map exists
            map_exists = self.driver.execute_script("return typeof window.map !== 'undefined'")
            return map_exists
        except:
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
                print("❌ Login verification failed")
                return False
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def login(self):
        if self.load_cookies():
            self.driver.get(TF_LOGIN_URL)
            self.random_delay(3, 5)
            if self.check_login_success():
                print("✅ Using saved session")
                return True
        return self.force_fresh_login()
    
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
        """Quick check for trains"""
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
        """Wait up to 60 seconds for trains"""
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
        """Extract trains - simplified version"""
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
        
        if not self.setup_driver():
            return [], "Driver setup failed"
        
        try:
            if not self.login():
                return [], "Login failed"
            
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
        print("⚠️ No trains to write")

def main():
    scraper = TrainScraper()
    trains, note = scraper.run()
    write_output(trains, note)

if __name__ == "__main__":
    main()
