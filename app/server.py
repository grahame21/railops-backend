import os, time, json, threading, logging, requests
from datetime import datetime, timezone
from flask import Flask, jsonify, make_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ASPXAUTH = os.getenv("ASPXAUTH","").strip()
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS","60"))
PROXY_URL = os.getenv("PROXY_URL","").strip()
REFERER = os.getenv("TRAINFINDER_REFERER","https://trainfinder.otenko.com/home/nextlevel?zm=7&bbox=110.0,-45.0,155.0,-10.0").strip()

proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
session = requests.Session()

latest_payload = {"status":"starting"}
last_updated = None
lock = threading.Lock()

def fetch_trainfinder():
    if not ASPXAUTH:
        raise RuntimeError("ASPXAUTH env var is not set")
    headers = {
        "accept": "*/*",
        "x-requested-with": "XMLHttpRequest",
        "referer": REFERER,
        "origin": "https://trainfinder.otenko.com",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    }
    cookies = {".ASPXAUTH": ASPXAUTH}
    r = session.post("https://trainfinder.otenko.com/Home/GetViewPortData",
                     headers=headers, cookies=cookies, data=b"", proxies=proxies, timeout=30)
    logging.info("TrainFinder HTTP %s", r.status_code)
    r.raise_for_status()
    data = r.json()
    if data is None or (isinstance(data, dict) and all(v is None for v in data.values())):
        raise RuntimeError("Null payload. Adjust TRAINFINDER_REFERER (zm ~6–7 & bbox).")
    return data

def background_loop():
    global latest_payload, last_updated
    while True:
        try:
            data = fetch_trainfinder()
            with lock:
                latest_payload = data
                last_updated = datetime.now(timezone.utc).isoformat()
            logging.info("Updated trains.json (%s)", last_updated)
        except Exception as e:
            logging.error("Fetch cycle error: %s", e)
        time.sleep(UPDATE_INTERVAL_SECONDS)

app = Flask(__name__)

@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.route("/")
def health():
    with lock:
        return jsonify({"ok": True, "last_updated": last_updated})

@app.route("/trains.json")
def trains():
    with lock:
        resp = make_response(json.dumps(latest_payload, ensure_ascii=False, separators=(",",":")))
    resp.mimetype = "application/json"
    return resp

threading.Thread(target=background_loop, daemon=True).start()
