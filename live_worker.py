import os, json, time, math, pickle, random, datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


TF_LOGIN_URL = os.environ.get("TF_LOGIN_URL", "https://trainfinder.otenko.com/home/nextlevel")
OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "trainfinder_cookies.pkl")

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

BASE_MIN_SECONDS = int(os.environ.get("BASE_MIN_SECONDS", "30"))
BASE_MAX_SECONDS = int(os.environ.get("BASE_MAX_SECONDS", "60"))
MIN_TRAINS_OK = int(os.environ.get("MIN_TRAINS_OK", "20"))
MAX_BACKOFF_SECONDS = int(os.environ.get("MAX_BACKOFF_SECONDS", "900"))
LOCK_PATH = Path(os.environ.get("LOCK_PATH", "/tmp/railops_live.lock"))

CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")


def utc_now_z():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def write_output(trains, note=""):
    payload = {"lastUpdated": utc_now_z(), "note": note, "trains": trains or []}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"📝 {OUT_FILE}: {len(trains or [])} trains | {note}")


def webmercator_to_latlon(x, y):
    try:
        x = float(x); y = float(y)
        lon = (x / 20037508.34) * 180.0
        lat = (y / 20037508.34) * 180.0
        lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


def acquire_lock():
    if LOCK_PATH.exists():
        raise RuntimeError(f"Lock exists at {LOCK_PATH} (worker already running?)")
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")


def release_lock():
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
    except Exception:
        pass


def make_driver():
    opts = Options()
    opts.binary_location = CHROME_BIN
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-AU")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    service = webdriver.ChromeService(executable_path=CHROMEDRIVER_BIN)
    d = webdriver.Chrome(service=service, options=opts)
    d.set_page_load_timeout(60)
    return d


def try_close_warning_popup(driver):
    # tries to click the X on TrainFinder warning overlay
    try:
        driver.execute_script("""
          var paths = document.getElementsByTagName('path');
          for (var i = 0; i < paths.length; i++) {
            var d = paths[i].getAttribute('d') || '';
            if (d.includes('M13.7,11l6.1-6.1')) {
              var parent = paths[i].parentElement;
              while (parent && !['BUTTON','DIV','A'].includes(parent.tagName)) parent = parent.parentElement;
              if (parent) parent.click();
              break;
            }
          }
        """)
    except Exception:
        pass


def save_cookies(driver):
    try:
        pickle.dump(driver.get_cookies(), open(COOKIE_FILE, "wb"))
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
    driver.get(TF_LOGIN_URL)
    time.sleep(3)

    if load_cookies(driver):
        driver.refresh()
        time.sleep(3)
        try_close_warning_popup(driver)
        time.sleep(1)

    page = (driver.page_source or "").lower()

    # login form present?
    if "user_name" in page or "pass_word" in page or "user_name" in (driver.page_source or ""):
        if not TF_USERNAME or not TF_PASSWORD:
            raise RuntimeError("Need TF_USERNAME/TF_PASSWORD for first login (or provide valid cookies).")

        print("🔐 Logging in…")
        u = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "useR_name")))
        u.clear(); u.send_keys(TF_USERNAME)
        p = driver.find_element(By.ID, "pasS_word")
        p.clear(); p.send_keys(TF_PASSWORD)
        driver.execute_script("document.querySelector('div.button-green')?.click()")
        time.sleep(6)
        try_close_warning_popup(driver)
        time.sleep(2)
        save_cookies(driver)
    else:
        print("✅ Session appears logged-in (no login form detected).")


# Robust extractor: tries known globals, then falls back to scanning OL map layers
EXTRACT_SCRIPT = r"""
(function() {

  function collectFromSource(src) {
    if (!src || !src.getFeatures) return [];
    var feats = src.getFeatures() || [];
    var out = [];
    for (var i = 0; i < feats.length; i++) {
      try {
        var f = feats[i];
        var props = f.getProperties ? f.getProperties() : {};
        var geom = f.getGeometry ? f.getGeometry() : null;
        if (!geom || !geom.getCoordinates) continue;
        var coords = geom.getCoordinates();
        if (!coords || coords.length < 2) continue;
        out.push({ props: props, x: coords[0], y: coords[1] });
      } catch(e) {}
    }
    return out;
  }

  var rows = [];

  var globals = ['regTrainsSource','unregTrainsSource','markerSource','arrowMarkersSource','trainSource','trainMarkers'];
  for (var g = 0; g < globals.length; g++) {
    try { rows = rows.concat(collectFromSource(window[globals[g]])); } catch(e) {}
  }

  if (rows.length === 0) {
    try {
      var maps = [];
      if (window.map && window.map.getLayers) maps.push(window.map);
      if (window.tfMap && window.tfMap.getLayers) maps.push(window.tfMap);

      for (var k in window) {
        try {
          var v = window[k];
          if (v && v.getLayers && v.getView && typeof v.getLayers === 'function') maps.push(v);
        } catch(e) {}
      }

      var seen = new Set();
      maps.forEach(function(m) {
        try {
          var layers = m.getLayers().getArray();
          layers.forEach(function(layer) {
            try {
              var src = layer.getSource ? layer.getSource() : null;
              if (!src || !src.getFeatures) return;
              collectFromSource(src).forEach(function(r) {
                var id = (r.props && (r.props.id || r.props.ID)) || '';
                var key = String(id) + '|' + String(r.x) + '|' + String(r.y);
                if (seen.has(key)) return;
                seen.add(key);
                rows.push(r);
              });
            } catch(e) {}
          });
        } catch(e) {}
      });
    } catch(e) {}
  }

  return rows.map(function(r, idx) {
    var p = r.props || {};
    return {
      id: p.id || p.ID || ('feat_' + idx),
      train_number: p.trainNumber || p.train_number || '',
      train_name: p.trainName || p.train_name || '',
      loco: p.loco || p.trKey || '',
      operator: p.operator || '',
      origin: p.serviceFrom || p.origin || '',
      destination: p.serviceTo || p.destination || '',
      heading: p.heading || 0,
      km: p.trainKM || '',
      time: p.trainTime || '',
      date: p.trainDate || '',
      speed_raw: p.trainSpeed || '',
      x: r.x,
      y: r.y
    };
  });

})();
"""


def normalize_trains(raw):
    import re
    trains = []
    for t in raw or []:
        lat, lon = webmercator_to_latlon(t.get("x"), t.get("y"))
        if not lat or not lon:
            continue
        if not (-45 <= lat <= -9 and 110 <= lon <= 155):
            continue

        speed = 0
        m = re.search(r"(\d+)", str(t.get("speed_raw", "") or ""))
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
    # wait up to 20 seconds for features
    for _ in range(20):
        raw = driver.execute_script(EXTRACT_SCRIPT) or []
        if len(raw) >= 5:
            return normalize_trains(raw)
        time.sleep(1)
    raw = driver.execute_script(EXTRACT_SCRIPT) or []
    return normalize_trains(raw)


def main():
    acquire_lock()
    backoff = 0
    driver = None

    try:
        driver = make_driver()
        login_if_needed(driver)

        print("🚦 Live worker started (single session, jitter + backoff)")
        while True:
            try:
                trains = extract_trains(driver)

                if len(trains) < MIN_TRAINS_OK:
                    backoff = min(MAX_BACKOFF_SECONDS, max(60, (backoff * 2) if backoff else 120))
                    write_output(trains, f"Low train count ({len(trains)}). Backoff {backoff}s")
                    time.sleep(backoff)
                    driver.refresh()
                    time.sleep(4)
                    try_close_warning_popup(driver)
                    continue

                backoff = 0
                write_output(trains, "OK")
                time.sleep(random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS))

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
