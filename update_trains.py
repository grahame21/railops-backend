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
        
        # Enable performance logging to see what's happening
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
        
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
                print("✅ Cookies loaded")
                return True
            except:
                pass
        return False
    
    def random_delay(self, min_sec=0.5, max_sec=2):
        time.sleep(random.uniform(min_sec, max_sec))
    
    def debug_page_state(self):
        """Print detailed debug info about the page"""
        print("\n🔍 DEBUG: Checking page state...")
        
        # Check current URL
        current_url = self.driver.current_url
        print(f"   Current URL: {current_url}")
        
        # Check page title
        page_title = self.driver.title
        print(f"   Page title: {page_title}")
        
        # Check for any error messages on the page
        try:
            error_elements = self.driver.find_elements(By.CSS_SELECTOR, '.error, .alert, .warning, [class*="error"]')
            if error_elements:
                print(f"   ⚠️ Found {len(error_elements)} error elements on page")
                for el in error_elements[:3]:
                    print(f"      - {el.text[:100]}")
        except:
            pass
        
        # Check console logs for errors
        try:
            logs = self.driver.get_log('browser')
            error_logs = [log for log in logs if log['level'] == 'SEVERE']
            if error_logs:
                print(f"   ⚠️ Found {len(error_logs)} browser errors:")
                for log in error_logs[:3]:
                    print(f"      - {log['message'][:100]}")
        except:
            pass
        
        # Check what train sources exist
        script = """
        var sources = {
            'regTrainsSource': typeof window.regTrainsSource !== 'undefined',
            'unregTrainsSource': typeof window.unregTrainsSource !== 'undefined',
            'markerSource': typeof window.markerSource !== 'undefined',
            'arrowMarkersSource': typeof window.arrowMarkersSource !== 'undefined',
            'map': typeof window.map !== 'undefined',
            'currentTrains': typeof window.currentTrains !== 'undefined'
        };
        
        var counts = {};
        if (window.regTrainsSource && window.regTrainsSource.getFeatures) {
            counts.regTrainsSource = window.regTrainsSource.getFeatures().length;
        }
        if (window.unregTrainsSource && window.unregTrainsSource.getFeatures) {
            counts.unregTrainsSource = window.unregTrainsSource.getFeatures().length;
        }
        if (window.markerSource && window.markerSource.getFeatures) {
            counts.markerSource = window.markerSource.getFeatures().length;
        }
        if (window.arrowMarkersSource && window.arrowMarkersSource.getFeatures) {
            counts.arrowMarkersSource = window.arrowMarkersSource.getFeatures().length;
        }
        
        return {sources: sources, counts: counts};
        """
        
        try:
            debug = self.driver.execute_script(script)
            print(f"\n   OpenLayers sources:")
            for source, exists in debug['sources'].items():
                if exists:
                    count = debug['counts'].get(source, 'N/A')
                    print(f"      ✅ {source}: {count} features")
                else:
                    print(f"      ❌ {source}: not found")
        except Exception as e:
            print(f"   Error checking sources: {e}")
    
    def check_session_valid(self):
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
    
    def login(self):
        print("\n📌 Logging in...")
        self.driver.get(TF_LOGIN_URL)
        self.random_delay(2, 4)
        
        if "home/nextlevel" in self.driver.current_url and "login" not in self.driver.current_url.lower():
            print("✅ Already logged in")
            return True
        
        try:
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            for char in TF_USERNAME:
                username.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            print("✅ Username entered")
        except:
            print("❌ Could not find username field")
            return False
        
        self.random_delay(0.5, 1.5)
        
        try:
            password = self.driver.find_element(By.ID, "pasS_word")
            for char in TF_PASSWORD:
                password.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            print("✅ Password entered")
        except:
            print("❌ Could not find password field")
            return False
        
        self.random_delay(1, 2)
        
        # Click login
        clicked = self.driver.execute_script("""
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
        
        if clicked:
            print("✅ Login button clicked")
        else:
            print("⚠️ Could not find login button, trying alternative")
            # Try alternative click method
            self.driver.execute_script("""
                var inputs = document.querySelectorAll('input[type="submit"], input[type="button"]');
                for(var i = 0; i < inputs.length; i++) {
                    if(inputs[i].value.includes('Log') || inputs[i].value.includes('Sign')) {
                        inputs[i].click();
                        return;
                    }
                }
            """)
        
        self.random_delay(3, 5)
        
        # Close warning
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
        print("✅ Warning page closed")
        
        self.save_cookies()
        return True
    
    def zoom_to_australia(self):
        self.random_delay(2, 4)
        
        result = self.driver.execute_script("""
            if (window.map) {
                try {
                    var australia = [112, -44, 154, -10];
                    var proj = window.map.getView().getProjection();
                    var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                    window.map.getView().fit(extent, { duration: 3000, maxZoom: 8 });
                    return true;
                } catch(e) {
                    console.log('Zoom error:', e);
                    return false;
                }
            }
            return false;
        """)
        
        if result:
            print("🌏 Zoomed to Australia")
        else:
            print("⚠️ Could not zoom map")
    
    def extract_trains(self):
        script = """
        var allTrains = [];
        var seenIds = new Set();
        
        var sources = ['regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource'];
        var sourceStats = {};
        
        sources.forEach(function(sourceName) {
            var source = window[sourceName];
            if (!source || typeof source.getFeatures !== 'function') {
                sourceStats[sourceName] = 'not found';
                return;
            }
            
            try {
                var features = source.getFeatures();
                sourceStats[sourceName] = features.length + ' features';
                
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
                    } catch(e) {
                        console.log('Error processing feature:', e);
                    }
                });
            } catch(e) {
                sourceStats[sourceName] = 'error: ' + e.toString();
            }
        });
        
        return {
            trains: allTrains,
            stats: sourceStats
        };
        """
        
        try:
            result = self.driver.execute_script(script)
            print(f"\n📊 Source statistics:")
            for source, stat in result['stats'].items():
                print(f"   {source}: {stat}")
            return result['trains']
        except Exception as e:
            print(f"❌ Error extracting trains: {e}")
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
            
            if self.load_cookies():
                self.driver.get(TF_LOGIN_URL)
                self.random_delay(2, 4)
                
                # Debug page state before login check
                self.debug_page_state()
                
                if not self.check_session_valid():
                    print("⚠️ Session expired, logging in again")
                    if not self.login():
                        return [], "Login failed"
            else:
                if not self.login():
                    return [], "Login failed"
            
            # Debug after login
            self.debug_page_state()
            
            print("\n⏳ Waiting 30 seconds for map to stabilize...")
            time.sleep(30)
            
            self.zoom_to_australia()
            
            print("⏳ Waiting 60 seconds for trains to load...")
            time.sleep(60)
            
            # Debug again before extraction
            self.debug_page_state()
            
            print("\n🔍 Extracting trains...")
            raw_trains = self.extract_trains()
            print(f"\n✅ Extracted {len(raw_trains)} raw positions")
            
            if len(raw_trains) > 0:
                print(f"\n📋 First raw train sample:")
                print(json.dumps(raw_trains[0], indent=2))
            
            australian_trains = self.filter_australian_trains(raw_trains)
            
            print(f"\n✅ Australian trains: {len(australian_trains)}")
            
            if australian_trains:
                print(f"\n📋 First Australian train:")
                print(f"   ID: {australian_trains[0]['id']}")
                print(f"   Location: {australian_trains[0]['lat']:.4f}, {australian_trains[0]['lon']:.4f}")
                print(f"   Speed: {australian_trains[0]['speed']} km/h")
            
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
