import datetime
import json
import math
import os
import pickle
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

TF_URL = os.environ.get("TF_LOGIN_URL", "https://trainfinder.otenko.com/home/nextlevel")
OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "trainfinder_cookies.pkl")
COOKIE_TEXT_FILE = os.environ.get("COOKIE_TEXT_FILE", "cookie.txt")
TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()
MIN_OK_TRAINS = int(os.environ.get("MIN_OK_TRAINS", "8"))

EXTRACT_JS = r"""
return (function() {
  function isJunkId(s) {
    if (!s) return true;
    const v = String(s).toLowerCase();
    return v.startsWith('arrowmarkerssource_')
      || v.startsWith('markersource_')
      || v.startsWith('regtrainssource_')
      || v.startsWith('unregtrainssource_')
      || v.startsWith('trainsource_')
      || v.includes('arrowmarkerssource');
  }
  function toLatLon(x, y) {
    const lon = (x / 20037508.34) * 180.0;
    let lat = (y / 20037508.34) * 180.0;
    lat = 180.0 / Math.PI * (2.0 * Math.atan(Math.exp(lat * Math.PI / 180.0)) - Math.PI / 2.0);
    return { lat, lon };
  }
  function inAustralia(lat, lon) {
    return lat >= -45 && lat <= -8 && lon >= 110 && lon <= 155;
  }
  function parseSpeed(v) {
    if (v == null) return 0;
    const m = String(v).match(/(\d+(?:\.\d+)?)/);
    return m ? Number(m[1]) : 0;
  }
  const sources = ['regTrainsSource','unregTrainsSource','markerSource','arrowMarkersSource','trainSource','trainMarkers','trainPoints'];
  const trains = [];
  const seen = new Set();
  for (const sourceName of sources) {
    const source = window[sourceName];
    if (!source || !source.getFeatures) continue;
    let features = [];
    try { features = source.getFeatures() || []; } catch (e) { features = []; }
    for (let i = 0; i < features.length; i++) {
      const feature = features[i];
      try {
        const geom = feature.getGeometry && feature.getGeometry();
        if (!geom || !geom.getCoordinates) continue;
        const coords = geom.getCoordinates();
        if (!coords || coords.length < 2) continue;
        const ll = toLatLon(coords[0], coords[1]);
        if (!inAustralia(ll.lat, ll.lon)) continue;
        const props = feature.getProperties ? (feature.getProperties() || {}) : {};
        const trainNumber = props.trainNumber || props.train_number || props.ID || props.id || '';
        const trainName = props.trainName || props.train_name || props.name || props.NAME || props.loco || props.trKey || '';
        const loco = props.loco || props.Loco || props.unit || props.Unit || props.trKey || '';
        const origin = props.serviceFrom || props.origin || props.Origin || '';
        const destination = props.serviceTo || props.destination || props.Destination || '';
        const description = props.serviceDesc || props.description || props.Description || props.service || props.Service || '';
        const cId = props.cId || '';
        const servId = props.servId || '';
        const trKey = props.trKey || '';
        const heading = Number(props.heading || props.Heading || 0) || 0;
        const speed = parseSpeed(props.trainSpeed || props.speed || props.Speed || 0);
        const km = props.trainKM || props.km || '';
        const trainTime = props.trainTime || props.time || props.timestamp || '';
        const trainDate = props.trainDate || props.date || '';
        const id = String(trainName || trainNumber || loco || cId || servId || `${sourceName}_${i}`).trim();
        if (!id || isJunkId(id)) continue;
        if (seen.has(id)) continue;
        seen.add(id);
        trains.push({
          id,
          train_number: String(trainNumber || '').trim(),
          train_name: String(trainName || '').trim(),
          loco: String(loco || '').trim(),
          origin: String(origin || '').trim(),
          destination: String(destination || '').trim(),
          description: String(description || '').trim(),
          cId: String(cId || '').trim(),
          servId: String(servId || '').trim(),
          trKey: String(trKey || '').trim(),
          speed,
          heading,
          km: String(km || '').trim(),
          time: String(trainTime || '').trim(),
          date: String(trainDate || '').trim(),
          lat: Number(ll.lat.toFixed(6)),
          lon: Number(ll.lon.toFixed(6)),
          source: sourceName
        });
      } catch (e) {}
    }
  }
  return trains;
})();
"""

def utc_now_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

def payload(trains: List[Dict[str, Any]], note: str) -> Dict[str, Any]:
    return {"lastUpdated": utc_now_z(), "note": note, "trains": trains or []}

def write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def read_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def load_last_good() -> Optional[Dict[str, Any]]:
    data = read_json(OUT_FILE)
    if isinstance(data, dict) and isinstance(data.get("trains"), list) and data.get("trains"):
        return data
    return None

def extract_aspxauth(value: str) -> str:
    if not value:
        return ""
    m = re.search(r"(?:^|;\s*)\.ASPXAUTH=([^;\s]+)", value)
    if m:
        return m.group(1).strip()
    return value.strip().strip('"').strip("'")

def raw_cookie_value() -> str:
    for key in ("ASPXAUTH", "TRAINFINDER_COOKIE", "TRAINFINDER_COOKIE_RAW"):
        val = os.environ.get(key, "").strip()
        if val:
            return extract_aspxauth(val)
    if os.path.exists(COOKIE_TEXT_FILE):
        try:
            return extract_aspxauth(Path(COOKIE_TEXT_FILE).read_text(encoding="utf-8").strip())
        except Exception:
            return ""
    return ""

def save_cookie_text(value: str) -> None:
    if value:
        Path(COOKIE_TEXT_FILE).write_text(value.strip(), encoding="utf-8")

def make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-AU")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    return driver

def safe_get(driver: webdriver.Chrome, url: str) -> None:
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass

def close_warning(driver: webdriver.Chrome) -> None:
    try:
        driver.execute_script("""
            var paths = document.getElementsByTagName('path');
            for (var i = 0; i < paths.length; i++) {
              var d = paths[i].getAttribute('d') || '';
              if (d.includes('M13.7,11l6.1-6.1')) {
                var parent = paths[i].parentElement;
                while (parent && parent.tagName !== 'BUTTON' && parent.tagName !== 'DIV' && parent.tagName !== 'A') {
                  parent = parent.parentElement;
                }
                if (parent) { parent.click(); break; }
              }
            }
        """)
    except Exception:
        pass

def save_cookies(driver: webdriver.Chrome) -> None:
    cookies = driver.get_cookies()
    try:
        with open(COOKIE_FILE, "wb") as f:
            pickle.dump(cookies, f)
    except Exception:
        pass
    for c in cookies:
        if c.get("name") == ".ASPXAUTH" and c.get("value"):
            save_cookie_text(c["value"])
            break

def inject_cookies(driver: webdriver.Chrome) -> bool:
    injected = False
    raw = raw_cookie_value()
    if raw:
        try:
            driver.add_cookie({"name": ".ASPXAUTH", "value": raw, "domain": "trainfinder.otenko.com", "path": "/", "secure": True})
            injected = True
        except Exception:
            pass
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "rb") as f:
                cookies = pickle.load(f)
            for c in cookies:
                try:
                    c = dict(c)
                    c.pop("sameSite", None)
                    driver.add_cookie(c)
                    injected = True
                except Exception:
                    pass
        except Exception:
            pass
    return injected

def page_has_login_form(driver: webdriver.Chrome) -> bool:
    try:
        if driver.find_elements(By.ID, "useR_name") or driver.find_elements(By.ID, "pasS_word"):
            return True
        if driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
            return True
    except Exception:
        pass
    text = (driver.page_source or "").lower()
    return "login" in text and "password" in text

def login_with_credentials(driver: webdriver.Chrome) -> bool:
    if not TF_USERNAME or not TF_PASSWORD:
        return False
    try:
        user = WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.ID, "useR_name")))
        pw = driver.find_element(By.ID, "pasS_word")
    except Exception:
        try:
            user = driver.find_element(By.CSS_SELECTOR, "input[type='text'],input[type='email']")
            pw = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        except Exception:
            return False
    user.clear(); user.send_keys(TF_USERNAME)
    pw.clear(); pw.send_keys(TF_PASSWORD); pw.send_keys("
")
    time.sleep(8)
    close_warning(driver)
    save_cookies(driver)
    return True

def ensure_session(driver: webdriver.Chrome) -> Tuple[bool, str]:
    safe_get(driver, TF_URL)
    time.sleep(3)
    injected = inject_cookies(driver)
    if injected:
        safe_get(driver, TF_URL)
        time.sleep(4)
        close_warning(driver)
        if not page_has_login_form(driver):
            save_cookies(driver)
            return True, "session restored from saved cookie"
    safe_get(driver, TF_URL)
    time.sleep(3)
    if not page_has_login_form(driver):
        close_warning(driver)
        save_cookies(driver)
        return True, "session already active"
    if login_with_credentials(driver):
        safe_get(driver, TF_URL)
        time.sleep(5)
        close_warning(driver)
        if not page_has_login_form(driver):
            return True, "logged in with TF_USERNAME/TF_PASSWORD"
        return False, "login attempted but session still not active"
    return False, "missing .ASPXAUTH cookie (set ASPXAUTH env or provide cookie.txt)"

def zoom_to_australia(driver: webdriver.Chrome) -> None:
    try:
        driver.execute_script("""
            if (window.map && window.ol && window.ol.proj) {
              var australia = [112, -44, 154, -10];
              var proj = window.map.getView().getProjection();
              var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
              window.map.getView().fit(extent, { duration: 0, maxZoom: 10 });
            }
        """)
    except Exception:
        pass

def extract_trains(driver: webdriver.Chrome, tries: int = 4) -> List[Dict[str, Any]]:
    best = []
    for attempt in range(tries):
        time.sleep(8 if attempt == 0 else 6)
        zoom_to_australia(driver)
        time.sleep(3)
        try:
            trains = driver.execute_script(EXTRACT_JS) or []
        except Exception:
            trains = []
        if len(trains) > len(best):
            best = trains
        if len(best) >= MIN_OK_TRAINS:
            break
        try:
            driver.refresh()
        except Exception:
            pass
    return best

def scrape_trains(headless: bool = True) -> Tuple[List[Dict[str, Any]], str]:
    driver = make_driver(headless=headless)
    try:
        ok, session_note = ensure_session(driver)
        if not ok:
            return [], session_note
        trains = extract_trains(driver)
        if trains:
            return trains, f"ok - {len(trains)} trains ({session_note})"
        return [], f"session ok but extracted 0 trains ({session_note})"
    finally:
        try:
            save_cookies(driver)
        except Exception:
            pass
        driver.quit()

def update_local_file(headless: bool = True, preserve_last_good: bool = True) -> Dict[str, Any]:
    trains, note = scrape_trains(headless=headless)
    if trains:
        data = payload(trains, note)
        write_json_atomic(OUT_FILE, data)
        return data
    last_good = load_last_good() if preserve_last_good else None
    if last_good:
        stale = dict(last_good)
        stale["lastUpdated"] = utc_now_z()
        stale["note"] = f"stale data kept - {note}"
        write_json_atomic(OUT_FILE, stale)
        return stale
    data = payload([], note)
    write_json_atomic(OUT_FILE, data)
    return data
