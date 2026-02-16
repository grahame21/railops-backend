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
            traceback.print_exc()
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
    
    def random_delay(self, min_sec=1, max_sec=4):
        time.sleep(random.uniform(min_sec, max_sec))
    
    def check_session_valid(self):
        try:
            self.driver.get(TF_LOGIN_URL)
            self.random_delay(2, 4)
            if "login" in self.driver.current_url.lower():
                print("⚠️ Session expired")
                return False
            print("✅ Session valid")
            return True
        except Exception as e:
            print(f"⚠️ Session check error: {e}")
            return False
    
    def force_fresh_login(self):
        print("\n🔐 Performing fresh login...")
        
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            print("🗑️ Removed old cookies")
        
        self.driver.delete_all_cookies()
        self.driver.get(TF_LOGIN_URL)
        self.random_delay(2, 5)
        
        try:
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            username.clear()
            for char in TF_USERNAME:
                username.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))
            print("✅ Username entered")
            
            self.random_delay(1, 3)
            
            password = self.driver.find_element(By.ID, "pasS_word")
            password.clear()
            for char in TF_PASSWORD:
                password.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))
            print("✅ Password entered")
            
            self.random_delay(1, 3)
            
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
            
            self.random_delay(4, 7)
            
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
            
            self.random_delay(3, 6)
            
            self.save_cookies()
            return True
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            traceback.print_exc()
            return False
    
    def login(self):
        if self.load_cookies():
            self.driver.get(TF_LOGIN_URL)
            self.random_delay(3, 6)
            if self.check_session_valid():
                print("✅ Using saved session")
                return True
            else:
                print("⚠️ Saved session invalid, doing fresh login")
                return self.force_fresh_login()
        else:
            return self.force_fresh_login()
    
    def zoom_to_australia(self):
        self.random_delay(2, 5)
        try:
            self.driver.execute_script("""
                if (window.map) {
                    var australia = [112, -44, 154, -10];
                    var proj = window.map.getView().getProjection();
                    var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                    window.map.getView().fit(extent, { duration: 3000, maxZoom: 8 });
                }
            """)
            print("🌏 Zoomed to Australia")
        except Exception as e:
            print(f"⚠️ Could not zoom: {e}")
    
    def get_all_feature_counts(self):
        script = """
        var result = {};
        var sources = ['regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource'];
        sources.forEach(function(name) {
            if (window[name] && window[name].getFeatures) {
                result[name] = window[name].getFeatures().length;
            } else {
                result[name] = 0;
            }
        });
        return result;
        """
        try:
            return self.driver.execute_script(script)
        except:
            return {}
    
    def wait_for_trains(self, max_wait=180):
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains to load...")
        
        start_time = time.time()
        best_count = 0
        
        while time.time() - start_time < max_wait:
            counts = self.get_all_feature_counts()
            total = sum(counts.values())
            
            if total > best_count:
                best_count = total
                print(f"   📈 Found {total} features")
            
            if total > 100:
                print(f"   ✅ Proceeding with {total} features")
                return True
            
            time.sleep(5)
        
        print(f"   ⏰ Timeout. Got {best_count} features")
        return best_count > 50
    
    def extract_all_trains(self):
        print("\n🔍 Extracting ALL trains...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        var sources = ['regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource'];
        
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
                            
                            // Parse speed
                            var speedValue = props.trainSpeed || props.speed || 0;
                            var speedNum = 0;
                            if (typeof speedValue === 'string') {
                                var match = speedValue.match(/(\\d+\\.?\\d*)/);
                                if (match) {
                                    speedNum = parseFloat(match[1]);
                                }
                            } else if (typeof speedValue === 'number') {
                                speedNum = speedValue;
                            }
                            
                            // Use train_name for display if available
                            var displayId = props.trainName || props.trainNumber || 
                                          props.serviceName || sourceName + '_' + index;
                            
                            var trainData = {
                                'id': sourceName + '_' + index,  // Keep original ID for reference
                                'display_id': String(displayId),
                                'train_number': props.trainNumber || '',
                                'train_name': props.trainName || '',
                                'service_name': props.serviceName || '',
                                'cId': props.cId || '',
                                'servId': props.servId || '',
                                'trKey': props.trKey || '',
                                'speed': speedNum,
                                'heading': props.heading || props.Heading || 0,
                                'km': props.trainKM || '',
                                'origin': props.serviceFrom || '',
                                'destination': props.serviceTo || '',
                                'description': props.serviceDesc || '',
                                'date': props.trainDate || '',
                                'time': props.trainTime || '',
                                'tooltip': props.tooltipHTML || '',
                                'source': sourceName,
                                'x': coords[0],
                                'y': coords[1]
                            };
                            
                            // Avoid duplicates by display_id
                            if (!seenIds.has(displayId)) {
                                seenIds.add(displayId);
                                allTrains.push(trainData);
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        });
        
        return allTrains;
        """
        
        try:
            trains = self.driver.execute_script(script)
            print(f"   ✅ Extracted {len(trains)} unique trains")
            return trains
        except Exception as e:
            print(f"   ❌ Error: {e}")
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
            x = t.get('x', 0)
            y = t.get('y', 0)
            
            if abs(x) > 180 or abs(y) > 90:
                lat, lon = self.webmercator_to_latlon(x, y)
            else:
                lat, lon = y, x
            
            if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
                # Use display_id for deduplication
                display_id = t.get('display_id', 'unknown')
                
                if display_id not in seen_ids:
                    seen_ids.add(display_id)
                    australian_trains.append({
                        'id': display_id,  # Use display_id as main ID
                        'train_number': t.get('train_number', ''),
                        'train_name': t.get('train_name', ''),
                        'service_name': t.get('service_name', ''),
                        'cId': t.get('cId', ''),
                        'servId': t.get('servId', ''),
                        'trKey': t.get('trKey', ''),
                        'speed': round(float(t.get('speed', 0)), 1),
                        'heading': round(float(t.get('heading', 0)), 1),
                        'km': t.get('km', ''),
                        'origin': t.get('origin', ''),
                        'destination': t.get('destination', ''),
                        'description': t.get('description', ''),
                        'date': t.get('date', ''),
                        'time': t.get('time', ''),
                        'tooltip': t.get('tooltip', ''),
                        'source': t.get('source', ''),
                        'lat': lat,
                        'lon': lon
                    })
        
        print(f"\n📊 Found {len(australian_trains)} Australian trains")
        return australian_trains
    
    def run(self):
        print("\n🚀 Starting scraper run...")
        
        if not TF_USERNAME or not TF_PASSWORD:
            print("❌ Missing credentials")
            return [], "Missing credentials"
        
        if not self.setup_driver():
            return [], "Failed to setup driver"
        
        try:
            if not self.login():
                return [], "Login failed"
            
            print("\n⏳ Waiting 30 seconds for map to stabilize...")
            time.sleep(30)
            
            self.zoom_to_australia()
            
            # Wait for trains
            self.wait_for_trains(max_wait=180)
            
            # Extract trains
            raw_trains = self.extract_all_trains()
            
            australian_trains = self.filter_australian_trains(raw_trains)
            
            return australian_trains, f"ok - {len(australian_trains)} trains"
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            traceback.print_exc()
            return [], f"error: {type(e).__name__}"
        finally:
            if self.driver:
                self.driver.quit()
                print("👋 Browser closed")

def write_output(trains, note=""):
    if len(trains) > 0:
        print(f"\n📝 Writing {len(trains)} trains")
        payload = {
            "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
            "note": note,
            "trains": trains
        }
        
        try:
            with open(OUT_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"✅ Output written")
        except Exception as e:
            print(f"❌ Failed to write: {e}")

def main():
    print("\n🏁 Starting...")
    scraper = TrainScraper()
    trains, note = scraper.run()
    write_output(trains, note)
    print("\n✅ Done")

if __name__ == "__main__":
    main()
