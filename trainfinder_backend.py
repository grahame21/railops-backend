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
TF_VIEWPORT_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

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


def get_aspxauth_from_driver(driver: webdriver.Chrome) -> Optional[str]:
    try:
        for c in driver.get_cookies():
            if c.get("name") == ".ASPXAUTH" and c.get("value"):
                return c["value"]
    except Exception:
        pass
    return None


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
        if "nextlevel" in current and "password" not in source:
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


def _iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def _parse_feature_like(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    lat = None
    lon = None

    if isinstance(item.get("geometry"), dict):
        coords = item["geometry"].get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            x = _safe_float(coords[0])
            y = _safe_float(coords[1])
            if x is not None and y is not None:
                if abs(x) > 1000 or abs(y) > 1000:
                    lat, lon = _wm_to_latlon(x, y)
                else:
                    lon, lat = x, y

    if lat is None or lon is None:
        lat = _safe_float(
            item.get("lat")
            or item.get("latitude")
            or item.get("y")
            or item.get("Latitude")
        )
        lon = _safe_float(
            item.get("lon")
            or item.get("lng")
            or item.get("longitude")
            or item.get("x")
            or item.get("Longitude")
        )

    if lat is None or lon is None:
        return None

    if not (-90 < lat < 90 and -180 < lon < 180):
        return None

    if lat < -45 or lat > -8 or lon < 110 or lon > 155:
        return None

    train_number = (
        item.get("trainNumber")
        or item.get("train_number")
        or item.get("ID")
        or item.get("id")
        or ""
    )
    train_name = item.get("trainName") or item.get("train_name") or item.get("name") or ""
    loco = item.get("loco") or item.get("locoNumber") or item.get("loco_number") or ""
    origin = item.get("serviceFrom") or item.get("origin") or item.get("from") or ""
    destination = item.get("serviceTo") or item.get("destination") or item.get("to") or ""
    description = item.get("serviceDesc") or item.get("description") or item.get("service") or ""
    km = item.get("trainKM") or item.get("km") or ""
    train_time = item.get("trainTime") or item.get("time") or ""
    train_date = item.get("trainDate") or item.get("date") or ""
    cid = item.get("cId") or ""
    serv_id = item.get("servId") or ""
    tr_key = item.get("trKey") or ""
    heading = _extract_numeric(item.get("heading") or item.get("bearing") or item.get("dir") or 0, 0)
    speed = _extract_numeric(item.get("trainSpeed") or item.get("speed") or item.get("spd") or 0, 0)

    rec_id = str(tr_key or cid or train_name or train_number or loco or f"{lat:.5f},{lon:.5f}").strip()
    if not rec_id:
        return None

    return {
        "id": rec_id,
        "train_number": str(train_number or ""),
        "train_name": str(train_name or ""),
        "loco": str(loco or ""),
        "speed": speed,
        "heading": heading,
        "origin": str(origin or ""),
        "destination": str(destination or ""),
        "description": str(description or ""),
        "km": str(km or ""),
        "time": str(train_time or ""),
        "date": str(train_date or ""),
        "cId": str(cid or ""),
        "servId": str(serv_id or ""),
        "trKey": str(tr_key or ""),
        "lat": lat,
        "lon": lon,
        "raw": item,
    }


def fetch_viewport_data(driver: webdriver.Chrome, payload: Dict[str, Any]) -> Tuple[Optional[Any], str]:
    script = """
    const done = arguments[arguments.length - 1];
    const payload = arguments[0];

    fetch(arguments[1], {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/plain, */*'
      },
      body: JSON.stringify(payload)
    })
    .then(async (resp) => {
      const text = await resp.text();
      done({
        ok: resp.ok,
        status: resp.status,
        text: text
      });
    })
    .catch((err) => {
      done({
        ok: false,
        status: 0,
        text: String(err)
      });
    });
    """
    try:
        result = driver.execute_async_script(script, payload, TF_VIEWPORT_URL)
        text = result.get("text", "") if isinstance(result, dict) else ""
        if not isinstance(result, dict) or not result.get("ok"):
            return None, text

        try:
            return json.loads(text), text
        except Exception:
            return None, text
    except Exception as e:
        return None, str(e)


def build_au_payloads() -> List[Dict[str, Any]]:
    centers = [
        (-27.0, 133.0, 4),
        (-33.5, 151.0, 6),
        (-37.8, 144.9, 6),
        (-31.95, 115.86, 6),
        (-34.93, 138.60, 6),
        (-27.47, 153.03, 6),
        (-42.88, 147.33, 6),
        (-12.46, 130.84, 6),
    ]

    payloads: List[Dict[str, Any]] = []
    for lat, lng, zm in centers:
        payloads.append(
            {
                "lat": lat,
                "lng": lng,
                "zm": zm,
                "favs": None,
                "alerts": None,
                "places": None,
                "tts": None,
                "webcams": None,
                "atcsGomi": None,
                "atcsObj": None,
            }
        )
    return payloads


def scrape_trains_from_endpoint(driver: webdriver.Chrome) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    debug: Dict[str, Any] = {
        "method": "endpoint",
        "requests": [],
    }

    driver.get(TF_HOME_URL)
    wait_for_page(6)
    dismiss_overlays(driver)

    all_trains: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for payload in build_au_payloads():
        data, raw_text = fetch_viewport_data(driver, payload)

        entry: Dict[str, Any] = {
            "payload": payload,
            "raw_prefix": raw_text[:500] if isinstance(raw_text, str) else "",
            "parsed": isinstance(data, (dict, list)),
            "dict_keys": list(data.keys())[:50] if isinstance(data, dict) else [],
        }

        request_count_before = len(all_trains)

        if data is not None:
            for obj in _iter_dicts(data):
                rec = _parse_feature_like(obj)
                if not rec:
                    continue

                dedup = f"{rec['id']}|{rec['lat']:.5f}|{rec['lon']:.5f}"
                if dedup in seen:
                    continue

                seen.add(dedup)
                all_trains.append(rec)

        entry["new_trains_found"] = len(all_trains) - request_count_before
        debug["requests"].append(entry)

    debug["total_trains_found"] = len(all_trains)
    return all_trains, debug


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
