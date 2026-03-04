import os
import json
import time
import math
import pickle
import random
import datetime
import signal

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By


OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "trainfinder_cookies.pkl")
TF_LOGIN_URL = os.environ.get("TF_LOGIN_URL", "https://trainfinder.otenko.com/home/nextlevel")

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

BASE_MIN_SECONDS = int(os.environ.get("BASE_MIN_SECONDS", "15"))
BASE_MAX_SECONDS = int(os.environ.get("BASE_MAX_SECONDS", "30"))

# Tolerant so we don't get stuck in LOW forever if TrainFinder feature counts vary
MIN_TRAINS_OK = int(os.environ.get("MIN_TRAINS_OK", "50"))

MAX_BACKOFF_SECONDS = int(os.environ.get("MAX_BACKOFF_SECONDS", "120"))
INITIAL_BACKOFF_SECONDS = int(os.environ.get("INITIAL_BACKOFF_SECONDS", "15"))
BACKOFF_MULTIPLIER = float(os.environ.get("BACKOFF_MULTIPLIER", "1.6"))

PUSH_URL = os.environ.get("PUSH_URL", "https://railops-live-au.fly.dev/push")
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "").strip()

PUBLIC_TRAINS_JSON_URL = os.environ.get("PUBLIC_TRAINS_JSON_URL", "https://railops-live-au.fly.dev/trains.json")

CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")

STOP = False


def handle_stop(sig, frame):
    global STOP
    STOP = True


signal.signal(signal.SIGINT, handle_stop)
signal.signal(signal.SIGTERM, handle_stop)


def utc_now_z():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def build_payload(trains, note):
    return {"lastUpdated": utc_now_z(), "note": note, "trains": trains or []}


def write_local(payload):
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def push_to_web(payload):
    if not PUSH_URL or not PUSH_TOKEN:
        print("⚠️ PUSH_URL / PUSH_TOKEN not set (skipping push)")
        return False
    try:
        r = requests.post(
            PUSH_URL,
            json=payload,
            headers={"X-Auth-Token": PUSH_TOKEN},
            timeout=20,
        )
        if 200 <= r.status_code < 300:
            return True
        print(f"⚠️ Push failed: HTTP {r.status_code} {r.text[:200]}")
        return False
    except Exception:
        print("⚠️ Push exception")
        return False


def webmercator_to_latlon(x, y):
    """
    TrainFinder features appear to be WebMercator meters most of the time.
    We also support lon/lat degrees if they ever appear.
    """
    try:
        x = float(x)
        y = float(y)

        # WebMercator meters heuristic
        if abs(x) > 1000 and abs(y) > 1000:
            lon = (x / 20037508.34) * 180.0
            lat = (y / 20037508.34) * 180.0
            lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
            return round(lat, 6), round(lon, 6)

        # Already lon/lat degrees fallback
        if -180 <= x <= 180 and -90 <= y <= 90:
            return round(y, 6), round(x, 6)

        return None, None
    except Exception:
        return None, None


def load_seed_trains():
    try:
        if os.path.exists(OUT_FILE):
            with open(OUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            trains = data.get("trains") or []
            if isinstance(trains, list) and trains:
                print(f"✅ Seeded last-good trains from local {OUT_FILE}: {len(trains)} trains")
                return trains
    except Exception:
        pass

    try:
        r = requests.get(PUBLIC_TRAINS_JSON_URL, timeout=10, headers={"Cache-Control": "no-cache"})
        if r.ok:
            data = r.json()
            trains = data.get("trains") or []
            if isinstance(trains, list) and trains:
                print(f"✅ Seeded last-good trains from {PUBLIC_TRAINS_JSON_URL}: {len(trains)} trains")
                return trains
    except Exception:
        pass

    print("ℹ️ No seed trains available yet")
    return []


def make_driver():
    chrome_options = Options()
    chrome_options.binary_location = CHROME_BIN

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=en-AU")

    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    service = webdriver.ChromeService(executable_path=CHROMEDRIVER_BIN)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.set_page_load_timeout(180)
    driver.set_script_timeout(80)

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
    except Exception:
        pass

    return driver


def safe_get(driver, url):
    try:
        driver.get(url)
        return True
    except TimeoutException:
        print("⚠️ Page load timeout on GET — stopping load and continuing")
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        return False


def safe_refresh(driver):
    try:
        driver.refresh()
        return True
    except TimeoutException:
        print("⚠️ Page load timeout on REFRESH — stopping load and continuing")
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        return False


def close_warning(driver):
    try:
        driver.execute_script(
            """
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
            """
        )
        print("✅ Warning close attempted")
    except Exception:
        pass


def element_visible(el):
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def find_username_field(driver):
    candidates = []
    try:
        candidates += driver.find_elements(By.CSS_SELECTOR, "input[type='email']")
        candidates += driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
    except Exception:
        pass

    scored = []
    for el in candidates:
        try:
            if not element_visible(el):
                continue
            attrs = {
                "id": (el.get_attribute("id") or "").lower(),
                "name": (el.get_attribute("name") or "").lower(),
                "placeholder": (el.get_attribute("placeholder") or "").lower(),
                "aria": (el.get_attribute("aria-label") or "").lower(),
            }
            blob = " ".join(attrs.values())
            score = 0
            if "email" in blob:
                score += 5
            if "user" in blob or "username" in blob:
                score += 4
            if "login" in blob:
                score += 2
            if score > 0:
                scored.append((score, el))
        except Exception:
            continue

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    for el in candidates:
        if element_visible(el):
            return el

    return None


def find_password_field(driver):
    try:
        els = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        for el in els:
            if element_visible(el):
                return el
    except Exception:
        pass
    return None


def click_login_button(driver):
    selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button",
        "input[type='button']",
        "div.button-green",
        "div[class*='button']",
    ]
    for sel in selectors:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for b in btns:
                if not element_visible(b):
                    continue
                txt = (b.get_attribute("value") or b.text or "").strip().lower()
                if any(k in txt for k in ["log in", "login", "sign in", "submit", "continue"]):
                    try:
                        b.click()
                        return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False


def ensure_logged_in(driver):
    safe_get(driver, TF_LOGIN_URL)
    time.sleep(6)

    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "rb") as f:
                cookies = pickle.load(f)
            for c in cookies:
                try:
                    driver.add_cookie(c)
                except Exception:
                    pass
            safe_get(driver, TF_LOGIN_URL)
            time.sleep(5)
            print("✅ Loaded saved cookies")
        except Exception:
            pass

    page_lower = (driver.page_source or "").lower()
    password_inputs = []
    try:
        password_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    except Exception:
        pass

    login_needed = ("password" in page_lower and ("log in" in page_lower or "login" in page_lower)) or any(
        element_visible(p) for p in password_inputs
    )

    if not login_needed:
        print("✅ Session appears logged-in (no login form detected).")
        close_warning(driver)
        return

    if not TF_USERNAME or not TF_PASSWORD:
        raise RuntimeError("Missing TF_USERNAME / TF_PASSWORD")

    print("🔐 Login form detected — attempting login…")

    user_el = find_username_field(driver)
    pass_el = find_password_field(driver)

    if user_el is None or pass_el is None:
        snippet = (driver.page_source or "")[:2000].replace("\n", " ")
        print("❌ Login fields not found. HTML snippet:", snippet)
        raise RuntimeError("Could not find login fields")

    try:
        user_el.clear()
    except Exception:
        pass
    user_el.send_keys(TF_USERNAME)

    try:
        pass_el.clear()
    except Exception:
        pass
    pass_el.send_keys(TF_PASSWORD)

    clicked = click_login_button(driver)
    if not clicked:
        try:
            pass_el.send_keys("\n")
        except Exception:
            pass

    time.sleep(10)

    try:
        with open(COOKIE_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("✅ Cookies saved")
    except Exception:
        pass

    close_warning(driver)


def warmup_map(driver):
    print("⏳ Warmup: waiting 25s for map…")
    time.sleep(25)

    print("🌏 Zooming to Australia…")
    try:
        driver.execute_script(
            """
            try {
              if (window.map && window.ol && ol.proj && window.map.getView) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 0, maxZoom: 8 });
              }
            } catch(e) {}
            """
        )
    except Exception:
        pass

    time.sleep(10)

    print("⏳ Warmup: waiting 60s for trains…")
    time.sleep(60)


# ✅ NEW: Wait for ANY vector features in the map layers (not window globals)
WAIT_FOR_MAP_FEATURES_JS = r"""
try {
  if (!window.map || !map.getLayers) return {ok:false, reason:"no map"};
  var layers = map.getLayers().getArray();
  var best = {name:null, count:0};

  for (var i=0;i<layers.length;i++){
    try{
      var layer = layers[i];
      if (!layer || !layer.getSource) continue;
      var src = layer.getSource();
      if (!src) continue;

      // Vector sources usually have getFeatures()
      if (typeof src.getFeatures === 'function'){
        var n = src.getFeatures().length;
        if (n > best.count){
          best.count = n;
          best.name = (layer.get('title') || layer.get('name') || layer.constructor && layer.constructor.name) || ("layer_"+i);
        }
      }

      // Some layers use source.getSource() (e.g., cluster)
      if (typeof src.getSource === 'function'){
        var inner = src.getSource();
        if (inner && typeof inner.getFeatures === 'function'){
          var n2 = inner.getFeatures().length;
          if (n2 > best.count){
            best.count = n2;
            best.name = (layer.get('title') || layer.get('name') || layer.constructor && layer.constructor.name) || ("layer_"+i);
          }
        }
      }
    }catch(e){}
  }

  if (best.count > 0) return {ok:true, name:best.name, count:best.count};
  return {ok:false, reason:"no vector features yet"};
} catch(e) { return {ok:false, err:String(e)}; }
"""


# ✅ NEW: Extract point features from ALL map vector layers
EXTRACT_FROM_MAP_LAYERS_JS = r"""
try {
  if (!window.map || !map.getLayers) return [];
  var out = [];
  var layers = map.getLayers().getArray();

  function addFeature(sourceName, feature, idx){
    try{
      var props = (feature.getProperties && feature.getProperties()) ? feature.getProperties() : (feature.values_ || {});
      var geom = (feature.getGeometry && feature.getGeometry()) ? feature.getGeometry() : null;
      if (!geom || !geom.getType || geom.getType() !== 'Point') return;

      var coords = geom.getCoordinates ? geom.getCoordinates() : null;
      if (!coords || coords.length < 2) return;

      // TrainFinder-like properties
      var t = {
        id: props.id || props.ID || (sourceName + "_" + idx),
        train_number: props.trainNumber || props.train_number || props.trainNo || "",
        train_name: props.trainName || props.train_name || "",
        service_name: props.serviceName || "",
        loco: props.loco || "",
        operator: props.operator || "",
        origin: props.serviceFrom || props.origin || "",
        destination: props.serviceTo || props.destination || "",
        speed: 0,
        heading: props.heading || 0,
        km: props.trainKM || "",
        time: props.trainTime || "",
        date: props.trainDate || "",
        description: props.serviceDesc || props.description || "",
        cId: props.cId || "",
        servId: props.servId || "",
        trKey: props.trKey || "",
        x: coords[0],
        y: coords[1]
      };

      if (props.trainSpeed) {
        var m = String(props.trainSpeed).match(/(\d+)/);
        if (m) t.speed = parseInt(m[0]);
      }

      out.push(t);
    }catch(e){}
  }

  for (var i=0;i<layers.length;i++){
    try{
      var layer = layers[i];
      if (!layer || !layer.getSource) continue;
      var src = layer.getSource();
      if (!src) continue;

      var srcName = (layer.get('title') || layer.get('name') || layer.constructor && layer.constructor.name) || ("layer_"+i);

      if (typeof src.getFeatures === 'function'){
        var feats = src.getFeatures();
        for (var j=0;j<feats.length;j++){
          addFeature(srcName, feats[j], j);
        }
      }

      if (typeof src.getSource === 'function'){
        var inner = src.getSource();
        if (inner && typeof inner.getFeatures === 'function'){
          var feats2 = inner.getFeatures();
          for (var k=0;k<feats2.length;k++){
            addFeature(srcName+"_inner", feats2[k], k);
          }
        }
      }
    }catch(e){}
  }

  return out;
} catch(e) {
  return [];
}
"""


def wait_for_map_features(driver, timeout_s=120):
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            res = driver.execute_script(WAIT_FOR_MAP_FEATURES_JS)
            if isinstance(res, dict) and res.get("ok"):
                print(f"✅ Map layer features found: {res.get('name')} ({res.get('count')} features)")
                return True
        except Exception:
            pass
        time.sleep(2)

    print("⚠️ No map-layer vector features found within timeout")
    return False


def extract_trains(driver):
    if not wait_for_map_features(driver, timeout_s=120):
        return []

    for _ in range(6):
        try:
            raw = driver.execute_script(EXTRACT_FROM_MAP_LAYERS_JS) or []
            if len(raw) >= 50:
                return raw
        except TimeoutException:
            print("⚠️ Script timeout during extract — retrying")
        except WebDriverException:
            pass
        time.sleep(2)

    try:
        return driver.execute_script(EXTRACT_FROM_MAP_LAYERS_JS) or []
    except Exception:
        return []


def normalize(raw_trains):
    trains = []
    for t in raw_trains or []:
        lat, lon = webmercator_to_latlon(t.get("x"), t.get("y"))
        if lat is None or lon is None:
            continue
        if -45 <= lat <= -9 and 110 <= lon <= 155:
            trains.append(
                {
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
                    "lon": lon,
                }
            )
    return trains


def next_backoff(current):
    if current <= 0:
        return min(MAX_BACKOFF_SECONDS, max(1, INITIAL_BACKOFF_SECONDS))
    grown = int(max(current + 1, current * BACKOFF_MULTIPLIER))
    return min(MAX_BACKOFF_SECONDS, max(1, grown))


def main():
    if not TF_USERNAME or not TF_PASSWORD:
        raise RuntimeError("Missing TF_USERNAME/TF_PASSWORD (Fly secrets)")

    print("=" * 60)
    print("🚂 RAILOPS - FAST WORKER (map-layer extraction)")
    print("=" * 60)
    print(f"MIN_TRAINS_OK={MIN_TRAINS_OK}")
    print("=" * 60)

    backoff = 0
    consecutive_failures = 0
    driver = None

    last_good_trains = load_seed_trains()
    last_good_note = "Seeded from previous trains.json" if last_good_trains else "No good data yet"

    try:
        driver = make_driver()
        ensure_logged_in(driver)
        warmup_map(driver)

        print("🚦 Worker loop started")

        while not STOP:
            try:
                raw = extract_trains(driver)
                print(f"🔎 Raw feature count: {len(raw)}")

                trains = normalize(raw)
                print(f"🚂 Normalized train count: {len(trains)}")

                if len(trains) < MIN_TRAINS_OK:
                    backoff = next_backoff(backoff)

                    if trains:
                        payload = build_payload(trains, f"Low train count ({len(trains)}). Retry in {backoff}s")
                        last_good_trains = trains
                        last_good_note = payload["note"]
                    else:
                        payload = build_payload(
                            last_good_trains,
                            f"Low train count (0). Keeping last good. Retry in {backoff}s | prev: {last_good_note}"
                        )

                    write_local(payload)
                    push_to_web(payload)
                    print(f"📝 Output: {len(payload.get('trains') or [])} trains | LOW -> backoff {backoff}s")

                    time.sleep(backoff)
                    safe_refresh(driver)
                    time.sleep(10)
                    close_warning(driver)
                    consecutive_failures = 0
                    continue

                backoff = 0
                consecutive_failures = 0

                payload = build_payload(trains, "OK")
                last_good_trains = trains
                last_good_note = payload["note"]

                write_local(payload)
                push_to_web(payload)
                print(f"📝 Output: {len(trains)} trains | OK")

                time.sleep(random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS))

            except Exception as e:
                consecutive_failures += 1
                backoff = next_backoff(backoff)

                payload = build_payload(
                    last_good_trains,
                    f"Error: {type(e).__name__}. Keeping last good. Retry in {backoff}s | prev: {last_good_note}"
                )
                write_local(payload)
                push_to_web(payload)

                print(f"📝 Output: {len(payload.get('trains') or [])} trains | ERROR {type(e).__name__} -> backoff {backoff}s")
                time.sleep(backoff)

                if consecutive_failures >= 3:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = make_driver()
                    ensure_logged_in(driver)
                    warmup_map(driver)
                    consecutive_failures = 0
                else:
                    safe_refresh(driver)
                    time.sleep(10)
                    close_warning(driver)

        payload = build_payload(last_good_trains, "Stopping gracefully (keeping last good)")
        write_local(payload)
        push_to_web(payload)

    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
