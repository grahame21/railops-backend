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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
COOKIE_PKL = "trainfinder_cookies.pkl"
COOKIE_TXT = "cookie.txt"

MAP_STABILIZE_SECONDS = 12
POST_ZOOM_WAIT_SECONDS = 8
SOURCE_POLL_ATTEMPTS = 18
SOURCE_POLL_INTERVAL = 5
PAGE_REFRESH_ATTEMPTS = 2


def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


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
    try:
        cookies = driver.get_cookies()
        with open(COOKIE_PKL, "wb") as f:
            pickle.dump(cookies, f)
        aspxauth = get_aspxauth_from_driver(driver)
        if aspxauth:
            save_text_cookie(aspxauth)
    except Exception:
        pass


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


def write_trains_json(
    trains: List[Dict[str, Any]],
    out_file: str = "trains.json",
    note: str = "ok",
    preserve_existing_if_empty: bool = True,
) -> Dict[str, Any]:
    payload = {
        "lastUpdated": now_utc_iso(),
        "note": f"{note} - {len(trains)} trains",
        "trains": trains or [],
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
                    json.dump(old, f, ensure_ascii=False, indent=2)
                return old
        except Exception:
            pass

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def write_debug_json(debug: Dict[str, Any], out_file: str = "debug_sources.json") -> None:
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(debug, f, ensure_ascii=False, indent=2)


def webmercator_to_latlon(x: Any, y: Any) -> Tuple[Optional[float], Optional[float]]:
    try:
        x = float(x)
        y = float(y)
        lon = (x / 20037508.34) * 180
        lat = (y / 20037508.34) * 180
        lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


def make_driver(headless: bool = True) -> webdriver.Chrome:
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=en-AU")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(90)

    try:
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
    except Exception:
        pass

    return driver


def _add_cookie_pickle_to_browser(driver: webdriver.Chrome, cookies: List[Dict[str, Any]]) -> bool:
    if not cookies:
        return False

    try:
        driver.get("https://trainfinder.otenko.com/")
        time.sleep(2)

        added = False
        for cookie in cookies:
            try:
                c = dict(cookie)
                c.pop("sameSite", None)
                if c.get("expiry") is None:
                    c.pop("expiry", None)
                if "domain" not in c or not c["domain"]:
                    c["domain"] = "trainfinder.otenko.com"
                if "path" not in c or not c["path"]:
                    c["path"] = "/"
                driver.add_cookie(c)
                added = True
            except Exception:
                continue
        return added
    except Exception:
        return False


def _add_aspxauth_to_browser(driver: webdriver.Chrome, cookie_value: str) -> bool:
    cookie_value = (cookie_value or "").strip()
    if not cookie_value:
        return False

    try:
        driver.get("https://trainfinder.otenko.com/")
        time.sleep(2)
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


def dismiss_warning(driver: webdriver.Chrome) -> None:
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
                    if (parent) {
                        parent.click();
                    }
                }
            }
            """
        )
        time.sleep(2)
    except Exception:
        pass


def _looks_logged_in(driver: webdriver.Chrome) -> bool:
    try:
        url = (driver.current_url or "").lower()
        src = (driver.page_source or "").lower()

        if "user_name" in src or "pass_word" in src or "useR_name".lower() in src or "pasS_word".lower() in src:
            return False
        if "returnurl=" in url:
            return False

        cookies_json = json.dumps(driver.get_cookies()).lower()
        if ".aspxauth" in cookies_json:
            return True

        return "nextlevel" in url and "password" not in src
    except Exception:
        return False


def ensure_session(
    headless: bool = True,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[webdriver.Chrome, bool, str]:
    username = (username or os.environ.get("TF_USERNAME", "")).strip()
    password = (password or os.environ.get("TF_PASSWORD", "")).strip()

    driver = make_driver(headless=headless)

    try:
        driver.get(TF_LOGIN_URL)
        time.sleep(5)

        raw_cookie = load_text_cookie()
        if raw_cookie:
            _add_aspxauth_to_browser(driver, raw_cookie)
            driver.get(TF_LOGIN_URL)
            time.sleep(4)
            dismiss_warning(driver)
            if _looks_logged_in(driver):
                save_cookies(driver)
                return driver, True, "cookie login ok"

        pickle_cookies = load_cookie_pickle()
        if pickle_cookies:
            _add_cookie_pickle_to_browser(driver, pickle_cookies)
            driver.get(TF_LOGIN_URL)
            time.sleep(4)
            dismiss_warning(driver)
            if _looks_logged_in(driver):
                save_cookies(driver)
                return driver, True, "cookie login ok"

        username_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        password_box = driver.find_element(By.ID, "pasS_word")

        if not username or not password:
            return driver, False, "missing credentials"

        username_box.clear()
        username_box.send_keys(username)
        password_box.clear()
        password_box.send_keys(password)

        driver.execute_script(
            """
            var buttons = document.querySelectorAll('input[type="button"], button');
            for (var i = 0; i < buttons.length; i++) {
                var value = buttons[i].value || '';
                var text = buttons[i].textContent || '';
                if (value === 'Log In' || text.includes('Log In')) {
                    buttons[i].click();
                    return true;
                }
            }
            return false;
            """
        )

        time.sleep(6)
        dismiss_warning(driver)
        save_cookies(driver)

        if _looks_logged_in(driver):
            return driver, True, "password login ok"

        return driver, False, "could not establish TrainFinder session"
    except Exception as e:
        return driver, False, f"session error: {type(e).__name__}: {e}"


def _zoom_to_australia(driver: webdriver.Chrome) -> None:
    try:
        driver.execute_script(
            """
            if (window.map && window.ol) {
                var australia = [112, -44, 154, -10];
                var proj = window.map.getView().getProjection();
                var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                window.map.getView().fit(extent, { duration: 2000, maxZoom: 8 });
            }
            """
        )
    except Exception:
        pass


def _collect_page_sources(driver: webdriver.Chrome) -> Dict[str, Any]:
    script = r"""
    var allTrains = [];
    var sourceStats = [];
    var sources = [
        'regTrainsSource',
        'unregTrainsSource',
        'markerSource',
        'arrowMarkersSource',
        'trainSource',
        'trainMarkers'
    ];

    sources.forEach(function(sourceName) {
        var source = window[sourceName];
        if (!source || !source.getFeatures) {
            sourceStats.push({ name: sourceName, exists: false, count: 0 });
            return;
        }

        var features = source.getFeatures() || [];
        sourceStats.push({ name: sourceName, exists: true, count: features.length });

        features.forEach(function(feature, idx) {
            try {
                var props = feature.getProperties ? feature.getProperties() : {};
                var geom = feature.getGeometry ? feature.getGeometry() : null;

                if (!geom || geom.getType() !== 'Point') return;

                var coords = geom.getCoordinates();
                if (!coords || coords.length < 2) return;

                var speed = 0;
                if (props.trainSpeed) {
                    var match = String(props.trainSpeed).match(/(\d+)/);
                    if (match) speed = parseInt(match[0]);
                }

                allTrains.push({
                    id: props.id || props.ID || props.trKey || props.cId || (sourceName + '_' + idx),
                    train_number: props.trainNumber || props.train_number || '',
                    train_name: props.trainName || props.train_name || '',
                    service_name: props.serviceName || '',
                    loco: props.loco || '',
                    operator: props.operator || '',
                    origin: props.serviceFrom || props.origin || '',
                    destination: props.serviceTo || props.destination || '',
                    speed: speed,
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
            } catch (e) {}
        });
    });

    return {
        allTrains: allTrains,
        sourceStats: sourceStats,
        hasMap: !!window.map,
        hasOl: !!window.ol,
        title: document.title || '',
        url: window.location.href || ''
    };
    """
    result = driver.execute_script(script)
    return result if isinstance(result, dict) else {}


def _poll_for_live_sources(driver: webdriver.Chrome) -> Dict[str, Any]:
    last_result: Dict[str, Any] = {}

    for attempt in range(1, SOURCE_POLL_ATTEMPTS + 1):
        result = _collect_page_sources(driver)
        raw_trains = result.get("allTrains", []) if isinstance(result, dict) else []
        source_stats = result.get("sourceStats", []) if isinstance(result, dict) else []

        total_source_count = 0
        for src in source_stats:
            try:
                total_source_count += int(src.get("count") or 0)
            except Exception:
                pass

        result["raw_count"] = len(raw_trains)
        result["source_total_count"] = total_source_count
        result["poll_attempt"] = attempt

        print(
            f"🔎 Poll {attempt}/{SOURCE_POLL_ATTEMPTS}: "
            f"raw={len(raw_trains)} source_total={total_source_count}",
            flush=True
        )

        last_result = result

        if len(raw_trains) > 0 or total_source_count > 0:
            return result

        time.sleep(SOURCE_POLL_INTERVAL)

    return last_result


def _filter_au_trains(raw_trains: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    trains: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for t in raw_trains:
        lat, lon = webmercator_to_latlon(t.get("x"), t.get("y"))
        if lat is None or lon is None:
            continue
        if not (-45 <= lat <= -9 and 110 <= lon <= 155):
            continue

        rec = {
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

        dedup = f"{rec['id']}|{rec['lat']:.5f}|{rec['lon']:.5f}"
        if dedup in seen:
            continue
        seen.add(dedup)
        trains.append(rec)

    return trains


def scrape_trains_from_page(driver: webdriver.Chrome) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    debug: Dict[str, Any] = {
        "method": "page_sources",
        "sources_found": [],
        "raw_count": 0,
        "au_count": 0,
        "refresh_attempts_used": 0,
    }

    final_raw_trains: List[Dict[str, Any]] = []
    final_result: Dict[str, Any] = {}

    for refresh_attempt in range(1, PAGE_REFRESH_ATTEMPTS + 1):
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        dismiss_warning(driver)

        debug["url_after_open"] = driver.current_url

        print(f"\n⏳ Waiting {MAP_STABILIZE_SECONDS} seconds for map to stabilize...")
        time.sleep(MAP_STABILIZE_SECONDS)

        print("🌏 Zooming to Australia...")
        _zoom_to_australia(driver)

        print(f"⏳ Waiting {POST_ZOOM_WAIT_SECONDS} seconds after zoom...")
        time.sleep(POST_ZOOM_WAIT_SECONDS)

        result = _poll_for_live_sources(driver)
        raw_trains = result.get("allTrains", []) if isinstance(result, dict) else []
        source_stats = result.get("sourceStats", []) if isinstance(result, dict) else []

        final_result = result
        final_raw_trains = raw_trains

        debug["refresh_attempts_used"] = refresh_attempt
        debug["sources_found"] = source_stats
        debug["hasMap"] = result.get("hasMap", False)
        debug["hasOl"] = result.get("hasOl", False)
        debug["page_title"] = result.get("title", "")
        debug["page_url"] = result.get("url", "")
        debug["raw_count"] = len(raw_trains)
        debug["source_total_count"] = result.get("source_total_count", 0)
        debug["poll_attempt"] = result.get("poll_attempt", 0)

        au_trains = _filter_au_trains(raw_trains)
        debug["au_count"] = len(au_trains)

        if au_trains:
            if au_trains:
                debug["sample"] = au_trains[0]
            return au_trains, debug

        if refresh_attempt < PAGE_REFRESH_ATTEMPTS:
            print(f"⚠️ No AU trains found after refresh attempt {refresh_attempt}. Refreshing page and retrying...")
            try:
                driver.refresh()
            except Exception:
                pass
            time.sleep(6)

    final_au_trains = _filter_au_trains(final_raw_trains)
    debug["au_count"] = len(final_au_trains)
    if final_au_trains:
        debug["sample"] = final_au_trains[0]

    return final_au_trains, debug
