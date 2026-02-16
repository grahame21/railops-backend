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
print("🚂 RAILOPS - TRAIN SCRAPER - MAXIMUM EXTRACTION")
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
    
    def get_total_feature_count(self):
        """Get total number of features across all sources"""
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
    
    def wait_for_max_trains(self, max_wait=180, target_count=500):
        """Wait until we have a substantial number of trains"""
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains to load (target: {target_count})...")
        
        start_time = time.time()
        best_count = 0
        
        while time.time() - start_time < max_wait:
            current_count = self.get_total_feature_count()
            
            if current_count > best_count:
                best_count = current_count
                print(f"   📈 New peak: {current_count} features at {int(time.time() - start_time)}s")
            
            if current_count >= target_count:
                print(f"   ✅ Reached target: {current_count} features")
                return True
            
            # Every 30 seconds, try to trigger more loading
            elapsed = int(time.time() - start_time)
            if elapsed % 30 == 0 and elapsed > 0:
                print(f"   Still loading... ({current_count} features, best: {best_count})")
                # Pan and zoom to trigger loading
                self.driver.execute_script("""
                    if (window.map) {
                        var view = window.map.getView();
                        var center = view.getCenter();
                        view.setCenter([center[0] + 10000, center[1]]);
                        setTimeout(function() {
                            view.setCenter(center);
                        }, 500);
                    }
                """)
            
            time.sleep(5)
        
        print(f"   ⏰ Timeout reached. Best count: {best_count}")
        return best_count > 100
    
    def extract_trains_direct(self):
        """Extract EVERY train from ALL sources with NO FILTERING"""
        print("\n🔍 Extracting ALL trains from ALL sources (no filtering)...")
        
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
                            
                            // Parse speed from any field that might contain it
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
                            
                            // Create a unique ID - use whatever is available
                            var trainId = props.trainNumber || props.trainName || 
                                         props.serviceName || props.id || props.ID ||
                                         sourceName + '_' + index;
                            
                            // Extract EVERY field we can find, even if empty
                            var trainData = {
                                // Core identifiers
                                'id': String(trainId),
                                'train_number': props.trainNumber || '',
                                'train_name': props.trainName || '',
                                'service_name': props.serviceName || '',
                                
                                // IDs from various sources
                                'cId': props.cId || '',
                                'servId': props.servId || '',
                                'trKey': props.trKey || '',
                                
                                // Movement data
                                'speed': speedNum,
                                'speed_raw': props.trainSpeed || 0,
                                'heading': props.heading || props.Heading || 0,
                                'km': props.trainKM || '',
                                
                                // Service details
                                'origin': props.serviceFrom || '',
                                'destination': props.serviceTo || '',
                                'description': props.serviceDesc || '',
                                'date': props.trainDate || '',
                                'time': props.trainTime || '',
                                
                                // Display data
                                'tooltip': props.tooltipHTML || '',
                                'label_content': props.labelContent || '',
                                'label_anchor': props.labelAnchor || '',
                                'label_style': props.labelStyle || '',
                                
                                // Flags
                                'is_train': props.is_train || false,
                                'is_train_path': props.is_train_path || false,
                                'is_actual_location': props.is_actual_location || false,
                                
                                // Source metadata
                                'source': sourceName,
                                'feature_index': index,
                                
                                // Coordinates
                                'x': coords[0],
                                'y': coords[1]
                            };
                            
                            // Keep EVERY train, even duplicates from different sources
                            // (we'll dedupe by ID later)
                            allTrains.push(trainData);
                        }
                    } catch(e) {
                        // Skip problematic features
                    }
                });
            } catch(e) {}
        });
        
        // Now deduplicate by ID, keeping the version with most data
        var uniqueTrains = {};
        allTrains.forEach(function(train) {
            var id = train.id;
            if (!uniqueTrains[id] || Object.keys(train).length > Object.keys(uniqueTrains[id]).length) {
                uniqueTrains[id] = train;
            }
        });
        
        var finalTrains = Object.values(uniqueTrains);
        console.log('📊 Source statistics:', JSON.stringify(sourceStats));
        console.log('📊 Raw features:', allTrains.length, 'Unique trains:', finalTrains.length);
        
        return finalTrains;
        """
        
        try:
            trains = self.driver.execute_script(script)
            print(f"   ✅ Extracted {len(trains)} unique trains from ALL sources")
            return trains
        except Exception as e:
            print(f"   ❌ Error extracting trains: {e}")
            traceback.print_exc()
            return []
    
    def extract_with_multiple_passes(self):
        """Try multiple extraction strategies"""
        all_trains = []
        
        # Pass 1: Normal extraction
        print("\n🔄 Pass 1: Standard extraction")
        trains1 = self.extract_trains_direct()
        all_trains.extend(trains1)
        
        # Pass 2: Pan the map to load more
        print("\n🔄 Pass 2: Panning map to load more...")
        self.driver.execute_script("""
            if (window.map) {
                var view = window.map.getView();
                var center = view.getCenter();
                // Pan east
                view.setCenter([center[0] + 500000, center[1]]);
                setTimeout(function() {
                    // Pan west
                    view.setCenter([center[0] - 500000, center[1]]);
                }, 2000);
            }
        """)
        time.sleep(5)
        trains2 = self.extract_trains_direct()
        all_trains.extend(trains2)
        
        # Pass 3: Zoom out and in
        print("\n🔄 Pass 3: Zooming to load more...")
        self.driver.execute_script("""
            if (window.map) {
                var view = window.map.getView();
                var zoom = view.getZoom();
                view.setZoom(zoom - 2);
                setTimeout(function() {
                    view.setZoom(zoom);
                }, 3000);
            }
        """)
        time.sleep(5)
        trains3 = self.extract_trains_direct()
        all_trains.extend(trains3)
        
        # Deduplicate by ID
        unique = {}
        for train in all_trains:
            tid = train.get('id', '')
            if tid not in unique:
                unique[tid] = train
        
        final_trains = list(unique.values())
        print(f"\n📊 Combined results: {len(all_trains)} raw, {len(final_trains)} unique")
        
        return final_trains
    
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
            
            # Convert coordinates
            if abs(x) > 180 or abs(y) > 90:
                lat, lon = self.webmercator_to_latlon(x, y)
            else:
                lat, lon = y, x
            
            # Keep EVERY train with valid Australian coordinates
            if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
                train_id = t.get('id', 'unknown')
                
                # Avoid exact duplicates
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
                        'is_train': t.get('is_train', False),
                        'lat': lat,
                        'lon': lon
                    })
        
        print(f"\n📊 Train Statistics:")
        print(f"   Total trains in Australia: {len(australian_trains)}")
        
        # Count what data we have
        with_names = sum(1 for t in australian_trains if t.get('train_name'))
        with_numbers = sum(1 for t in australian_trains if t.get('train_number'))
        with_origin = sum(1 for t in australian_trains if t.get('origin'))
        with_dest = sum(1 for t in australian_trains if t.get('destination'))
        with_speed = sum(1 for t in australian_trains if t.get('speed', 0) > 0)
        
        print(f"   Trains with loco names: {with_names}")
        print(f"   Trains with train numbers: {with_numbers}")
        print(f"   Trains with origin: {with_origin}")
        print(f"   Trains with destination: {with_dest}")
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
            
            # Wait for maximum trains
            if not self.wait_for_max_trains(max_wait=180, target_count=500):
                print("⚠️ Could not reach target count, proceeding with what we have")
            
            # Extract with multiple passes
            raw_trains = self.extract_with_multiple_passes()
            
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
                print(f"   Source: {sample['source']}")
            
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
    # If we got no trains but had trains before, keep the old data
    if len(trains) == 0 and os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE, 'r') as f:
                old_data = json.load(f)
            old_trains = old_data.get('trains', [])
            if len(old_trains) > 0:
                print(f"\n📦 No new trains, keeping existing data ({len(old_trains)} trains)")
                # Still update the timestamp to show we tried
                payload = {
                    "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
                    "note": f"{note} - using cached data",
                    "trains": old_trains
                }
                with open(OUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                print(f"✅ Updated timestamp only, kept {len(old_trains)} trains")
                return
        except Exception as e:
            print(f"⚠️ Could not read old data: {e}")
    
    print(f"\n📝 Writing output: {len(trains)} trains, status: {note}")
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains or []
    }
    
    if os.path.exists(OUT_FILE) and len(trains) > 0:
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
