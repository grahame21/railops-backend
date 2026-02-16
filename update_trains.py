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
    
    def wait_for_trains(self, max_wait=120):
        """Wait until trains actually appear in the sources"""
        print(f"\n⏳ Waiting up to {max_wait} seconds for trains to appear...")
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            # Check current train count
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
                current_count = self.driver.execute_script(script)
                
                # If we have more than just the artifact (1 feature), we have trains
                if current_count > 10:  # Wait until we have a substantial number
                    print(f"   ✅ Found {current_count} features after {int(time.time() - start_time)}s")
                    return True
                
                # Print progress every 10 seconds
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0 and elapsed > 0:
                    print(f"   Still waiting... ({current_count} features after {elapsed}s)")
                    
            except Exception as e:
                pass
            
            time.sleep(2)
        
        print(f"   ⚠️ Timeout reached with no trains")
        return False
    
    def extract_trains_direct(self):
        """Extract ALL train data from ALL available sources"""
        print("\n🔍 Extracting trains from ALL sources...")
        
        script = """
        var allTrains = [];
        var seenIds = new Set();
        var sourceStats = {};
        
        // Get ALL possible sources - including those with many features
        var sources = [
            'regTrainsSource',     // Registered trains
            'unregTrainsSource',   // Unregistered trains
            'markerSource',        // Markers
            'arrowMarkersSource',  // Arrow markers (these have data too!)
            'trainSource',         // Generic train source
            'trainMarkers',        // Train markers
            'trainPoints'          // Train points
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
                            
                            // Parse speed - extract numeric value from strings like "5 km/h"
                            var speedValue = props.trainSpeed || 0;
                            var speedNum = 0;
                            if (typeof speedValue === 'string') {
                                var match = speedValue.match(/(\\d+\\.?\\d*)/);
                                if (match) {
                                    speedNum = parseFloat(match[1]);
                                }
                            } else if (typeof speedValue === 'number') {
                                speedNum = speedValue;
                            }
                            
                            // Extract ALL available fields
                            var trainData = {
                                // Core identifiers
                                'id': props.trainNumber || props.trainName || props.serviceName || 
                                      props.id || props.ID || sourceName + '_' + index,
                                'train_number': props.trainNumber || '',
                                'train_name': props.trainName || '',
                                'service_name': props.serviceName || '',
                                
                                // Loco/consist info
                                'consist_id': props.cId || '',
                                'service_id': props.servId || '',
                                'tr_key': props.trKey || '',
                                
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
                                
                                // Source info (for debugging)
                                'source': sourceName,
                                
                                // Coordinates
                                'x': coords[0],
                                'y': coords[1]
                            };
                            
                            // Create unique ID - try multiple fields
                            var uniqueId = trainData.train_number || trainData.train_name || 
                                          trainData.service_name || trainData.id || 
                                          sourceName + '_' + index;
                            
                            if (!seenIds.has(uniqueId)) {
                                seenIds.add(uniqueId);
                                allTrains.push(trainData);
                            }
                        }
                    } catch(e) {}
                });
            } catch(e) {}
        });
        
        // Log source statistics
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
    
    def extract_with_retry(self, max_retries=3):
        """Try to extract trains multiple times if initial attempt fails"""
        
        for attempt in range(max_retries):
            print(f"\n🔄 Extraction attempt {attempt + 1}/{max_retries}")
            
            # Try direct extraction
            raw_trains = self.extract_trains_direct()
            
            if len(raw_trains) > 100:  # Success! We have a good number of trains
                print(f"   ✅ Successfully extracted {len(raw_trains)} trains")
                return raw_trains
            
            # If not enough trains, wait and try zooming again
            print(f"   ⚠️ Only found {len(raw_trains)} trains, waiting and retrying...")
            
            if attempt < max_retries - 1:
                # Zoom out and back in to trigger loading
                self.driver.execute_script("""
                    if (window.map) {
                        var view = window.map.getView();
                        var zoom = view.getZoom();
                        view.setZoom(zoom - 1);
                        setTimeout(function() {
                            view.setZoom(zoom);
                        }, 1000);
                    }
                """)
                time.sleep(15)  # Wait for new data to load
        
        return raw_trains  # Return what we got, even if less than expected
    
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
                        'consist_id': t.get('consist_id', ''),
                        'service_id': t.get('service_id', ''),
                        'tr_key': t.get('tr_key', ''),
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
        print(f"   Total trains extracted: {len(australian_trains)}")
        
        # Count trains with various fields
        with_names = sum(1 for t in australian_trains if t.get('train_name'))
        with_numbers = sum(1 for t in australian_trains if t.get('train_number'))
        with_origin = sum(1 for t in australian_trains if t.get('origin'))
        with_dest = sum(1 for t in australian_trains if t.get('destination'))
        print(f"   Trains with loco names: {with_names}")
        print(f"   Trains with train numbers: {with_numbers}")
        print(f"   Trains with origin: {with_origin}")
        print(f"   Trains with destination: {with_dest}")
        
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
            
            # Wait for trains to actually appear (up to 2 minutes)
            if not self.wait_for_trains(max_wait=120):
                print("⚠️ No trains appeared within timeout")
                return [], "timeout - no trains"
            
            # Try to extract with retries
            raw_trains = self.extract_with_retry(max_retries=3)
            
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
                print(f"   Location: ({sample.get('x')}, {sample.get('y')})")
            
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
                print(f"   Source: {sample['source']}")
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
