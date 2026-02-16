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
        for attempt in range(3):
            try:
                chrome_options = Options()
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument('--headless=new')
                
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
                print(f"❌ Attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(5)
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
            return False
    
    def login(self):
        if self.load_cookies():
            self.driver.get(TF_LOGIN_URL)
            self.random_delay(3, 6)
            if self.check_session_valid():
                print("✅ Using saved session")
                return True
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
    
    def get_feature_count(self):
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
    
    def wait_for_trains(self, max_wait=180):
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains to load...")
        start_time = time.time()
        while time.time() - start_time < max_wait:
            count = self.get_feature_count()
            if count > 10:
                print(f"   ✅ Found {count} trains after {int(time.time() - start_time)}s")
                return True
            if int(time.time() - start_time) % 30 == 0:
                print(f"   Still waiting... ({count} trains)")
            time.sleep(5)
        return False
    
    def extract_real_trains(self):
        print("\n🔍 Extracting REAL trains...")
        script = """
        var realTrains = [];
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
                    var trainNumber = props.trainNumber || '';
                    var trainName = props.trainName || '';
                    var origin = props.serviceFrom || '';
                    var destination = props.serviceTo || '';
                    
                    if (!trainNumber && !trainName && !origin && !destination) return;
                    
                    var speedValue = props.trainSpeed || 0;
                    var speedNum = 0;
                    if (typeof speedValue === 'string') {
                        var match = speedValue.match(/(\\d+)/);
                        if (match) speedNum = parseInt(match[0]);
                    } else {
                        speedNum = parseInt(speedValue) || 0;
                    }
                    
                    var displayId = trainName || trainNumber;
                    if (!displayId || seenIds.has(displayId)) return;
                    
                    seenIds.add(displayId);
                    realTrains.push({
                        'id': displayId,
                        'train_number': trainNumber,
                        'train_name': trainName,
                        'speed': speedNum,
                        'origin': origin,
                        'destination': destination,
                        'description': props.serviceDesc || '',
                        'km': props.trainKM || '',
                        'time': props.trainTime || '',
                        'cId': props.cId or '',
                        'servId': props.servId or '',
                        'trKey': props.trKey or '',
                        'x': coords[0],
                        'y': coords[1]
                    });
                } catch(e) {}
            });
        });
        return realTrains;
        """
        try:
            trains = self.driver.execute_script(script)
            print(f"   ✅ Extracted {len(trains)} REAL trains")
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
                train_id = t.get('id', 'unknown')
                if train_id not in seen_ids:
                    seen_ids.add(train_id)
                    australian_trains.append({
                        'id': train_id,
                        'train_number': t.get('train_number', ''),
                        'train_name': t.get('train_name', ''),
                        'speed': t.get('speed', 0),
                        'origin': t.get('origin', ''),
                        'destination': t.get('destination', ''),
                        'description': t.get('description', ''),
                        'km': t.get('km', ''),
                        'time': t.get('time', ''),
                        'cId': t.get('cId', ''),
                        'servId': t.get('servId', ''),
                        'trKey': t.get('trKey', ''),
                        'lat': lat,
                        'lon': lon
                    })
        return australian_trains
    
    def run(self):
        print("\n🚀 Starting scraper run...")
        if not self.setup_driver() or not self.login():
            return [], "Setup failed"
        try:
            print("\n⏳ Waiting 30 seconds for map to stabilize...")
            time.sleep(30)
            self.zoom_to_australia()
            self.wait_for_trains(max_wait=180)
            raw_trains = self.extract_real_trains()
            australian_trains = self.filter_australian_trains(raw_trains)
            return australian_trains, f"ok - {len(australian_trains)} trains"
        finally:
            if self.driver:
                self.driver.quit()
                print("👋 Browser closed")

def write_output(trains, note=""):
    if trains:
        payload = {
            "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
            "note": note,
            "trains": trains
        }
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"✅ Wrote {len(trains)} trains")

def main():
    scraper = TrainScraper()
    trains, note = scraper.run()
    write_output(trains, note)

if __name__ == "__main__":
    main()
