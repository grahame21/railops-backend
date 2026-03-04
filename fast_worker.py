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

OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "trainfinder_cookies.pkl")
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

PUSH_URL = os.environ.get("PUSH_URL", "")
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "")

CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")

BASE_MIN_SECONDS = 12
BASE_MAX_SECONDS = 20

STOP = False

# IMPORTANT: Only capture the real train API
KEYWORDS = ("getviewportdata", "viewportdata", "viewport")

def handle_stop(sig, frame):
    global STOP
    STOP = True

signal.signal(signal.SIGINT, handle_stop)
signal.signal(signal.SIGTERM, handle_stop)

def utc_now_z():
    return datetime.datetime.utcnow().isoformat() + "Z"

def build_payload(trains, note):
    return {
        "lastUpdated": utc_now_z(),
        "note": note,
        "trains": trains or []
    }

def write_local(payload):
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except:
        pass

def push_to_web(payload):
    if not PUSH_URL or not PUSH_TOKEN:
        return
    try:
        requests.post(
            PUSH_URL,
            json=payload,
            headers={"X-Auth-Token": PUSH_TOKEN},
            timeout=15
        )
    except:
        pass

def webmercator_to_latlon(x, y):
    try:
        x = float(x)
        y = float(y)

        lon = (x / 20037508.34) * 180
        lat = (y / 20037508.34) * 180
        lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)

        return round(lat,6), round(lon,6)
    except:
        return None,None

def make_driver():
    chrome_options = Options()
    chrome_options.binary_location = CHROME_BIN

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    service = webdriver.ChromeService(executable_path=CHROMEDRIVER_BIN)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.execute_cdp_cmd("Network.enable", {})

    return driver

def safe_get(driver, url):
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except:
            pass

def login(driver):

    safe_get(driver, TF_LOGIN_URL)
    time.sleep(6)

    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE,"rb") as f:
                cookies = pickle.load(f)
            for c in cookies:
                try:
                    driver.add_cookie(c)
                except:
                    pass
            safe_get(driver, TF_LOGIN_URL)
            time.sleep(4)
            print("✅ Loaded saved cookies")
        except:
            pass

    try:
        username = driver.find_element(By.CSS_SELECTOR,"input[type='email'],input[type='text']")
        password = driver.find_element(By.CSS_SELECTOR,"input[type='password']")
    except:
        print("Already logged in")
        return

    print("🔐 Logging in")

    username.clear()
    username.send_keys(TF_USERNAME)

    password.clear()
    password.send_keys(TF_PASSWORD)
    password.send_keys("\n")

    time.sleep(8)

    try:
        with open(COOKIE_FILE,"wb") as f:
            pickle.dump(driver.get_cookies(),f)
        print("✅ Cookies saved")
    except:
        pass

def read_network_candidate(driver):

    try:
        logs = driver.get_log("performance")
    except:
        return None

    for entry in reversed(logs):

        try:
            msg = json.loads(entry["message"])["message"]
            if msg.get("method") != "Network.requestWillBeSent":
                continue

            req = msg["params"]["request"]
            url = req.get("url","").lower()

            if not any(k in url for k in KEYWORDS):
                continue

            method = req.get("method","GET")
            body = req.get("postData")

            print("Captured:",url)

            return {
                "url":req.get("url"),
                "method":method,
                "body":body
            }

        except:
            continue

    return None

def replay(driver, req):

    script = """
    const cb = arguments[arguments.length-1];

    fetch(arguments[0],{
      method:arguments[1],
      headers:{
        'Accept':'application/json',
        'Content-Type':'application/json;charset=UTF-8',
        'X-Requested-With':'XMLHttpRequest'
      },
      body:arguments[2],
      credentials:'include'
    })
    .then(r=>r.text())
    .then(t=>cb({ok:true,text:t}))
    .catch(e=>cb({ok:false,err:String(e)}));
    """

    return driver.execute_async_script(script,req["url"],req["method"],req["body"])

def extract_trains(data):

    trains=[]
    stack=[data]

    while stack:

        obj=stack.pop()

        if isinstance(obj,dict):

            if "x" in obj and "y" in obj:
                lat,lon = webmercator_to_latlon(obj["x"],obj["y"])
                if lat and lon:
                    trains.append({
                        "lat":lat,
                        "lon":lon,
                        "id":obj.get("id","")
                    })

            for v in obj.values():
                stack.append(v)

        elif isinstance(obj,list):
            stack.extend(obj)

    return trains

def main():

    print("🚂 RailOps worker starting")

    driver = make_driver()

    login(driver)

    print("⏳ Waiting for TrainFinder map JS...")
    time.sleep(25)

    captured=None

    while not STOP:

        if not captured:

            captured = read_network_candidate(driver)

            if not captured:
                print("Waiting for viewport request...")
                time.sleep(5)
                continue

        res = replay(driver,captured)

        if not res["ok"]:
            print("Replay failed")
            time.sleep(10)
            continue

        try:
            data = json.loads(res["text"])
        except:
            print("Not JSON")
            time.sleep(10)
            continue

        trains = extract_trains(data)

        payload = build_payload(trains,"OK")

        write_local(payload)
        push_to_web(payload)

        print("Trains:",len(trains))

        time.sleep(random.randint(BASE_MIN_SECONDS,BASE_MAX_SECONDS))


if __name__=="__main__":
    main()
