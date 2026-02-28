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

# Setup driver
options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1920,1080')
driver = webdriver.Chrome(options=options)

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

# Extract trains - EXACTLY as it worked before
trains = driver.execute_script("""
var allTrains = [];
var seenIds = new Set();

// ONLY these sources - they worked before
var sources = ['regTrainsSource', 'unregTrainsSource'];

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
            
            // Get ALL the rich data from that successful run
            var trainData = {
                'id': props.trainName || props.trainNumber || sourceName + '_' + features.indexOf(feature),
                'train_number': props.trainNumber || '',
                'train_name': props.trainName || '',
                'service_name': props.serviceName || '',
                'cId': props.cId || '',
                'servId': props.servId || '',
                'trKey': props.trKey || '',
                'speed': 0,
                'km': props.trainKM || '',
                'origin': props.serviceFrom || '',
                'destination': props.serviceTo || '',
                'description': props.serviceDesc || '',
                'date': props.trainDate || '',
                'time': props.trainTime || '',
                'tooltip': props.tooltipHTML || '',
                'is_train': props.is_train || false,
                'lat': lat,
                'lon': lon
            };
            
            // Parse speed
            if (props.trainSpeed) {
                var match = String(props.trainSpeed).match(/(\d+)/);
                if (match) trainData.speed = parseInt(match[0]);
            }
            
            if (!seenIds.has(trainData.id)) {
                seenIds.add(trainData.id);
                allTrains.push(trainData);
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
    "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
    "note": f"ok - {len(trains)} trains",
    "trains": trains
}

with open(OUT_FILE, 'w') as f:
    json.dump(output, f, indent=2)

print(f"✅ Saved to {OUT_FILE}")
