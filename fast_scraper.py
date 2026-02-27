import os
import json
import datetime
import time
import math
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

print("=" * 60)
print("🚂 FAST TRAIN SCRAPER")
print("=" * 60)
print(f"Current time: {datetime.datetime.now()}")
print("=" * 60)

OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"

class FastScraper:
    def __init__(self):
        self.driver = None
        
    def load_cookies(self):
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"⚠️ Could not load cookies: {e}")
        return None
    
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--window-size=1920,1080')
        self.driver = webdriver.Chrome(options=chrome_options)
        return True
    
    def inject_cookies(self, cookies):
        try:
            self.driver.get("https://trainfinder.otenko.com")
            time.sleep(2)
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass
            self.driver.get("https://trainfinder.otenko.com/home/nextlevel")
            print("✅ Page loaded, waiting for map...")
            time.sleep(5)
            return True
        except Exception as e:
            print(f"❌ Cookie injection failed: {e}")
            return False
    
    def check_session_valid(self):
        try:
            if "login" in self.driver.current_url.lower():
                print("❌ Redirected to login page")
                return False
            map_exists = self.driver.execute_script("return typeof window.map !== 'undefined'")
            if map_exists:
                print("✅ Map loaded")
                return True
            else:
                print("⚠️ Map not detected")
                return False
        except:
            return False
    
    def wait_for_trains(self, max_wait=30):
        """Wait for trains to appear"""
        print("\n⏳ Waiting for trains to load...")
        
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
        
        for i in range(max_wait):
            try:
                count = self.driver.execute_script(script)
                if count > 10:
                    print(f"✅ Found {count} trains after {i} seconds")
                    return True
                if i % 5 == 0:
                    print(f"   ... {count} trains so far")
                time.sleep(1)
            except:
                time.sleep(1)
        
        final_count = self.driver.execute_script(script)
        print(f"⚠️ Only found {final_count} trains after {max_wait} seconds")
        return final_count > 0
    
    def extract_trains(self):
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
                    var trainNumber = props.trainNumber || '';
                    var trainName = props.trainName || '';
                    var origin = props.serviceFrom || '';
                    var destination = props.serviceTo || '';
                    if (!trainNumber && !trainName && !origin && !destination) return;
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
            print(f"✅ Extracted {len(trains)} raw trains")
            return trains
        except Exception as e:
            print(f"❌ Extraction error: {e}")
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
        return result
    
    def run(self):
        print("\n🚀 Starting fast scrape...")
        
        cookies = self.load_cookies()
        if not cookies:
            print("❌ No cookies found")
            return []
        
        if not self.setup_driver():
            return []
        
        if not self.inject_cookies(cookies):
            self.driver.quit()
            return []
        
        if not self.check_session_valid():
            self.driver.quit()
            return []
        
        self.wait_for_trains(max_wait=30)
        
        raw_trains = self.extract_trains()
        australian = self.filter_australian(raw_trains)
        print(f"\n📊 Australian trains: {len(australian)}")
        
        self.driver.quit()
        return australian

def write_output(trains):
    if not trains:
        print("⚠️ No trains to write - keeping existing data")
        return
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": f"ok - {len(trains)} trains",
        "trains": trains
    }
    with open(OUT_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"✅ Wrote {len(trains)} trains to {OUT_FILE}")

def main():
    scraper = FastScraper()
    trains = scraper.run()
    write_output(trains)

if __name__ == "__main__":
    main()
