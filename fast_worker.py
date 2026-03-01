import os
import json
import time
import math
import pickle
import random
import datetime
import signal
import sys

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

# Jitter timing
BASE_MIN_SECONDS = int(os.environ.get("BASE_MIN_SECONDS", "30"))
BASE_MAX_SECONDS = int(os.environ.get("BASE_MAX_SECONDS", "60"))

# Backoff
MIN_TRAINS_OK = int(os.environ.get("MIN_TRAINS_OK", "50"))
MAX_BACKOFF_SECONDS = int(os.environ.get("MAX_BACKOFF_SECONDS", "900"))

# Chromium paths inside the container
CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")

STOP = False

def handle_sigint(sig, frame):
    global STOP
    STOP = True

signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGTERM, handle_sigint)

print("=" * 60)
print("🚂 RAILOPS - FAST WORKER (Xvfb + proven OL extraction)")
print("=" * 60)

def utc_now_z():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

def write_output(trains, note=""):
    payload = {
        "lastUpdated": utc_now_z(),
        "note": note,
        "trains": trains or []
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"📝 Output: {len(trains or [])} trains | {note}")

def webmercator_to_latlon(x, y):
    try:
        x = float(x)
        y = float(y)
        lon = (x / 20037508.34) * 180
        lat = (y / 20037508.34) * 180
        lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
        return round(lat, 6), round(lon, 6)
    except:
        return None, None

def make_driver():
    chrome_options = Options()
    chrome_options.binary_location = CHROME_BIN

    # IMPORTANT: we will run under Xvfb, so we do NOT need --headless
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=en-AU")

    # Reduce automation fingerprints a bit
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    service = webdriver.ChromeService(executable_path=CHROMEDRIVER_BIN)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)

    # further reduce webdriver flag
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except:
        pass

    return driver

def close_warning(driver):
    try:
        driver.execute_script("""
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
        print("✅ Warning close attempted")
    except:
        pass

def ensure_logged_in(driver):
    driver.get(TF_LOGIN_URL)
    time.sleep(5)

    # Load cookies if exist
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "rb") as f:
                cookies = pickle.load(f)
            for c in cookies:
                try:
                    driver.add_cookie(c)
                except:
                    pass
            driver.get(TF_LOGIN_URL)
            time.sleep(4)
            print("✅ Loaded saved cookies")
        except:
            pass

    # If login inputs appear, login
    page = (driver.page_source or "").lower()
    if ("user_name" in page) or ("pass_word" in page) or ("useR_name".lower() in page):
        if not TF_USERNAME or not TF_PASSWORD:
            raise RuntimeError("Missing TF_USERNAME / TF_PASSWORD")

        print("🔐 Logging in…")
        username = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.clear()
        username.send_keys(TF_USERNAME)

        password = driver.find_element(By.ID, "pasS_word")
        password.clear()
        password.send_keys(TF_PASSWORD)

        # click Log In
        driver.execute_script("""
            var buttons = document.querySelectorAll('input[type="button"], button, div.button-green');
            for (var i=0;i<buttons.length;i++){
              var t = (buttons[i].value || buttons[i].textContent || '').toLowerCase();
              if (t.includes('log in') || buttons[i].className.includes('button-green')) {
                buttons[i].click(); break;
              }
            }
        """)
        time.sleep(6)

        # Save cookies
        try:
            with open(COOKIE_FILE, "wb") as f:
                pickle.dump(driver.get_cookies(), f)
            print("✅ Cookies saved")
        except:
            pass
    else:
        print("✅ Session appears logged-in (no login form detected).")

    close_warning(driver)

def warmup_map(driver):
    # Let map stabilise and load trains
    print("⏳ Warmup: waiting 25s for map…")
    time.sleep(25)

    # Zoom to Australia
    print("🌏 Zooming to Australia…")
    driver.execute_script("""
        try {
          if (window.map && window.ol && ol.proj && window.map.getView) {
            var australia = [112, -44, 154, -10];
            var proj = window.map.getView().getProjection();
            var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
            window.map.getView().fit(extent, { duration: 0, maxZoom: 8 });
          }
        } catch(e) {}
    """)
    time.sleep(10)

    print("⏳ Warmup: waiting 45s for trains…")
    time.sleep(45)

EXTRACT_SCRIPT = r"""
var allTrains = [];
var sources = [
  'regTrainsSource','unregTrainsSource','markerSource',
  'arrowMarkersSource','trainSource','trainMarkers'
];

sources.forEach(function(sourceName){
  var source = window[sourceName];
  if (!source || !source.getFeatures) return;
  var features = source.getFeatures();

  features.forEach(function(feature, idx){
    try {
      var props = feature.getProperties();
      var geom = feature.getGeometry();
      if (!geom || geom.getType() !== 'Point') return;
      var coords = geom.getCoordinates();

      var trainData = {
        'id': props.id || props.ID || (sourceName + '_' + idx),
        'train_number': props.trainNumber || props.train_number || '',
        'train_name': props.trainName || props.train_name || '',
        'service_name': props.serviceName || '',
        'loco': props.loco || '',
        'operator': props.operator || '',
        'origin': props.serviceFrom || props.origin || '',
        'destination': props.serviceTo || props.destination || '',
        'speed': 0,
        'heading': props.heading || 0,
        'km': props.trainKM || '',
        'time': props.trainTime || '',
        'date': props.trainDate || '',
        'description': props.serviceDesc || '',
        'cId': props.cId || '',
        'servId': props.servId || '',
        'trKey': props.trKey || '',
        'x': coords[0],
        'y': coords[1]
      };

      if (props.trainSpeed) {
        var match = String(props.trainSpeed).match(/(\d+)/);
        if (match) trainData.speed = parseInt(match[0]);
      }

      allTrains.push(trainData);
    } catch(e) {}
  });
});

return allTrains;
"""

def extract_trains(driver):
    # try multiple times quickly (in case layers are still updating)
    for _ in range(10):
        raw = driver.execute_script(EXTRACT_SCRIPT) or []
        if len(raw) >= 50:
            return raw
        time.sleep(2)
    return driver.execute_script(EXTRACT_SCRIPT) or []

def normalize(raw_trains):
    trains = []
    for t in raw_trains or []:
        lat, lon = webmercator_to_latlon(t.get("x"), t.get("y"))
        if lat and lon and -45 <= lat <= -9 and 110 <= lon <= 155:
            trains.append({
                "id": t.get("id","unknown"),
                "train_number": t.get("train_number",""),
                "train_name": t.get("train_name",""),
                "loco": t.get("loco",""),
                "operator": t.get("operator",""),
                "origin": t.get("origin",""),
                "destination": t.get("destination",""),
                "speed": t.get("speed",0),
                "heading": t.get("heading",0),
                "km": t.get("km",""),
                "time": t.get("time",""),
                "date": t.get("date",""),
                "description": t.get("description",""),
                "cId": t.get("cId",""),
                "servId": t.get("servId",""),
                "trKey": t.get("trKey",""),
                "lat": lat,
                "lon": lon
            })
    return trains

def main():
    if not TF_USERNAME or not TF_PASSWORD:
        raise RuntimeError("Missing TF_USERNAME/TF_PASSWORD Fly secrets")

    backoff = 0
    driver = None

    try:
        driver = make_driver()
        ensure_logged_in(driver)
        warmup_map(driver)

        print("🚦 Worker loop started (30–60s jitter + backoff)")

        while not STOP:
            try:
                raw = extract_trains(driver)
                trains = normalize(raw)

                if len(trains) < MIN_TRAINS_OK:
                    backoff = min(MAX_BACKOFF_SECONDS, (backoff * 2) if backoff else 120)
                    write_output(trains, f"Low train count ({len(trains)}). Backoff {backoff}s")
                    time.sleep(backoff)
                    driver.refresh()
                    time.sleep(10)
                    close_warning(driver)
                    continue

                backoff = 0
                write_output(trains, "OK")

                sleep_for = random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS)
                time.sleep(sleep_for)

                # Light refresh occasionally to keep map fresh
                driver.execute_script("try { if(window.map){ window.map.renderSync(); } } catch(e) {}")

            except Exception as e:
                backoff = min(MAX_BACKOFF_SECONDS, (backoff * 2) if backoff else 120)
                write_output([], f"Error: {type(e).__name__}. Backoff {backoff}s")
                time.sleep(backoff)
                try:
                    driver.refresh()
                    time.sleep(10)
                    close_warning(driver)
                except:
                    pass

        write_output([], "Stopping gracefully")

    finally:
        try:
            if driver:
                driver.quit()
        except:
            pass

if __name__ == "__main__":
    main()
