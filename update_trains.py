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
print("🚂 RAILOPS - TRAIN SCRAPER - FIXED VERSION")
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
            traceback.print_exc()
            return False
    
    def login(self):
        if self.load_cookies():
            self.driver.get(TF_LOGIN_URL)
            self.random_delay(3, 5)
            if self.check_session_valid():
                print("✅ Using saved session")
                return True
            else:
                print("⚠️ Saved session invalid, doing fresh login")
                return self.force_fresh_login()
        else:
            return self.force_fresh_login()
    
    def zoom_to_australia(self):
        self.random_delay(2, 4)
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
        """Get feature counts from ALL sources"""
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
    
    def wait_for_trains(self, max_wait=240):
        """Wait until we have a substantial number of features from ANY source"""
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains to load...")
        
        start_time = time.time()
        best_count = 0
        
        while time.time() - start_time < max_wait:
            counts = self.get_all_feature_counts()
            total = sum(counts.values())
            
            if total > best_count:
                best_count = total
                print(f"   📈 New peak: {total} features at {int(time.time() - start_time)}s")
                print(f"      Sources: {counts}")
            
            if total > 100:  # We have a good number of trains
                print(f"   ✅ Found {total} features, proceeding...")
                return True
            
            # Every 30 seconds, try to trigger more loading
            elapsed = int(time.time() - start_time)
            if elapsed % 30 == 0 and elapsed > 0:
                print(f"   Still loading... ({total} features after {elapsed}s)")
                # Pan the map to trigger loading
                self.driver.execute_script("""
                    if (window.map) {
                        var view = window.map.getView();
                        var center = view.getCenter();
                        view.setCenter([center[0] + 100000, center[1]]);
                        setTimeout(function() {
                            view.setCenter(center);
                        }, 1000);
                    }
                """)
            
            time.sleep(5)
        
        print(f"   ⏰ Timeout reached. Best count: {best_count}")
        return best_count > 50  # Return True if we got at least some trains
    
    def extract_all_trains(self):
        """Extract ALL trains from ALL sources with rich data"""
        print("\n🔍 Extracting ALL trains from ALL sources...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        var sourceStats = {};
        
        // ALL possible sources
        var sources = [
            'regTrainsSource',
            'unregTrainsSource',
            'markerSource',
            'arrowMarkersSource'
        ];
        
        sources.forEach(function(sourceName) {
            var source = window[sourceName];
            if (!source || !source.getFeatures) return;
            
            try {
                var features = source.getFeatures();
                sourceStats[sourceName] = features.length;
                
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
                            
                            // Get the best available ID
                            var trainId = props.trainNumber || props.trainName || 
                                         props.serviceName || props.id || props.ID ||
                                         sourceName + '_' + index;
                            
                            // Extract ALL available fields
                            var trainData = {
                                'id': String(trainId),
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
                            
                            // Keep ALL trains, even if they have minimal data
                            // Just avoid exact duplicates
                            if (!seenIds.has(trainId)) {
                                seenIds.add(trainId);
                                allTrains.push(trainData);
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        });
        
        console.log('📊 Source statistics:', JSON.stringify(sourceStats));
        return allTrains;
        """
        
        try:
            trains = self.driver.execute_script(script)
            print(f"   ✅ Extracted {len(trains)} trains from ALL sources")
            return trains
        except Exception as e:
            print(f"   ❌ Error extracting trains: {e}")
            traceback.print_exc()
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
        
        print(f"\n📊 Train Statistics:")
        print(f"   Total trains in Australia: {len(australian_trains)}")
        
        # Count rich data
        with_names = sum(1 for t in australian_trains if t.get('train_name'))
        with_numbers = sum(1 for t in australian_trains if t.get('train_number'))
        with_origin = sum(1 for t in australian_trains if t.get('origin'))
        with_dest = sum(1 for t in australian_trains if t.get('destination'))
        with_desc = sum(1 for t in australian_trains if t.get('description'))
        with_speed = sum(1 for t in australian_trains if t.get('speed', 0) > 0)
        
        print(f"   Trains with loco names: {with_names}")
        print(f"   Trains with train numbers: {with_numbers}")
        print(f"   Trains with origin: {with_origin}")
        print(f"   Trains with destination: {with_dest}")
        print(f"   Trains with description: {with_desc}")
        print(f"   Trains with speed > 0: {with_speed}")
        
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
            
            # Wait for trains to load (up to 4 minutes)
            if not self.wait_for_trains(max_wait=240):
                print("⚠️ Fewer trains than expected, but proceeding anyway")
            
            # Extract ALL trains
            raw_trains = self.extract_all_trains()
            
            print(f"\n✅ Total raw trains before filtering: {len(raw_trains)}")
            
            if raw_trains:
                print(f"\n📋 First raw train sample:")
                sample = raw_trains[0]
                print(f"   ID: {sample.get('id')}")
                print(f"   Train Number: {sample.get('train_number')}")
                print(f"   Train Name: {sample.get('train_name')}")
                print(f"   Origin: {sample.get('origin')}")
                print(f"   Destination: {sample.get('destination')}")
                print(f"   Speed: {sample.get('speed')}")
                print(f"   Source: {sample.get('source')}")
            
            australian_trains = self.filter_australian_trains(raw_trains)
            
            print(f"\n✅ Australian trains after filtering: {len(australian_trains)}")
            
            if australian_trains:
                print(f"\n📋 Sample Australian train:")
                sample = australian_trains[0]
                print(f"   ID: {sample['id']}")
                print(f"   Train Number: {sample['train_number']}")
                print(f"   Train Name: {sample['train_name']}")
                print(f"   Origin: {sample['origin']}")
                print(f"   Destination: {sample['destination']}")
                print(f"   Speed: {sample['speed']} km/h")
                print(f"   Description: {sample['description']}")
            
            return australian_trains, f"ok - {len(australian_trains)} trains"
            
        except Exception as e:
            print(f"\n❌ Error in run: {e}")
            traceback.print_exc()
            return [], f"error: {type(e).__name__}"
        finally:
            if self.driver:
                self.driver.quit()
                print("👋 Browser closed")

def write_output(trains, note=""):
    # If we got trains, always write them
    if len(trains) > 0:
        print(f"\n📝 Writing output: {len(trains)} trains, status: {note}")
        payload = {
            "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
            "note": note,
            "trains": trains
        }
        
        # Create backup
        try:
            if os.path.exists(OUT_FILE):
                backup_name = f"trains_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(OUT_FILE, 'r') as src:
                    with open(backup_name, 'w') as dst:
                        dst.write(src.read())
                print(f"💾 Backup created: {backup_name}")
        except:
            pass
        
        try:
            with open(OUT_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"✅ Output written to {OUT_FILE}")
        except Exception as e:
            print(f"❌ Failed to write output: {e}")
    else:
        print("\n⚠️ No trains extracted, keeping previous file")

def main():
    print("\n🏁 Starting main function...")
    scraper = TrainScraper()
    trains, note = scraper.run()
    write_output(trains, note)
    print("\n✅ Script completed")
    
    if "error" in note:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
