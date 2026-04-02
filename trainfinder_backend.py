import os
import re
import json
import time
import math
import pickle
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException


TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
TF_HOME_URL = "https://trainfinder.otenko.com/home/nextlevel"
COOKIE_PKL = "trainfinder_cookies.pkl"
COOKIE_TXT = "cookie.txt"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()


def now_utc_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def load_text_cookie() -> Optional[str]:
    env_cookie = (
        os.environ.get("ASPXAUTH", "").strip()
        or os.environ.get("TRAINFINDER_COOKIE", "").strip()
        or os.environ.get("TRAINFINDER_COOKIE_RAW", "").strip()
    )
    if env_cookie:
        return env_cookie

    if os.path.exists(COOKIE_TXT):
        raw = open(COOKIE_TXT, "r", encoding="utf-8").read().strip()
        if not raw:
            return None

        m = re.search(r"\.ASPXAUTH=([^;\s]+)", raw)
        if m:
            return m.group(1).strip()

        return raw

    return None


def save_text_cookie(cookie_value: str) -> None:
    cookie_value = (cookie_value or "").strip()
    if not cookie_value:
        return
    with open(COOKIE_TXT, "w", encoding="utf-8") as f:
        f.write(cookie_value)


def save_cookies(driver: webdriver.Chrome) -> None:
    cookies = driver.get_cookies()
    with open(COOKIE_PKL, "wb") as f:
        pickle.dump(cookies, f)

    aspxauth = get_aspxauth_from_driver(driver)
    if aspxauth:
        save_text_cookie(aspxauth)


def load_cookie_pickle() -> List[Dict[str, Any]]:
    if not os.path.exists(COOKIE_PKL):
        return []
    try:
        with open(COOKIE_PKL, "rb") as f:
            data = pickle.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def get_aspxauth_from_driver(driver: webdriver.Chrome) -> Optional[str]:
    try:
        for c in driver.get_cookies():
            if c.get("name") == ".ASPXAUTH" and c.get("value"):
                return c["value"]
    except Exception:
        pass
    return None


def make_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-AU")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)

    try:
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
    except Exception:
        pass

    return driver


def wait_for_page(seconds: float = 5.0) -> None:
    time.sleep(seconds)


def add_aspxauth_cookie(driver: webdriver.Chrome, cookie_value: str) -> bool:
    cookie_value = (cookie_value or "").strip()
    if not cookie_value:
        return False

    try:
        driver.get("https://trainfinder.otenko.com/")
        wait_for_page(2)
        driver.add_cookie(
            {
                "name": ".ASPXAUTH",
                "value": cookie_value,
                "domain": "trainfinder.otenko.com",
                "path": "/",
                "secure": True,
            }
        )
        return True
    except Exception:
        return False


def add_pickle_cookies(driver: webdriver.Chrome, cookies: List[Dict[str, Any]]) -> bool:
    if not cookies:
        return False

    try:
        driver.get("https://trainfinder.otenko.com/")
        wait_for_page(2)

        added_any = False
        for c in cookies:
            try:
                cookie = dict(c)
                cookie.pop("sameSite", None)
                if cookie.get("expiry") is None:
                    cookie.pop("expiry", None)
                if "domain" not in cookie or not cookie["domain"]:
                    cookie["domain"] = "trainfinder.otenko.com"
                if "path" not in cookie or not cookie["path"]:
                    cookie["path"] = "/"
                driver.add_cookie(cookie)
                added_any = True
            except Exception:
                continue
        return added_any
    except Exception:
        return False


def looks_logged_in(driver: webdriver.Chrome) -> bool:
    try:
        current = (driver.current_url or "").lower()
        source = (driver.page_source or "").lower()

        if "returnurl=" in current:
            return False
        if "/account/login" in current:
            return False
        if "login" in current and "nextlevel" not in current:
            return False

        cookies_json = json.dumps(driver.get_cookies()).lower()
        if ".aspxauth" in cookies_json and "sign in" not in source and "password" not in source:
            return True

        if "logout" in source:
            return True
        if "openlayers" in source:
            return True
    except Exception:
        pass
    return False


def dismiss_overlays(driver: webdriver.Chrome) -> None:
    selectors = [
        "button",
        ".close",
        ".btn-close",
        ".modal .close",
        ".modal button",
        ".swal2-confirm",
    ]
    texts = {"ok", "okay", "close", "dismiss", "continue", "accept"}

    for _ in range(3):
        try:
            for sel in selectors:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    try:
                        txt = (el.text or "").strip().lower()
                        if txt in texts:
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(1)
                    except Exception:
                        continue
        except Exception:
            pass

    try:
        driver.execute_script(
            """
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
            """
        )
    except Exception:
        pass


def try_cookie_login(driver: webdriver.Chrome) -> bool:
    raw_cookie = load_text_cookie()
    pickle_cookies = load_cookie_pickle()

    if raw_cookie:
        add_aspxauth_cookie(driver, raw_cookie)
        driver.get(TF_HOME_URL)
        wait_for_page(6)
        dismiss_overlays(driver)
        if looks_logged_in(driver):
            save_cookies(driver)
            return True

    if pickle_cookies:
        add_pickle_cookies(driver, pickle_cookies)
        driver.get(TF_HOME_URL)
        wait_for_page(6)
        dismiss_overlays(driver)
        if looks_logged_in(driver):
            save_cookies(driver)
            return True

    return False


def find_first(driver: webdriver.Chrome, selectors: List[Tuple[str, str]]):
    for by, value in selectors:
        try:
            el = driver.find_element(by, value)
            if el:
                return el
        except NoSuchElementException:
            continue
    return None


def try_password_login(driver: webdriver.Chrome) -> bool:
    if not TF_USERNAME or not TF_PASSWORD:
        return False

    driver.get(TF_LOGIN_URL)
    wait_for_page(5)
    dismiss_overlays(driver)

    user = find_first(
        driver,
        [
            (By.ID, "useR_name"),
            (By.NAME, "useR_name"),
            (By.ID, "Email"),
            (By.NAME, "Email"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[type='text']"),
        ],
    )

    pw = find_first(
        driver,
        [
            (By.ID, "pasS_word"),
            (By.NAME, "pasS_word"),
            (By.ID, "Password"),
            (By.NAME, "Password"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ],
    )

    if not user or not pw:
        return False

    try:
        user.clear()
        user.send_keys(TF_USERNAME)
        pw.clear()
        pw.send_keys(TF_PASSWORD)
        pw.send_keys("\n")
        time.sleep(8)
        dismiss_overlays(driver)

        if looks_logged_in(driver):
            save_cookies(driver)
            return True
    except Exception:
        return False

    return False


def ensure_session(headless: bool = True):
    driver = make_driver(headless=headless)

    try:
        if try_cookie_login(driver):
            return driver, True, "cookie login ok"

        if try_password_login(driver):
            return driver, True, "password login ok"

        return driver, False, "could not establish TrainFinder session"
    except Exception as e:
        return driver, False, f"session error: {e}"


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _extract_numeric(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    s = str(v)
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return default
    try:
        return float(m.group(0))
    except Exception:
        return default


def _wm_to_latlon(x: float, y: float) -> Tuple[float, float]:
    lon = (x / 20037508.34) * 180.0
    lat = (y / 20037508.34) * 180.0
    lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
    return lat, lon


def debug_page_state(driver: webdriver.Chrome) -> Dict[str, Any]:
    js = r"""
    function getCountFromObj(obj) {
      try {
        if (!obj) return null;
        if (typeof obj.getFeatures === 'function') {
          var f = obj.getFeatures() || [];
          return f.length;
        }
        if (obj.source && typeof obj.source.getFeatures === 'function') {
          var f2 = obj.source.getFeatures() || [];
          return f2.length;
        }
      } catch (e) {}
      return null;
    }

    var result = {
      url: location.href,
      title: document.title,
      readyState: document.readyState,
      globals: [],
      pageHints: {
        hasOl: !!window.ol,
        hasMap: !!window.map,
        bodyTextSnippet: (document.body && document.body.innerText ? document.body.innerText.slice(0, 1000) : '')
      }
    };

    var keys = Object.keys(window).sort();
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (
        /train|marker|source|layer|map|feature|ol/i.test(k)
      ) {
        try {
          var v = window[k];
          var count = getCountFromObj(v);
          var item = {
            name: k,
            type: typeof v,
            hasGetFeatures: !!(v && typeof v.getFeatures === 'function'),
            featureCount: count
          };
          result.globals.push(item);
        } catch (e) {}
      }
    }

    return result;
    """
    try:
        return driver.execute_script(js)
    except Exception as e:
        return {"error": str(e)}


def scrape_trains_from_page(driver: webdriver.Chrome) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    debug: Dict[str, Any] = {}

    try:
        driver.get(TF_HOME_URL)
        wait_for_page(8)
        dismiss_overlays(driver)

        try:
            driver.execute_script(
                """
                try {
                    if (window.map && window.ol) {
                        var australia = [112, -44, 154, -10];
                        var proj = window.map.getView().getProjection();
                        var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                        window.map.getView().fit(extent, { duration: 0, maxZoom: 8 });
                    }
                } catch (e) {}
                """
            )
        except Exception:
            pass

        wait_for_page(20)

        debug = debug_page_state(driver)

        js = r"""
        function numFromText(v) {
          if (v === null || v === undefined) return 0;
          var m = String(v).match(/-?\d+(\.\d+)?/);
          return m ? Number(m[0]) : 0;
        }

        function wmToLatLon(x, y) {
          var lon = (x / 20037508.34) * 180;
          var lat = (y / 20037508.34) * 180;
          lat = 180 / Math.PI * (2 * Math.atan(Math.exp(lat * Math.PI / 180)) - Math.PI / 2);
          return [lat, lon];
        }

        function extractFromFeature(feature, sourceName, index) {
          try {
            var props = feature && feature.getProperties ? (feature.getProperties() || {}) : {};
            var geom = feature && feature.getGeometry ? feature.getGeometry() : null;
            if (!geom || !geom.getCoordinates) return null;

            var coords = geom.getCoordinates();
            if (!coords || coords.length < 2) return null;

            var lat = null;
            var lon = null;

            if (Math.abs(coords[0]) > 1000 || Math.abs(coords[1]) > 1000) {
              var ll = wmToLatLon(coords[0], coords[1]);
              lat = ll[0];
              lon = ll[1];
            } else {
              lon = Number(coords[0]);
              lat = Number(coords[1]);
            }

            if (!(lat > -90 && lat < 90 && lon > -180 && lon < 180)) return null;
            if (lat < -45 || lat > -8 || lon < 110 || lon > 155) return null;

            var trainNumber = props.trainNumber || props.train_number || props.ID || props.id || '';
            var trainName = props.trainName || props.train_name || props.name || '';
            var loco = props.loco || props.locoNumber || props.loco_number || '';
            var origin = props.serviceFrom || props.origin || props.from || '';
            var destination = props.serviceTo || props.destination || props.to || '';
            var description = props.serviceDesc || props.description || props.service || '';
            var km = props.trainKM || props.km || '';
            var trainTime = props.trainTime || props.time || '';
            var trainDate = props.trainDate || props.date || '';
            var cId = props.cId || '';
            var servId = props.servId || '';
            var trKey = props.trKey || '';
            var heading = Number(props.heading || props.bearing || props.dir || 0) || 0;
            var speed = numFromText(props.trainSpeed || props.speed || props.spd || 0);

            var id = String(trKey || cId || trainName || trainNumber || loco || (sourceName + '_' + index)).trim();
            if (!id) return null;

            return {
              id: id,
              train_number: String(trainNumber || ''),
              train_name: String(trainName || ''),
              loco: String(loco || ''),
              speed: speed,
              heading: heading,
              origin: String(origin || ''),
              destination: String(destination || ''),
              description: String(description || ''),
              km: String(km || ''),
              time: String(trainTime || ''),
              date: String(trainDate || ''),
              cId: String(cId || ''),
              servId: String(servId || ''),
              trKey: String(trKey || ''),
              lat: lat,
              lon: lon,
              raw: props
            };
          } catch (e) {
            return null;
          }
        }

        function collectFeaturesFromAnyObject(name, obj) {
          var out = [];
          try {
            if (!obj) return out;

            if (typeof obj.getFeatures === 'function') {
              var arr = obj.getFeatures() || [];
              for (var i = 0; i < arr.length; i++) {
                out.push({ sourceName: name, feature: arr[i], index: i });
              }
              return out;
            }

            if (obj.source && typeof obj.source.getFeatures === 'function') {
              var arr2 = obj.source.getFeatures() || [];
              for (var j = 0; j < arr2.length; j++) {
                out.push({ sourceName: name, feature: arr2[j], index: j });
              }
              return out;
            }
          } catch (e) {}
          return out;
        }

        var results = [];
        var seen = {};
        var keys = Object.keys(window);

        for (var k = 0; k < keys.length; k++) {
          var name = keys[k];
          if (!/train|marker|source|layer|feature/i.test(name)) continue;

          var entries = collectFeaturesFromAnyObject(name, window[name]);
          for (var x = 0; x < entries.length; x++) {
            var row = extractFromFeature(entries[x].feature, entries[x].sourceName, entries[x].index);
            if (!row) continue;

            var dedupKey = row.id + '|' + row.lat.toFixed(5) + '|' + row.lon.toFixed(5);
            if (!seen[dedupKey]) {
              seen[dedupKey] = true;
              results.push(row);
            }
          }
        }

        return results;
        """
        trains = driver.execute_script(js)
        if not isinstance(trains, list):
            trains = []

        return trains, debug
    except Exception as e:
        debug = {"error": str(e)}
        return [], debug


def write_debug_json(debug: Dict[str, Any], out_file: str = "debug_sources.json") -> None:
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(debug, f, indent=2)


def write_trains_json(
    trains: List[Dict[str, Any]],
    out_file: str = "trains.json",
    note: str = "ok",
    preserve_existing_if_empty: bool = True,
) -> Dict[str, Any]:
    payload = {
        "lastUpdated": now_utc_iso(),
        "note": f"{note} - {len(trains)} trains",
        "trains": trains,
    }

    if preserve_existing_if_empty and len(trains) == 0 and os.path.exists(out_file):
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                old = json.load(f)
            old_trains = old.get("trains", [])
            if isinstance(old_trains, list) and len(old_trains) > 0:
                old["lastUpdated"] = now_utc_iso()
                old["note"] = f"{note} - kept previous {len(old_trains)} trains"
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(old, f, indent=2)
                return old
        except Exception:
            pass

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return payload
