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


OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "trainfinder_cookies.pkl")
TF_LOGIN_URL = os.environ.get("TF_LOGIN_URL", "https://trainfinder.otenko.com/home/nextlevel")

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

BASE_MIN_SECONDS = int(os.environ.get("BASE_MIN_SECONDS", "15"))
BASE_MAX_SECONDS = int(os.environ.get("BASE_MAX_SECONDS", "30"))

MIN_TRAINS_OK = int(os.environ.get("MIN_TRAINS_OK", "300"))  # lowered: avoid perpetual LOW if TrainFinder changes counts

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
    except Exception as e:
        print(f"⚠️ Push exception: {type(e).__name__}")
        return False


def webmercator_to_latlon(x, y):
    """
    TrainFinder features appear to be WebMercator meters sometimes.
    If not, we also attempt to treat them as lon/lat directly (fallback).
    """
    try:
        x = float(x)
        y = float(y)

        # Heuristic: WebMercator is usually huge numbers (millions)
        if abs(x) > 1000 and abs(y) > 1000:
            lon = (x / 20037508.34) * 180.0
            lat = (y / 20037508.34) * 180.0
            lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
            return round(lat, 6), round(lon, 6)

        # If coords are already lon/lat degrees
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


def ensure_logged_in(driver):
    safe_get(driver, TF_LOGIN_URL)
    time.sleep(5)

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
            time.sleep(4)
            print("✅ Loaded saved cookies")
        except Exception:
            pass

    page = (driver.page_source or "").lower()
    if ("user_name" in page) or ("pass_word" in page) or ("user" in page and "password" in page):
        if not TF_USERNAME or not TF_PASSWORD:
            raise RuntimeError("Missing TF_USERNAME / TF_PASSWORD")

        print("🔐 Login form detected — attempting login…")
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        # Try common IDs
        user_el = None
        for cand in ["useR_name", "user_name", "username", "email"]:
            try:
                user_el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, cand)))
                break
            except Exception:
                continue

        if user_el is None:
            raise RuntimeError("Could not find username field")

        user_el.clear()
        user_el.send_keys(TF_USERNAME)

        pass_el = None
        for cand in ["pasS_word", "pass_word", "password"]:
            try:
                pass_el = driver.find_element(By.ID, cand)
                break
            except Exception:
                continue

        if pass_el is None:
            raise RuntimeError("Could not find password field")

        pass_el.clear()
        pass_el.send_keys(TF_PASSWORD)

        driver.execute_script(
            """
            var buttons = document.querySelectorAll('input[type="button"], button, div.button-green');
            for (var i=0;i<buttons.length;i++){
              var t = (buttons[i].value || buttons[i].textContent || '').toLowerCase();
              if (t.includes('log in') || t.includes('login') || buttons[i].className.includes('button-green')) {
                buttons[i].click(); break;
              }
            }
            """
        )
        time.sleep(8)

        try:
            with open(COOKIE_FILE, "wb") as f:
                pickle.dump(driver.get_cookies(), f)
            print("✅ Cookies saved")
        except Exception:
            pass
    else:
        print("✅ Session appears logged-in (no login form detected).")

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


WAIT_FOR_ANY_SOURCE_JS = r"""
try {
  var names = [
    'regTrainsSource','unregTrainsSource','markerSource','arrowMarkersSource','trainSource','trainMarkers',
    'trainsSource','trains','markers','regTrains','unregTrains'
  ];

  function hasFeatures(s){
    try{
      if (!s) return 0;
      if (typeof s.getFeatures === 'function') return s.getFeatures().length;
      if (Array.isArray(s.features)) return s.features.length;
      if (Array.isArray(s)) return s.length;
      return 0;
    }catch(e){ return 0; }
  }

  for (var i=0;i<names.length;i++){
    var s = window[names[i]];
    var n = hasFeatures(s);
    if (n > 0) return {ok:true, name:names[i], count:n};
  }

  // Fallback: scan window for objects with getFeatures()
  var found = 0;
  var foundName = null;
  for (var k in window){
    try{
      var s2 = window[k];
      if (s2 && typeof s2.getFeatures === 'function'){
        var n2 = s2.getFeatures().length;
        if (n2 > found){
          found = n2;
          foundName = k;
        }
      }
    }catch(e){}
  }
  if (found > 0) return {ok:true, name:foundName, count:found};

  return {ok:false};
} catch(e) { return {ok:false, err:String(e)}; }
"""


EXTRACT_ANY_SOURCES_JS = r"""
try {
  var trains = [];

  function extractFromSource(sourceName, sourceObj){
    if (!sourceObj) return;

    var features = null;
    try{
      if (typeof sourceObj.getFeatures === 'function') features = sourceObj.getFeatures();
    }catch(e){}

    if (!features || !features.length) return;

    for (var i=0;i<features.length;i++){
      try{
        var f = features[i];
        var props = (f.getProperties && f.getProperties()) ? f.getProperties() : (f.values_ || {});
        var geom = (f.getGeometry && f.getGeometry()) ? f.getGeometry() : null;
        if (!geom || !geom.getType || geom.getType() !== 'Point') continue;
        var coords = geom.getCoordinates ? geom.getCoordinates() : null;
        if (!coords || coords.length < 2) continue;

        var t = {
          id: props.id || props.ID || (sourceName + "_" + i),
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
        trains.push(t);
      }catch(e){}
    }
  }

  var names = [
    'regTrainsSource','unregTrainsSource','markerSource','arrowMarkersSource','trainSource','trainMarkers',
    'trainsSource','trains','markers','regTrains','unregTrains'
  ];

  for (var i=0;i<names.length;i++){
    extractFromSource(names[i], window[names[i]]);
  }

  // Fallback: scan window for getFeatures sources and extract the biggest few
  var candidates = [];
  for (var k in window){
    try{
      var s = window[k];
      if (s && typeof s.getFeatures === 'function'){
        var n = s.getFeatures().length;
        if (n > 0) candidates.push({name:k, count:n});
      }
    }catch(e){}
  }
  candidates.sort(function(a,b){ return b.count - a.count; });
  for (var j=0;j<Math.min(6, candidates.length); j++){
    var c = candidates[j];
    extractFromSource(c.name, window[c.name]);
  }

  return trains;
} catch(e) {
  return [];
}
"""


def wait_for_any_source(driver, timeout_s=90):
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            res = driver.execute_script(WAIT_FOR_ANY_SOURCE_JS)
            if isinstance(res, dict) and res.get("ok"):
                print(f"✅ Found source: {res.get('name')} ({res.get('count')} features)")
                return True
        except Exception:
            pass
        time.sleep(2)
    print("⚠️ No sources with features found within timeout")
    return False


def extract_trains(driver):
    if not wait_for_any_source(driver, timeout_s=90):
        return []
    for _ in range(6):
        try:
            raw = driver.execute_script(EXTRACT_ANY_SOURCES_JS) or []
            if len(raw) >= 50:
                return raw
        except TimeoutException:
            print("⚠️ Script timeout during extract — retrying")
        except WebDriverException:
            pass
        time.sleep(2)
    try:
        return driver.execute_script(EXTRACT_ANY_SOURCES_JS) or []
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
        raise RuntimeError("Missing TF_USERNAME/TF_PASSWORD (set as Fly secrets)")

    print("=" * 60)
    print("🚂 RAILOPS - FAST WORKER (expanded source extraction)")
    print("=" * 60)
    print(f"BASE_MIN_SECONDS={BASE_MIN_SECONDS} BASE_MAX_SECONDS={BASE_MAX_SECONDS}")
    print(f"MIN_TRAINS_OK={MIN_TRAINS_OK}")
    print(f"INITIAL_BACKOFF_SECONDS={INITIAL_BACKOFF_SECONDS} MAX_BACKOFF_SECONDS={MAX_BACKOFF_SECONDS} MULT={BACKOFF_MULTIPLIER}")
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

        print("🚦 Worker loop started (seeded last-good + expanded sources + gentle backoff)")

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

                # Good data
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
