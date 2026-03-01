import os
import json
import time
import math
import pickle
import random
import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ----------------------------
# Config
# ----------------------------
TF_LOGIN_URL = os.environ.get("TF_LOGIN_URL", "https://trainfinder.otenko.com/home/nextlevel")

OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "trainfinder_cookies.pkl")

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

# Jitter range (seconds)
BASE_MIN_SECONDS = int(os.environ.get("BASE_MIN_SECONDS", "30"))
BASE_MAX_SECONDS = int(os.environ.get("BASE_MAX_SECONDS", "60"))

# If train count drops below this, we treat it as "something is wrong"
MIN_TRAINS_OK = int(os.environ.get("MIN_TRAINS_OK", "20"))

# Backoff caps (seconds)
MAX_BACKOFF_SECONDS = int(os.environ.get("MAX_BACKOFF_SECONDS", "900"))  # 15 minutes max

# Lock to prevent two workers running
LOCK_PATH = Path(os.environ.get("LOCK_PATH", "/tmp/railops_live.lock"))

# Chromium binary paths (Debian)
CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")


# ----------------------------
# Helpers
# ----------------------------
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
    print(f"📝 {OUT_FILE}: {len(trains or [])} trains | {note}")


def webmercator_to_latlon(x, y):
    """Convert EPSG:3857 to lat/lon."""
    try:
        x = float(x)
        y = float(y)
        lon = (x / 20037508.34) * 180.0
        lat = (y / 20037508.34) * 180.0
        lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


def acquire_lock():
    if LOCK_PATH.exists():
        raise RuntimeError(f"Lock exists at {LOCK_PATH}. Another worker may be running.")
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")


def release_lock():
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
    except Exception:
        pass


def make_driver():
    options = Options()
    options.binary_location = CHROME_BIN

    # Headless Chrome for server
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # Make it look a bit more "normal"
    options.add_argument("--lang=en-AU")
    options.add_argument("--disable-blink-features=AutomationControlled")

    service = webdriver.ChromeService(executable_path=CHROMEDRIVER_BIN)
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver


def try_close_warning_popup(driver):
    """
    TrainFinder sometimes shows a warning overlay.
    We try to click the X close icon (SVG path heuristic).
    """
    try:
        driver.execute_script("""
          var paths = document.getElementsByTagName('path');
          for (var i = 0; i < paths.length; i++) {
            var d = paths[i].getAttribute('d') || '';
            if (d.includes('M13.7,11l6.1-6.1')) {
              var parent = paths[i].parentElement;
              while (parent && !['BUTTON','DIV','A'].includes(parent.tagName)) {
                parent = parent.parentElement;
              }
              if (parent) { parent.click(); }
              break;
            }
          }
        """)
    except Exception:
        pass


def save_cookies(driver):
    try:
        cookies = driver.get_cookies()
        pickle.dump(cookies, open(COOKIE_FILE, "wb"))
        print("✅ Saved cookies:", COOKIE_FILE)
    except Exception as e:
        print("⚠️ Could not save cookies:", e)


def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE):
        return False
    try:
        cookies = pickle.load(open(COOKIE_FILE, "rb"))
        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        print("✅ Loaded cookies:", COOKIE_FILE)
        return True
    except Exception as e:
        print("⚠️ Cookie load failed:", e)
        return False


def login_if_needed(driver):
    """
    Goal: keep ONE long-lived session. Only login if we must.
    """
    driver.get(TF_LOGIN_URL)
    time.sleep(3)

    # Attempt cookie restore
    restored = load_cookies(driver)
    if restored:
        driver.refresh()
        time.sleep(3)
        try_close_warning_popup(driver)
        time.sleep(1)

    page = (driver.page_source or "").lower()

    # If login inputs still visible, do a one-time login
    if "user_name" in page or "pass_word" in page or "user_name" in driver.page_source:
        if not TF_USERNAME or not TF_PASSWORD:
            raise RuntimeError("Need TF_USERNAME/TF_PASSWORD (or a valid cookie file) to login.")

        print("🔐 Logging in…")
        u = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "useR_name")))
        u.clear()
        u.send_keys(TF_USERNAME)

        p = driver.find_element(By.ID, "pasS_word")
        p.clear()
        p.send_keys(TF_PASSWORD)

        # TrainFinder uses a clickable div button
        driver.execute_script("document.querySelector('div.button-green')?.click()")
        time.sleep(6)

        try_close_warning_popup(driver)
        time.sleep(2)

        save_cookies(driver)
        return

    print("✅ Session appears logged-in (no login form detected).")


# JavaScript that extracts OpenLayers feature data
EXTRACT_SCRIPT = r"""
(function() {
  var allTrains = [];
  var sources = [
    'regTrainsSource', 'unregTrainsSource', 'markerSource',
    'arrowMarkersSource', 'trainSource', 'trainMarkers'
  ];

  sources.forEach(function(sourceName) {
    var source = window[sourceName];
    if (!source || !source.getFeatures) return;

    var features = source.getFeatures();
    features.forEach(function(feature, idx) {
      try {
        var props = feature.getProperties ? feature.getProperties() : {};
        var geom = feature.getGeometry ? feature.getGeometry() : null;
        if (!geom || !geom.getType || geom.getType() !== 'Point') return;

        var coords = geom.getCoordinates ? geom.getCoordinates() : null;
        if (!coords || coords.length < 2) return;

        var trainData = {
          id: props.id || props.ID || (sourceName + '_' + idx),
          train_number: props.trainNumber || props.train_number || '',
          train_name: props.trainName || props.train_name || '',
          service_name: props.serviceName || '',
          loco: props.loco || '',
          operator: props.operator || '',
          origin: props.serviceFrom || props.origin || '',
          destination: props.serviceTo || props.destination || '',
          heading: props.heading || 0,
          km: props.trainKM || '',
          time: props.trainTime || '',
          date: props.trainDate || '',
          speed_raw: props.trainSpeed || '',
          x: coords[0],
          y: coords[1]
        };

        allTrains.push(trainData);
      } catch(e) {}
    });
  });

  return allTrains;
})();
"""


def normalize_trains(raw_trains):
    trains = []
    for t in raw_trains or []:
        lat, lon = webmercator_to_latlon(t.get("x"), t.get("y"))

        # Australia-ish bounds sanity check
        if not lat or not lon:
            continue
        if not (-45 <= lat <= -9 and 110 <= lon <= 155):
            continue

        # Parse speed if present
        speed = 0
        sr = str(t.get("speed_raw", "") or "")
        m = None
        try:
            import re
            m = re.search(r"(\d+)", sr)
        except Exception:
            m = None
        if m:
            try:
                speed = int(m.group(1))
            except Exception:
                speed = 0

        trains.append({
            "id": t.get("id", "unknown"),
            "train_number": t.get("train_number", ""),
            "train_name": t.get("train_name", ""),
            "loco": t.get("loco", ""),
            "operator": t.get("operator", ""),
            "origin": t.get("origin", ""),
            "destination": t.get("destination", ""),
            "speed": speed,
            "heading": t.get("heading", 0),
            "km": t.get("km", ""),
            "time": t.get("time", ""),
            "date": t.get("date", ""),
            "lat": lat,
            "lon": lon
        })

    return trains


def extract_trains(driver):
    raw = driver.execute_script(EXTRACT_SCRIPT)
    return normalize_trains(raw)


# ----------------------------
# Main loop with jitter + backoff
# ----------------------------
def main():
    acquire_lock()
    driver = None

    # backoff starts at 0; grows on trouble, resets on success
    backoff = 0

    try:
        driver = make_driver()
        login_if_needed(driver)

        print("🚦 Live worker started (single session, jitter + backoff)")

        while True:
            try:
                trains = extract_trains(driver)

                if len(trains) < MIN_TRAINS_OK:
                    # Something is likely wrong: warning, not loaded, etc.
                    backoff = min(MAX_BACKOFF_SECONDS, max(60, (backoff * 2) if backoff else 120))
                    write_output(trains, f"Low train count ({len(trains)}). Backoff {backoff}s")

                    time.sleep(backoff)
                    driver.refresh()
                    time.sleep(4)
                    try_close_warning_popup(driver)
                    continue

                # success: reset backoff
                backoff = 0
                write_output(trains, "OK")

                # jittered wait
                sleep_for = random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS)
                time.sleep(sleep_for)

            except Exception as e:
                backoff = min(MAX_BACKOFF_SECONDS, max(60, (backoff * 2) if backoff else 120))
                write_output([], f"Error: {e}. Backoff {backoff}s")
                time.sleep(backoff)
                try:
                    driver.refresh()
                    time.sleep(4)
                    try_close_warning_popup(driver)
                except Exception:
                    pass

    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        release_lock()


if __name__ == "__main__":
    main()
