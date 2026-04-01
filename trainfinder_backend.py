import os
import re
import json
import time
import pickle
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException


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
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def wait_for_page(driver: webdriver.Chrome, seconds: float = 5.0) -> None:
    time.sleep(seconds)


def add_aspxauth_cookie(driver: webdriver.Chrome, cookie_value: str) -> bool:
    cookie_value = (cookie_value or "").strip()
    if not cookie_value:
        return False

    try:
        driver.get("https://trainfinder.otenko.com/")
        wait_for_page(driver, 2)

        cookie = {
            "name": ".ASPXAUTH",
            "value": cookie_value,
            "domain": "trainfinder.otenko.com",
            "path": "/",
            "secure": True,
        }
        driver.add_cookie(cookie)
        return True
    except Exception:
        return False


def add_pickle_cookies(driver: webdriver.Chrome, cookies: List[Dict[str, Any]]) -> bool:
    if not cookies:
        return False

    try:
        driver.get("https://trainfinder.otenko.com/")
        wait_for_page(driver, 2)

        added_any = False
        for c in cookies:
            try:
                cookie = dict(c)
                cookie.pop("sameSite", None)
                cookie.pop("expiry", None) if cookie.get("expiry") is None else None
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

        if ".aspxauth" in json.dumps(driver.get_cookies()).lower():
            if "sign in" not in source and "username" not in source and "password" not in source:
                return True

        if "logout" in source:
            return True
        if "atcsobj" in source or "viewport" in source or "openlayers" in source:
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


def try_cookie_login(driver: webdriver.Chrome) -> bool:
    raw_cookie = load_text_cookie()
    pickle_cookies = load_cookie_pickle()

    if raw_cookie:
        add_aspxauth_cookie(driver, raw_cookie)
        driver.get(TF_HOME_URL)
        wait_for_page(driver, 5)
        dismiss_overlays(driver)
        if looks_logged_in(driver):
            save_cookies(driver)
            return True

    if pickle_cookies:
        add_pickle_cookies(driver, pickle_cookies)
        driver.get(TF_HOME_URL)
        wait_for_page(driver, 5)
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
    wait_for_page(driver, 5)
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


def ensure_session(headless: bool = True) -> Tuple[webdriver.Chrome, bool, str]:
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


def _best(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def _looks_like_marker_junk(name: str) -> bool:
    s = (name or "").lower()
    junk_bits = [
        "arrowmarkerssource_",
        "markersource_",
        "regtrainssource_",
        "unregtrainssource_",
        "trainsource_",
    ]
    return any(j in s for j in junk_bits)


def _flatten_features(obj: Any, out: List[Dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        if "features" in obj and isinstance(obj["features"], list):
            for f in obj["features"]:
                if isinstance(f, dict):
                    out.append(f)
        for v in obj.values():
            _flatten_features(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _flatten_features(item, out)


def _parse_geometry(feature: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates")

    if isinstance(coords, list) and len(coords) >= 2:
        lon = _safe_float(coords[0])
        lat = _safe_float(coords[1])

        if lon is not None and lat is not None:
            if abs(lon) <= 180 and abs(lat) <= 90:
                return lat, lon

    props = feature.get("properties") or {}
    lat = _safe_float(_best(props, ["lat", "latitude", "y"]))
    lon = _safe_float(_best(props, ["lon", "lng", "longitude", "x"]))
    return lat, lon


def _build_train_record(feature: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    props = feature.get("properties") or {}
    lat, lon = _parse_geometry(feature)

    if lat is None or lon is None:
        return None

    identifier = _best(
        props,
        [
            "trKey",
            "train_number",
            "trainNumber",
            "trainNo",
            "id",
            "ID",
            "loco",
            "locoNumber",
            "name",
            "train_name",
            "trainName",
        ],
        "",
    )

    loco = _best(props, ["loco", "locoNumber", "loco_number", "engine"], "")
    speed = _safe_float(_best(props, ["speed", "spd", "velocity"], 0)) or 0
    heading = _safe_float(_best(props, ["heading", "bearing", "dir", "direction"], 0)) or 0

    rec = {
        "id": str(identifier or loco or f"{lat},{lon}"),
        "train_number": str(identifier or ""),
        "loco": str(loco or ""),
        "lat": lat,
        "lon": lon,
        "speed": speed,
        "heading": heading,
        "origin": str(_best(props, ["origin", "from", "orig"], "") or ""),
        "destination": str(_best(props, ["destination", "dest", "to"], "") or ""),
        "description": str(_best(props, ["description", "desc", "service"], "") or ""),
        "time": str(_best(props, ["time", "lastUpdated", "updated"], "") or ""),
        "km": str(_best(props, ["km", "kilometres", "kilometers"], "") or ""),
        "raw": props,
    }
    return rec


def scrape_trains_from_page(driver: webdriver.Chrome) -> List[Dict[str, Any]]:
    trains: List[Dict[str, Any]] = []

    script = r"""
const out = [];
try {
  for (const k of Object.keys(window)) {
    try {
      const v = window[k];
      if (!v) continue;
      if (typeof v === 'object') {
        out.push(v);
      }
    } catch (e) {}
  }
} catch (e) {}
return JSON.stringify(out);
"""

    raw_objects = []
    try:
        payload = driver.execute_script(script)
        raw_objects = json.loads(payload)
    except Exception:
        raw_objects = []

    features: List[Dict[str, Any]] = []
    for obj in raw_objects:
        _flatten_features(obj, features)

    dedup: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        rec = _build_train_record(feature)
        if not rec:
            continue

        key = rec["id"]
        if _looks_like_marker_junk(key):
            continue

        if abs(rec["lat"]) > 90 or abs(rec["lon"]) > 180:
            continue

        dedup[key] = rec

    trains = list(dedup.values())
    return trains


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
