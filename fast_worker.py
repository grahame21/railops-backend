import os
import json
import time
import math
import pickle
import random
import datetime
import signal

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

OUT_FILE = "trains.json"
LAST_GOOD_FILE = "trains_last_good.json"
COOKIE_FILE = "trainfinder_cookies.pkl"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

# Jitter timing
BASE_MIN_SECONDS = int(os.environ.get("BASE_MIN_SECONDS", "30"))
BASE_MAX_SECONDS = int(os.environ.get("BASE_MAX_SECONDS", "60"))

# Backoff
MIN_TRAINS_OK = int(os.environ.get("MIN_TRAINS_OK", "500"))  # IMPORTANT: real runs are ~1400-1700
MAX_BACKOFF_SECONDS = int(os.environ.get("MAX_BACKOFF_SECONDS", "900"))

# Chromium paths inside the container
CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")

STOP = False


def handle_stop(sig, frame):
    global STOP
    STOP = True


signal.signal(signal.SIGINT, handle_stop)
signal.signal(signal.SIGTERM, handle_stop)

print("=" * 60)
print("🚂 RAILOPS - FAST WORKER (filtered sources + keep last good)")
print("=" * 60)


def utc_now_z():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_last_good_trains():
    try:
        if os.path.exists(LAST_GOOD_FILE):
            with open(LAST_GOOD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            trains = data.get("trains") or []
            if isinstance(trains, list) and len(trains) > 0:
                return trains
    except:
        pass
    return []


def write_output(trains, note=""):
    payload = {
        "lastUpdated": utc_now_z(),
        "note": note,
        "trains": trains or []
    }
    write_json(OUT_FILE, payload)
    print(f"📝 Output: {len(trains or [])} trains | {note}")


def save_last_good(trains):
    payload = {
        "lastUpdated": utc_now_z(),
        "note": "last_good",
        "trains": trains or []
    }
    try:
        write_json(LAST_GOOD_FILE, payload)
    except:
        pass


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

    # Running under Xvfb (not headless)
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
    driver.set_page_load_timeout(75)

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
    if ("user_name" in page) or ("pass_word" in page) or ("user_name" in page) or ("user_name" in page):
        if not TF_USERNAME or not TF_PASSWORD:
            raise RuntimeError("Missing TF_USERNAME / TF_PASSWORD")

        print("🔐 Logging in…")
        username = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        username.clear()
        username.send_keys(TF_USERNAME)

        password = driver.find_element(By.ID, "pasS_word")
        password.clear()
        password.send_keys(TF_PASSWORD)

        driver.execute_script("""
            var buttons = document.querySelectorAll('input[type="button"], button, div.button-green');
            for (var i=0;i<buttons.length;i++){
              var t = (buttons[i].value || buttons[i].textContent || '').toLowerCase();
              if (t.includes('log in') || (buttons[i].className||'').includes('button-green')) {
                buttons[i].click(); break;
              }
            }
        """)
        time.sleep(7)

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
    print("⏳ Warmup: waiting 20s for map…")
    time.sleep(20)

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
    time.sleep(8)

    print("⏳ Warmup: waiting 35s for trains…")
    time.sleep(35)


# IMPORTANT CHANGE:
# - We still look at markerSource, BUT we FILTER hard:
#   ignore any markerSource point that doesn't actually have train-ish fields.
EXTRACT_SCRIPT = r"""
var out = [];

function hasTrainSignals(p){
  // TrainFinder objects usually have at least SOME of these
  return !!(
    p.trKey ||
    p.trainNumber || p.train_number ||
    p.trainName || p.train_name ||
    p.trainSpeed ||
    p.serviceFrom || p.serviceTo ||
    p.serviceDesc ||
    p.cId || p.servId
  );
}

var sources = [
  'regTrainsSource',
  'unregTrainsSource',
  'trainSource',
  'trainMarkers',
  'arrowMarkersSource',
  'markerSource'
];

sources.forEach(function(sourceName){
  var source = window[sourceName];
  if (!source || !source.getFeatures) return;

  var features = source.getFeatures();
  features.forEach(function(feature, idx){
    try{
      var props = feature.getProperties();
      var geom = feature.getGeometry();
      if (!geom || geom.getType() !== 'Point') return;

      // FILTER: markerSource is full of random map markers; only keep ones that "smell like" trains
      if (sourceName === 'markerSource' && !hasTrainSignals(props)) return;

      var coords = geom.getCoordinates();

      var speedNum = 0;
      if (props.trainSpeed) {
        var m = String(props.trainSpeed).match(/(\d+)/);
        if (m) speedNum = parseInt(m[0]);
      }

      out.push({
        id: props.id || props.ID || (sourceName + '_' + idx),
        train_number: props.trainNumber || props.train_number || '',
        train_name: props.trainName || props.train_name || '',
        loco: props.loco || '',
        operator: props.operator || '',
        origin: props.serviceFrom || props.origin || '',
        destination: props.serviceTo || props.destination || '',
        speed: speedNum,
        heading: props.heading || 0,
        km: props.trainKM || '',
        time: props.trainTime || '',
        date: props.trainDate || '',
        description: props.serviceDesc || '',
        cId: props.cId || '',
        servId: props.servId || '',
        trKey: props.trKey || '',
        x: coords[0],
        y: coords[1]
      });
    } catch(e){}
  });
});

return out;
"""


def extract_trains(driver):
    # Try multiple times (layers sometimes update)
    last = []
    for _ in range(10):
        raw = driver.execute_script(EXTRACT_SCRIPT) or []
        last = raw
        if len(raw) >= 300:  # realistically should be >1000 when good, but allow a bit
            return raw
        time.sleep(2)
    return last


def normalize(raw_trains):
    trains = []
    for t in raw_trains or []:
        lat, lon = webmercator_to_latlon(t.get("x"), t.get("y"))
        if not (lat and lon):
            continue
        # Australia bounds
        if not (-45 <= lat <= -9 and 110 <= lon <= 155):
            continue

        tr = {
            "id": t.get("id", "unknown"),
            "train_number": t.get("train_number", ""),
            "train_name": t.get("train_name", ""),
            "loco": t.get("loco", ""),
            "operator": t.get("operator", ""),
            "origin": t.get("origin", ""),
            "destination": t.get("destination", ""),
            "speed": t.get("speed", 0),
            "heading": t.get("heading", 0),
            "km": t.get("km", ""),
            "time": t.get("time", ""),
            "date": t.get("date", ""),
            "description": t.get("description", ""),
            "cId": t.get("cId", ""),
            "servId": t.get("servId", ""),
            "trKey": t.get("trKey", ""),
            "lat": lat,
            "lon": lon
        }

        # FINAL FILTER: if it still looks like junk, drop it
        looks_like_markersource = str(tr.get("id", "")).startswith("markerSource_")
        has_any_id = bool(tr.get("train_number") or tr.get("trKey") or tr.get("train_name"))
        has_any_route = bool(tr.get("origin") or tr.get("destination") or tr.get("description"))
        if looks_like_markersource and not (has_any_id or has_any_route):
            continue

        trains.append(tr)

    return trains


def main():
    if not TF_USERNAME or not TF_PASSWORD:
        raise RuntimeError("Missing TF_USERNAME/TF_PASSWORD Fly secrets")

    backoff = 0
    driver = None
    consecutive_errors = 0
    last_good = load_last_good_trains()

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

                    # IMPORTANT: do NOT wipe trains.json to empty. Serve last good instead.
                    keep = last_good if last_good else trains
                    write_output(keep, f"Low train count ({len(trains)}). Serving last-good. Backoff {backoff}s")

                    time.sleep(backoff)
                    try:
                        driver.refresh()
                        time.sleep(10)
                        close_warning(driver)
                    except:
                        pass
                    continue

                # OK run
                last_good = trains
                save_last_good(trains)
                write_output(trains, "OK")

                backoff = 0
                consecutive_errors = 0

                time.sleep(random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS))
                try:
                    driver.execute_script("try { if(window.map){ window.map.renderSync(); } } catch(e) {}")
                except:
                    pass

            except TimeoutException:
                consecutive_errors += 1
                backoff = min(MAX_BACKOFF_SECONDS, (backoff * 2) if backoff else 120)

                keep = last_good if last_good else []
                write_output(keep, f"Error TimeoutException. Serving last-good. Backoff {backoff}s")

                time.sleep(backoff)
                try:
                    driver.refresh()
                    time.sleep(10)
                    close_warning(driver)
                except:
                    pass

            except WebDriverException as e:
                consecutive_errors += 1
                backoff = min(MAX_BACKOFF_SECONDS, (backoff * 2) if backoff else 120)

                keep = last_good if last_good else []
                write_output(keep, f"Error WebDriverException. Serving last-good. Backoff {backoff}s")

                time.sleep(backoff)

            except Exception as e:
                consecutive_errors += 1
                backoff = min(MAX_BACKOFF_SECONDS, (backoff * 2) if backoff else 120)

                keep = last_good if last_good else []
                write_output(keep, f"Error {type(e).__name__}. Serving last-good. Backoff {backoff}s")

                time.sleep(backoff)

            # If it keeps erroring, rebuild the driver cleanly
            if consecutive_errors >= 3:
                print("🔁 Too many consecutive errors — rebuilding browser session…")
                consecutive_errors = 0
                try:
                    if driver:
                        driver.quit()
                except:
                    pass
                driver = make_driver()
                ensure_logged_in(driver)
                warmup_map(driver)

        write_output(last_good if last_good else [], "Stopping gracefully")

    finally:
        try:
            if driver:
                driver.quit()
        except:
            pass


if __name__ == "__main__":
    main()
