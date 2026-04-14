import json
import math
import os
import random
import tempfile
import time
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from trainfinder_backend import ensure_session, scrape_trains_from_page


TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

BASE_MIN_SECONDS = 30
BASE_MAX_SECONDS = 60
MIN_TRAINS_OK = 200
MAX_BACKOFF_SECONDS = 900
LOCK_PATH = Path("/tmp/railops_live.lock")
DEBUG_SOURCES_FILE = "debug_sources.json"

CHROME_BIN = "/usr/bin/chromium"
CHROMEDRIVER_BIN = "/usr/bin/chromedriver"


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(target.parent)) as tmp:
        json.dump(payload, tmp, indent=2, ensure_ascii=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name

    os.replace(tmp_name, target)


def load_existing_payload(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"lastUpdated": None, "note": "no existing file", "trains": []}


def write_output(
    trains: List[Dict[str, Any]],
    note: str,
    preserve_existing_if_too_small: bool = True,
    min_trains_ok: int = MIN_TRAINS_OK,
) -> Dict[str, Any]:
    existing = load_existing_payload(OUT_FILE)
    existing_trains = existing.get("trains", [])
    existing_count = len(existing_trains) if isinstance(existing_trains, list) else 0

    use_existing = (
        preserve_existing_if_too_small
        and len(trains) < min_trains_ok
        and existing_count >= min_trains_ok
    )

    if use_existing:
        payload = {
            "lastUpdated": existing.get("lastUpdated"),
            "note": f"{note} | keeping last good ({existing_count} trains)",
            "trains": existing_trains,
        }
        atomic_write_json(OUT_FILE, payload)
        print(f"🛟 Keeping last good data: {existing_count} trains | reason: {note}")
        return payload

    payload = {
        "lastUpdated": utc_now(),
        "note": note,
        "trains": trains or [],
    }
    atomic_write_json(OUT_FILE, payload)
    print(f"📝 Wrote {len(trains)} trains | {note}")
    return payload


def webmercator_to_latlon(x: Any, y: Any) -> Tuple[Optional[float], Optional[float]]:
    try:
        x = float(x)
        y = float(y)
        lon = (x / 20037508.34) * 180.0
        lat = (y / 20037508.34) * 180.0
        lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


def make_driver() -> webdriver.Chrome:
    options = Options()
    options.binary_location = CHROME_BIN
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")

    service = webdriver.ChromeService(executable_path=CHROMEDRIVER_BIN)
    return webdriver.Chrome(service=service, options=options)


EXTRACT_SCRIPT = r"""
return (function() {
    const results = [];
    const sourceInfo = [];

    function pick(obj, keys) {
        for (const k of keys) {
            if (obj && obj[k] !== undefined && obj[k] !== null && obj[k] !== "") return obj[k];
        }
        return "";
    }

    for (const key in window) {
        try {
            const obj = window[key];
            if (!obj || !obj.getLayers || !obj.getView) continue;

            const layers = obj.getLayers().getArray();
            layers.forEach((layer, idx) => {
                let src = null;
                try { src = layer.getSource && layer.getSource(); } catch(e) {}
                if (!src || !src.getFeatures) return;

                const features = src.getFeatures() || [];
                let sourceName = "";
                try { sourceName = src.get && src.get("name") || ""; } catch(e) {}

                sourceInfo.push({
                    layerIndex: idx,
                    sourceName: sourceName || "",
                    count: features.length
                });

                features.forEach(f => {
                    try {
                        const g = f.getGeometry && f.getGeometry();
                        if (!g || !g.getCoordinates) return;

                        const coords = g.getCoordinates();
                        const props = f.getProperties ? f.getProperties() : {};

                        results.push({
                            id: pick(props, ["id", "ID", "trainId", "train_id"]),
                            train_number: pick(props, ["trainNumber", "train_number", "serviceNumber", "service_number"]),
                            loco: pick(props, ["loco", "trKey", "trainName", "train_name", "vehicle_number"]),
                            speed: pick(props, ["trainSpeed", "speed", "kph", "kmh"]),
                            operator: pick(props, ["operator", "current_operator", "operatorName", "currentOperator"]),
                            description: pick(props, ["description", "vehicle_description", "serviceDesc", "line_name", "route_name"]),
                            origin: pick(props, ["origin", "from", "serviceFrom"]),
                            destination: pick(props, ["destination", "to", "serviceTo"]),
                            location: pick(props, ["location", "current_location", "place", "town", "suburb", "city"]),
                            x: coords[0],
                            y: coords[1]
                        });
                    } catch (e) {}
                });
            });
        } catch (e) {}
    }

    return { results, sourceInfo };
})();
"""


def normalize_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except Exception:
        return default


def clean_text(v: Any) -> str:
    return str(v or "").strip()


def dedupe_trains(trains: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []

    for t in trains:
        lat = t.get("lat")
        lon = t.get("lon")
        key = (
            clean_text(t.get("id")),
            clean_text(t.get("train_number")),
            clean_text(t.get("loco")),
            lat,
            lon,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(t)

    return out


def filter_reasonable_trains(trains: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []

    for t in trains:
        try:
            lat = float(t.get("lat"))
            lon = float(t.get("lon"))
        except Exception:
            continue

        if not (-45.0 <= lat <= -8.0 and 110.0 <= lon <= 155.5):
            continue

        train_id = clean_text(t.get("id"))
        train_number = clean_text(t.get("train_number"))
        loco = clean_text(t.get("loco"))

        if not (train_id or train_number or loco):
            continue

        cleaned.append(t)

    return dedupe_trains(cleaned)


def scrape_with_backend(driver: webdriver.Chrome) -> List[Dict[str, Any]]:
    trains = scrape_trains_from_page(driver) or []
    if not isinstance(trains, list):
        return []

    out: List[Dict[str, Any]] = []
    for t in trains:
        try:
            lat = float(t.get("lat"))
            lon = float(t.get("lon"))
        except Exception:
            continue

        out.append(
            {
                "id": clean_text(t.get("id") or t.get("ID") or t.get("train_id") or t.get("trainId")),
                "train_number": clean_text(t.get("train_number") or t.get("trainNumber") or t.get("service_number") or t.get("serviceNumber")),
                "loco": clean_text(t.get("loco") or t.get("trKey") or t.get("train_name") or t.get("trainName")),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "speed": normalize_int(t.get("speed") or t.get("kph") or t.get("kmh")),
                "operator": clean_text(
                    t.get("operator")
                    or t.get("current_operator")
                    or t.get("operator_name")
                    or t.get("currentOperator")
                ),
                "description": clean_text(
                    t.get("description")
                    or t.get("vehicle_description")
                    or t.get("serviceDesc")
                    or t.get("line_name")
                    or t.get("route_name")
                ),
                "origin": clean_text(t.get("origin") or t.get("from") or t.get("serviceFrom")),
                "destination": clean_text(t.get("destination") or t.get("to") or t.get("serviceTo")),
                "location": clean_text(
                    t.get("location")
                    or t.get("current_location")
                    or t.get("place")
                    or t.get("town")
                    or t.get("suburb")
                    or t.get("city")
                ),
            }
        )

    return filter_reasonable_trains(out)


def scrape_with_js(driver: webdriver.Chrome) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    debug: Dict[str, Any] = {
        "method": "js_extract",
        "sourceInfo": [],
        "rawCount": 0,
        "keptCount": 0,
    }

    for _ in range(20):
        blob = driver.execute_script(EXTRACT_SCRIPT) or {}
        raw = blob.get("results") or []
        source_info = blob.get("sourceInfo") or []

        debug["sourceInfo"] = source_info
        debug["rawCount"] = len(raw)

        if raw and len(raw) > 5:
            trains: List[Dict[str, Any]] = []
            for t in raw:
                lat, lon = webmercator_to_latlon(t.get("x"), t.get("y"))
                if lat is None or lon is None:
                    continue

                trains.append(
                    {
                        "id": clean_text(t.get("id")),
                        "train_number": clean_text(t.get("train_number")),
                        "loco": clean_text(t.get("loco")),
                        "lat": lat,
                        "lon": lon,
                        "speed": normalize_int(t.get("speed")),
                        "operator": clean_text(t.get("operator")),
                        "description": clean_text(t.get("description")),
                        "origin": clean_text(t.get("origin")),
                        "destination": clean_text(t.get("destination")),
                        "location": clean_text(t.get("location")),
                    }
                )

            trains = filter_reasonable_trains(trains)
            debug["keptCount"] = len(trains)
            return trains, debug

        time.sleep(1)

    return [], debug


def save_debug_info(debug: Dict[str, Any]) -> None:
    try:
        atomic_write_json(DEBUG_SOURCES_FILE, debug)
    except Exception as e:
        print(f"Could not write debug info: {e}")


def scrape_once(driver: webdriver.Chrome) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    debug: Dict[str, Any] = {"attempted": []}

    try:
        trains = scrape_with_backend(driver)
        debug["attempted"].append({"method": "backend", "count": len(trains)})
        if len(trains) >= MIN_TRAINS_OK:
            debug["chosen"] = "backend"
            debug["finalCount"] = len(trains)
            return trains, f"ok - {len(trains)} trains", debug
    except Exception as e:
        debug["attempted"].append({"method": "backend", "error": str(e)})

    try:
        trains, js_debug = scrape_with_js(driver)
        debug["attempted"].append({"method": "js_extract", "count": len(trains)})
        debug["js"] = js_debug
        if len(trains) >= MIN_TRAINS_OK:
            debug["chosen"] = "js_extract"
            debug["finalCount"] = len(trains)
            return trains, f"ok - {len(trains)} trains", debug
    except Exception as e:
        debug["attempted"].append({"method": "js_extract", "error": str(e)})

    debug["chosen"] = "none"
    debug["finalCount"] = 0
    return [], "low train count / scrape failed", debug


def lock_exists_and_is_live() -> bool:
    if not LOCK_PATH.exists():
        return False

    try:
        pid_text = LOCK_PATH.read_text().strip()
        pid = int(pid_text)
        os.kill(pid, 0)
        return True
    except Exception:
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def acquire_lock() -> bool:
    if lock_exists_and_is_live():
        return False

    LOCK_PATH.write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def main() -> None:
    if not acquire_lock():
        print("Worker already running.")
        return

    driver: Optional[webdriver.Chrome] = None
    backoff = 0

    try:
        driver, ok, msg = ensure_session(headless=True)
        print(msg)

        if not ok or driver is None:
            raise RuntimeError(f"Could not start session: {msg}")

        print("🚦 Live worker started")

        while True:
            try:
                trains, note, debug = scrape_once(driver)
                save_debug_info(debug)

                if len(trains) < MIN_TRAINS_OK:
                    backoff = min(MAX_BACKOFF_SECONDS, backoff * 2 or 120)
                    write_output(
                        trains,
                        note=f"{note}. Backoff {backoff}s",
                        preserve_existing_if_too_small=True,
                    )
                    print(f"⚠️ Low count/backoff: sleeping {backoff}s")
                    time.sleep(backoff)

                    try:
                        driver.refresh()
                    except Exception:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver, ok, msg = ensure_session(headless=True)
                        print(msg)
                        if not ok or driver is None:
                            raise RuntimeError(f"Could not re-establish session: {msg}")
                    continue

                backoff = 0
                write_output(trains, note=note, preserve_existing_if_too_small=False)

                sleep_for = random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS)
                print(f"😴 Sleeping {sleep_for}s")
                time.sleep(sleep_for)

            except Exception as e:
                backoff = min(MAX_BACKOFF_SECONDS, backoff * 2 or 120)
                print(f"❌ Worker error: {e}")

                write_output(
                    [],
                    note=f"error: {e}. Backoff {backoff}s",
                    preserve_existing_if_too_small=True,
                )

                time.sleep(backoff)

                try:
                    if driver is not None:
                        driver.quit()
                except Exception:
                    pass

                driver, ok, msg = ensure_session(headless=True)
                print(msg)
                if not ok or driver is None:
                    print("⚠️ Session recovery failed, will retry next loop")

    finally:
        try:
            if driver is not None:
                driver.quit()
        except Exception:
            pass
        release_lock()


if __name__ == "__main__":
    main()
