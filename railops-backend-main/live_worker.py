import os
import json
import time
import math
import pickle
import random
import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

BASE_MIN_SECONDS = 30
BASE_MAX_SECONDS = 60
MIN_TRAINS_OK = 20
MAX_BACKOFF_SECONDS = 900
LOCK_PATH = Path("/tmp/railops_live.lock")

CHROME_BIN = "/usr/bin/chromium"
CHROMEDRIVER_BIN = "/usr/bin/chromedriver"


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def write_output(trains, note=""):
    payload = {
        "lastUpdated": utc_now(),
        "note": note,
        "trains": trains or []
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"📝 {len(trains)} trains | {note}")


def webmercator_to_latlon(x, y):
    try:
        x = float(x)
        y = float(y)
        lon = (x / 20037508.34) * 180
        lat = (y / 20037508.34) * 180
        lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
        return round(lat, 6), round(lon, 6)
    except:
        return None, None


def make_driver():
    options = Options()
    options.binary_location = CHROME_BIN
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    service = webdriver.ChromeService(executable_path=CHROMEDRIVER_BIN)
    return webdriver.Chrome(service=service, options=options)


def login(driver):
    driver.get(TF_LOGIN_URL)
    time.sleep(3)

    if os.path.exists(COOKIE_FILE):
        cookies = pickle.load(open(COOKIE_FILE, "rb"))
        for c in cookies:
            try:
                driver.add_cookie(c)
            except:
                pass
        driver.refresh()
        time.sleep(3)

    page = driver.page_source.lower()

    if "useR_name".lower() in page:
        print("🔐 Logging in...")
        u = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "useR_name"))
        )
        u.clear()
        u.send_keys(TF_USERNAME)

        p = driver.find_element(By.ID, "pasS_word")
        p.clear()
        p.send_keys(TF_PASSWORD)

        driver.execute_script("document.querySelector('div.button-green')?.click()")
        time.sleep(6)

        pickle.dump(driver.get_cookies(), open(COOKIE_FILE, "wb"))
        print("✅ Cookies saved")


EXTRACT_SCRIPT = """
return (function() {
    let results = [];
    for (let key in window) {
        try {
            let obj = window[key];
            if (obj && obj.getLayers && obj.getView) {
                let layers = obj.getLayers().getArray();
                layers.forEach(layer => {
                    let src = layer.getSource && layer.getSource();
                    if (src && src.getFeatures) {
                        src.getFeatures().forEach(f => {
                            let g = f.getGeometry();
                            if (!g || !g.getCoordinates) return;
                            let coords = g.getCoordinates();
                            let props = f.getProperties();
                            results.push({
                                id: props.id || "",
                                train_number: props.trainNumber || "",
                                loco: props.loco || "",
                                speed_raw: props.trainSpeed || "",
                                x: coords[0],
                                y: coords[1]
                            });
                        });
                    }
                });
            }
        } catch(e){}
    }
    return results;
})();
"""


def extract(driver):
    for _ in range(20):
        raw = driver.execute_script(EXTRACT_SCRIPT)
        if raw and len(raw) > 5:
            return raw
        time.sleep(1)
    return []


def main():
    if LOCK_PATH.exists():
        print("Worker already running.")
        return

    LOCK_PATH.write_text("running")

    backoff = 0
    driver = make_driver()

    try:
        login(driver)

        print("🚦 Live worker started")

        while True:
            try:
                raw = extract(driver)
                trains = []

                for t in raw:
                    lat, lon = webmercator_to_latlon(t["x"], t["y"])
                    if lat and lon:
                        trains.append({
                            "id": t["id"],
                            "train_number": t["train_number"],
                            "loco": t["loco"],
                            "lat": lat,
                            "lon": lon
                        })

                if len(trains) < MIN_TRAINS_OK:
                    backoff = min(MAX_BACKOFF_SECONDS, backoff * 2 or 120)
                    write_output(trains, f"Low train count. Backoff {backoff}s")
                    time.sleep(backoff)
                    driver.refresh()
                    continue

                backoff = 0
                write_output(trains, "OK")
                time.sleep(random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS))

            except Exception as e:
                backoff = min(MAX_BACKOFF_SECONDS, backoff * 2 or 120)
                write_output([], f"Error: {e}")
                time.sleep(backoff)

    finally:
        driver.quit()
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
