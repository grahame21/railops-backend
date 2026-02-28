import os
import json
import datetime
import time
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"

print("🚀 Starting fast scrape...")

# Load cookies
if not os.path.exists(COOKIE_FILE):
    print("❌ No cookie file found")
    exit(1)

with open(COOKIE_FILE, 'rb') as f:
    cookies = pickle.load(f)

# Setup driver with better options
options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1920,1080')
options.add_argument('--disable-blink-features=AutomationControlled')
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)

driver = webdriver.Chrome(options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

# Inject cookies
driver.get("https://trainfinder.otenko.com")
time.sleep(2)
for cookie in cookies:
    try:
        driver.add_cookie(cookie)
    except:
        pass

# Load map page
driver.get("https://trainfinder.otenko.com/home/nextlevel")
print("✅ Page loaded, waiting for map...")
time.sleep(10)

# Extract trains from ALL sources that ever contained trains
trains = driver.execute_script("""
var allTrains = [];
var seenIds = new Set();

// ALL sources that have ever contained trains
var sources = [
    'regTrainsSource',
    'unregTrainsSource', 
    'markerSource',
    'arrowMarkersSource',
    'trainSource',
    'trainMarkers',
    'trainPoints'
];

sources.forEach(function(sourceName) {
    var source = window[sourceName];
    if (!source || !source.getFeatures) return;
    
    var features = source.getFeatures();
    console.log(sourceName + ' has ' + features.length + ' features');
    
    features.forEach(function(feature) {
        try {
            var props = feature.getProperties();
            var geom = feature.getGeometry();
            
            if (!geom || geom.getType() !== 'Point') return;
            
            var coords = geom.getCoordinates();
            
            // Convert Web Mercator to lat/lon
            var x = coords[0];
            var y = coords[1];
            var lon = (x / 20037508.34) * 180;
            var lat = (y / 20037508.34) * 180;
            lat = 180 / Math.PI * (2 * Math.atan(Math.exp(lat * Math.PI / 180)) - Math.PI / 2);
            
            // Skip if not in Australia
            if (lat < -45 || lat > -9 || lon < 110 || lon > 155) return;
            
            // Get ALL available train data
            var trainNumber = props.trainNumber || props.train_number || '';
            var trainName = props.trainName || props.train_name || '';
            var origin = props.serviceFrom || props.origin || '';
            var destination = props.serviceTo || props.destination || '';
            var description = props.serviceDesc || props.description || '';
            var km = props.trainKM || props.km || '';
            var trainTime = props.trainTime || props.time || '';
            var trainDate = props.trainDate || props.date || '';
            var cId = props.cId || '';
            var servId = props.servId || '';
            var trKey = props.trKey || '';
            
            var speed = 0;
            if (props.trainSpeed) {
                var match = String(props.trainSpeed).match(/(\\d+)/);
                if (match) speed = parseInt(match[0]);
            }
            
            // Create unique ID
            var id = trainName || trainNumber || origin || sourceName + '_' + features.indexOf(feature);
            
            if (!seenIds.has(id)) {
                seenIds.add(id);
                allTrains.push({
                    'id': id,
                    'train_number': trainNumber,
                    'train_name': trainName,
                    'speed': speed,
                    'origin': origin,
                    'destination': destination,
                    'description': description,
                    'km': km,
                    'time': trainTime,
                    'date': trainDate,
                    'cId': cId,
                    'servId': servId,
                    'trKey': trKey,
                    'lat': lat,
                    'lon': lon
                });
            }
        } catch(e) {}
    });
});

return allTrains;
""")

driver.quit()
print(f"✅ Extracted {len(trains)} trains")

# Write output
output = {
    "lastUpdated": datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
    "note": f"ok - {len(trains)} trains",
    "trains": trains
}

with open(OUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2)

print(f"✅ Saved to {OUT_FILE}")
