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
    
    def extract_trains_direct(self):
        """Extract train data with real IDs prioritized"""
        print("\n🔍 Extracting trains directly from sources...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        var sources = ['regTrainsSource', 'unregTrainsSource', 'markerSource'];
        
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
                            
                            // Log ALL property names for debugging
                            console.log('Feature ' + sourceName + '_' + index + ' properties:', Object.keys(props));
                            
                            // Check ALL possible loco number fields
                            var locoNumber = props.loco || props.Loco || 
                                            props.unit || props.Unit || 
                                            props.engine || props.Engine ||
                                            props.locoid || props.LocoId ||
                                            props.locomotive || props.Locomotive ||
                                            props.engine_number || props.EngineNumber ||
                                            props.road_number || props.RoadNumber ||
                                            props.reporting_marks || props.ReportingMarks ||
                                            '';
                            
                            // Check ALL possible train ID fields
                            var trainId = props.train_id || props.trainId || 
                                         props.train_number || props.trainNumber || 
                                         props.service || props.Service || 
                                         props.name || props.NAME ||
                                         props.id || props.ID ||
                                         props.train || props.Train ||
                                         '';
                            
                            // Log what we found
                            if (locoNumber || trainId) {
                                console.log('Found - Loco:', locoNumber, 'Train ID:', trainId);
                            }
                            
                            // Use loco as primary ID if available, otherwise use train ID
                            var primaryId = locoNumber || trainId || sourceName + '_' + index;
                            
                            var trainData = {
                                'id': primaryId,
                                'loco': locoNumber,
                                'train_id': trainId,
                                'train_number': props.train_number || props.trainNumber || '',
                                'unit': props.unit || props.Unit || '',
                                'operator': props.operator || props.Operator || '',
                                'origin': props.origin || props.from || '',
                                'destination': props.destination || props.to || '',
                                'speed': props.speed || props.Speed || 0,
                                'heading': props.heading || props.Heading || 0,
                                'eta': props.eta || props.ETA || '',
                                'status': props.status || props.Status || '',
                                'type': props.type || props.Type || '',
                                'cars': props.cars || props.Cars || 0,
                                'line': props.line || props.Line || props.route || '',
                                'x': coords[0],
                                'y': coords[1]
                            };
                            
                            // Skip markerSource trains without real identifiers
                            if (sourceName === 'markerSource' && !locoNumber && !trainId) {
                                return;
                            }
                            
                            var uniqueId = primaryId;
                            if (!seenIds.has(uniqueId)) {
                                seenIds.add(uniqueId);
                                allTrains.push(trainData);
                            }
                        }
                    } catch(e) {
                        console.log('Error processing feature:', e);
                    }
                });
            } catch(e) {
                console.log('Error accessing source:', e);
            }
        });
        
        return allTrains;
        """
        
        try:
            trains = self.driver.execute_script(script)
            print(f"   ✅ Extracted {len(trains)} trains from OpenLayers sources")
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
        
        real_count = 0
        generic_count = 0
        
        for t in raw_trains:
            x = t.get('x', 0)
            y = t.get('y', 0)
            
            if abs(x) > 180 or abs(y) > 90:
                lat, lon = self.webmercator_to_latlon(x, y)
            else:
                lat, lon = y, x
            
            if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
                train_id = t.get('id', 'unknown')
                
                if t.get('loco') or t.get('train_id'):
                    real_count += 1
                else:
                    generic_count += 1
                
                if train_id not in seen_ids:
                    seen_ids.add(train_id)
                    australian_trains.append({
                        'id': train_id,
                        'loco': t.get('loco', ''),
                        'train_id': t.get('train_id', ''),
                        'train_number': t.get('train_number', ''),
                        'unit': t.get('unit', ''),
                        'operator': t.get('operator', ''),
                        'origin': t.get('origin', ''),
                        'destination': t.get('destination', ''),
                        'speed': round(float(t.get('speed', 0)), 1),
                        'heading': round(float(t.get('heading', 0)), 1),
                        'eta': t.get('eta', ''),
                        'status': t.get('status', ''),
                        'type': t.get('type', ''),
                        'cars': t.get('cars', 0),
                        'line': t.get('line', ''),
                        'lat': lat,
                        'lon': lon
                    })
        
        print(f"\n📊 Train Statistics:")
        print(f"   Real train IDs: {real_count}")
        print(f"   Generic IDs: {generic_count}")
        
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
            
            print("⏳ Waiting 60 seconds for trains to load...")
            time.sleep(60)
            
            raw_trains = self.extract_trains_direct()
            
            print(f"\n✅ Total raw trains before filtering: {len(raw_trains)}")
            
            if raw_trains:
                print(f"\n📋 First raw train sample:")
                sample = raw_trains[0]
                print(f"   ID: {sample.get('id')}")
                print(f"   Loco: {sample.get('loco')}")
                print(f"   Train ID: {sample.get('train_id')}")
                print(f"   Speed: {sample.get('speed')}")
                print(f"   Location: ({sample.get('x')}, {sample.get('y')})")
            
            australian_trains = self.filter_australian_trains(raw_trains)
            
            print(f"\n✅ Australian trains after filtering: {len(australian_trains)}")
            
            if australian_trains:
                print(f"\n📋 Sample Australian train:")
                sample = australian_trains[0]
                print(f"   ID: {sample['id']}")
                print(f"   Loco: {sample['loco']}")
                print(f"   Train ID: {sample['train_id']}")
                print(f"   Operator: {sample['operator']}")
                print(f"   Origin: {sample['origin']}")
                print(f"   Destination: {sample['destination']}")
                print(f"   Speed: {sample['speed']} km/h")
                print(f"   Location: {sample['lat']:.4f}, {sample['lon']:.4f}")
            
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
    print(f"\n📝 Writing output: {len(trains)} trains, status: {note}")
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
        except Exception as e:
            print(f"⚠️ Could not create backup: {e}")
    
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"✅ Output written to {OUT_FILE}")
    except Exception as e:
        print(f"❌ Failed to write output: {e}")

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
