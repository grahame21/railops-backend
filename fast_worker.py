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
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ----------------------------
# Config
# ----------------------------
OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "trainfinder_cookies.pkl")

TF_URL = os.environ.get("TF_LOGIN_URL", "https://trainfinder.otenko.com/home/nextlevel")
TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

PUSH_URL = os.environ.get("PUSH_URL", "https://railops-live-au.fly.dev/push")
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "").strip()

BASE_MIN_SECONDS = int(os.environ.get("BASE_MIN_SECONDS", "18"))
BASE_MAX_SECONDS = int(os.environ.get("BASE_MAX_SECONDS", "28"))

# If we get fewer trains than this, keep last-good and retry
MIN_OK_TRAINS = int(os.environ.get("MIN_OK_TRAINS", "8"))

STOP = False


def stop_handler(sig, frame):
    global STOP
    STOP = True


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


# ----------------------------
# Helpers
# ----------------------------
def utc_now_z():
    return datetime.datetime.utcnow().isoformat() + "Z"


def payload(trains, note):
    return {"lastUpdated": utc_now_z(), "note": note, "trains": trains or []}


def write_local(p):
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def push(p):
    if not PUSH_URL or not PUSH_TOKEN:
        print("⚠️ PUSH_URL/PUSH_TOKEN not set, skipping push")
        return
    try:
        r = requests.post(PUSH_URL, json=p, headers={"X-Auth-Token": PUSH_TOKEN}, timeout=20)
        if not (200 <= r.status_code < 300):
            print(f"⚠️ Push failed HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print("⚠️ Push exception:", type(e).__name__)


def is_junk_id(s):
    if not s:
        return True
    v = str(s).lower()
    return (
        v.startswith("arrowmarkerssource_")
        or v.startswith("markersource_")
        or v.startswith("regtrainssource_")
        or v.startswith("unregtrainssource_")
        or v.startswith("trainsource_")
        or "arrowmarkerssource" in v
    )


def webmercator_to_latlon(x, y):
    """x/y in EPSG:3857 meters -> lat/lon degrees"""
    try:
        x = float(x)
        y = float(y)
        lon = (x / 20037508.34) * 180.0
        lat = (y / 20037508.34) * 180.0
        lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


def make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-AU")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(180)
    driver.set_script_timeout(120)
    return driver


def safe_get(driver, url):
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass


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


def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE):
        return False
    try:
        with open(COOKIE_FILE, "rb") as f:
            cookies = pickle.load(f)
        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        print("✅ Loaded saved cookies")
        return True
    except Exception:
        return False


def save_cookies(driver):
    try:
        with open(COOKIE_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("✅ Cookies saved")
    except Exception:
        pass


def login_if_needed(driver):
    safe_get(driver, TF_URL)
    time.sleep(5)

    # load cookies and reload
    if load_cookies(driver):
        safe_get(driver, TF_URL)
        time.sleep(4)

    # Determine if login form present
    page = (driver.page_source or "").lower()
    need_login = ("pas" in page and "log" in page)  # loose
    try:
        pw = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if pw:
            need_login = True
    except Exception:
        pass

    if not need_login:
        print("✅ Session appears logged-in (no login form detected).")
        close_warning(driver)
        return

    if not TF_USERNAME or not TF_PASSWORD:
        raise RuntimeError("Missing TF_USERNAME/TF_PASSWORD")

    print("🔐 Login form detected — attempting login…")

    # Use your known IDs first
    user = None
    pw = None
    try:
        user = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "useR_name")))
        pw = driver.find_element(By.ID, "pasS_word")
    except Exception:
        # Fallback selectors
        try:
            user = driver.find_element(By.CSS_SELECTOR, "input[type='email'],input[type='text']")
            pw = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        except Exception:
            raise RuntimeError("Could not find username/password fields")

    user.clear()
    user.send_keys(TF_USERNAME)
    pw.clear()
    pw.send_keys(TF_PASSWORD)
    pw.send_keys("\n")

    time.sleep(8)
    save_cookies(driver)
    close_warning(driver)


def zoom_to_australia(driver):
    try:
        driver.execute_script(
            """
            if (window.map && window.ol && window.ol.proj) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 0, maxZoom: 10 });
            }
            """
        )
    except Exception:
        pass


def extract_trains_from_map(driver):
    """
    Returns a list of trains already normalized for your dashboard.html:
    lat/lon degrees, speed km/h (if present), heading degrees, origin/destination/desc, plus ids.
    """
    js = r"""
    function isJunkId(s){
      if (!s) return true;
      const v = String(s).toLowerCase();
      return v.startsWith("arrowmarkerssource_")
          || v.startsWith("markersource_")
          || v.startsWith("regtrainssource_")
          || v.startsWith("unregtrainssource_")
          || v.startsWith("trainsource_")
          || v.includes("arrowmarkerssource");
    }

    function getAny(props, keys){
      for (const k of keys){
        if (props[k] !== undefined && props[k] !== null && String(props[k]).trim() !== ""){
          return props[k];
        }
      }
      return "";
    }

    function normalizeTrain(props, coords3857){
      const x = coords3857[0], y = coords3857[1];

      // Try common fields used by TrainFinder props
      const trKey = getAny(props, ["trKey","TrKey","trk","key","Key","id","ID"]);
      const loco = getAny(props, ["loco","Loco","unit","Unit","train_name","trainName","name","Name"]);
      const trainNumber = getAny(props, ["train_number","trainNumber","trainNo","TrainNo","service","Service"]);
      const origin = getAny(props, ["origin","serviceFrom","from","From"]);
      const destination = getAny(props, ["destination","serviceTo","to","To"]);
      const desc = getAny(props, ["description","serviceDesc","desc","Desc"]);
      const speed = Number(getAny(props, ["speed","Speed","velocity","Velocity"])) || 0;
      const heading = Number(getAny(props, ["heading","Heading","rotation","Rotation"])) || 0;

      // Junk filter
      const labelCandidate = (String(loco || trKey || trainNumber)).trim();
      if (!labelCandidate || isJunkId(labelCandidate)) return null;

      return {
        trKey: String(trKey || ""),
        loco: String(loco || ""),
        train_number: String(trainNumber || ""),
        origin: String(origin || ""),
        destination: String(destination || ""),
        description: String(desc || ""),
        speed: speed,
        heading: heading,
        x: x,
        y: y
      };
    }

    function extractFromSource(src){
      const out = [];
      if (!src || !src.getFeatures) return out;
      try{
        const features = src.getFeatures();
        for (const f of features){
          try{
            const geom = f.getGeometry();
            if (!geom || geom.getType() !== "Point") continue;
            const coords = geom.getCoordinates();
            const props = f.getProperties() || {};
            const tr = normalizeTrain(props, coords);
            if (tr) out.push(tr);
          }catch(e){}
        }
      }catch(e){}
      return out;
    }

    let trains = [];

    // IMPORTANT: ONLY real train sources, NOT markers/arrows
    trains = trains.concat(extractFromSource(window.regTrainsSource));
    trains = trains.concat(extractFromSource(window.unregTrainsSource));

    // Some pages have layers instead of globals
    try{
      if (window.regTrainsLayer && window.regTrainsLayer.getSource) {
        trains = trains.concat(extractFromSource(window.regTrainsLayer.getSource()));
      }
      if (window.unregTrainsLayer && window.unregTrainsLayer.getSource) {
        trains = trains.concat(extractFromSource(window.unregTrainsLayer.getSource()));
      }
    }catch(e){}

    // Dedup by key-ish + coords
    const seen = new Set();
    const dedup = [];
    for (const t of trains){
      const key = (t.trKey || t.loco || t.train_number) + "|" + Math.round(t.x) + "|" + Math.round(t.y);
      if (seen.has(key)) continue;
      seen.add(key);
      dedup.push(t);
    }

    return dedup;
    """
    return driver.execute_script(js)


def main():
    if not TF_USERNAME or not TF_PASSWORD:
        p = payload([], "missing credentials")
        write_local(p)
        push(p)
        print("❌ Missing TF_USERNAME/TF_PASSWORD")
        return

    print("=" * 60)
    print("🚂 RAILOPS - PROPER MAP TRAINS EXTRACTOR")
    print("=" * 60)

    last_good = []
    driver = None

    try:
        driver = make_driver()

        while not STOP:
            try:
                login_if_needed(driver)

                print("⏳ Warmup: waiting 20s for map…")
                time.sleep(20)
                zoom_to_australia(driver)
                time.sleep(12)

                raw = extract_trains_from_map(driver) or []
                print(f"🔎 Raw extracted: {len(raw)} items")

                trains = []
                for t in raw:
                    lat, lon = webmercator_to_latlon(t.get("x"), t.get("y"))
                    if lat is None or lon is None:
                        continue
                    # AU bounds sanity
                    if not (-45 <= lat <= -9 and 110 <= lon <= 155):
                        continue

                    # map schema your dashboard expects
                    trains.append({
                        "trKey": t.get("trKey",""),
                        "loco": t.get("loco",""),
                        "train_number": t.get("train_number",""),
                        "origin": t.get("origin",""),
                        "destination": t.get("destination",""),
                        "description": t.get("description",""),
                        "speed": float(t.get("speed",0) or 0),
                        "heading": float(t.get("heading",0) or 0),
                        "lat": lat,
                        "lon": lon
                    })

                # Keep last-good if tiny/empty
                if len(trains) < MIN_OK_TRAINS and last_good:
                    note = f"low ({len(trains)}). keeping last-good {len(last_good)}"
                    p = payload(last_good, note)
                    write_local(p)
                    push(p)
                    print(f"📝 Output: {len(last_good)} trains | {note}")
                else:
                    last_good = trains
                    note = f"ok - {len(trains)} trains"
                    p = payload(trains, note)
                    write_local(p)
                    push(p)
                    print(f"📝 Output: {len(trains)} trains | OK")

                # jittered loop
                time.sleep(random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS))

            except Exception as e:
                note = f"error: {type(e).__name__}"
                p = payload(last_good, note)
                write_local(p)
                push(p)
                print("❌ Loop error:", note)
                time.sleep(15)

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
