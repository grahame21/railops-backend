import os, json, time, logging, requests, threading
from flask import Flask, jsonify, send_file

logging.basicConfig(level=getattr(logging, os.getenv("TF_LOG_LEVEL", "INFO").upper(), logging.INFO))

TF_COOKIE  = os.getenv("TF_ASPXAUTH", "").strip()
TF_REFERER = os.getenv("TF_REFERER", "").strip()
TF_UA      = os.getenv("TF_UA", "Mozilla/5.0")

API = "https://trainfinder.otenko.com/Home/GetViewPortData"
DATA_PATH = "/app/trains.json"

S = requests.Session()
S.headers.update({
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "user-agent": TF_UA,
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://trainfinder.otenko.com",
    "referer": TF_REFERER,
})
if TF_COOKIE:
    S.cookies.set(".ASPXAUTH", TF_COOKIE, domain="trainfinder.otenko.com", secure=True)

def warmup_session():
    try:
        r = S.get("https://trainfinder.otenko.com/home/nextlevel", timeout=20)
        logging.info("Warmup GET /home/nextlevel -> %s", r.status_code)
    except Exception as e:
        logging.warning("Warmup failed: %s", e)

def fetch_trains_raw():
    warmup_session()
    r = S.post(API, data=b"", timeout=30)
    logging.info("POST %s -> %s", API, r.status_code)
    try:
        js = r.json()
    except Exception:
        logging.error("Non-JSON: %s", r.text[:500])
        return None
    if not js or (isinstance(js, dict) and all(v is None for v in js.values())):
        logging.warning("Empty/NULL payload. Check zoom/viewport/cookie.")
        return None
    return js

def extract_trains(js):
    if isinstance(js, dict) and "trains" in js:
        return js["trains"]
    if isinstance(js, list):
        return js
    return []

def write_trains(path=DATA_PATH):
    js = fetch_trains_raw()
    trains = extract_trains(js) if js is not None else []
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trains, f, ensure_ascii=False)
    logging.info("wrote %s with %d trains", path, len(trains))
    return trains

app = Flask(__name__)

@app.get("/")
def root():
    return {"ok": True, "hint": "GET /trains.json, GET /debug, POST /fetch-now"}

@app.get("/trains.json")
def serve_trains():
    if not os.path.exists(DATA_PATH):
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
    return send_file(DATA_PATH, mimetype="application/json")

@app.get("/debug")
def debug():
    return jsonify({
        "referer": TF_REFERER,
        "ua": TF_UA,
        "cookie_len": len(TF_COOKIE),
        "has_cookie": bool(TF_COOKIE),
    })

@app.post("/fetch-now")
def fetch_now():
    trains = write_trains(DATA_PATH)
    return {"ok": True, "count": len(trains)}

def refresher():
    time.sleep(5)
    while True:
        try:
            write_trains(DATA_PATH)
        except Exception as e:
            logging.exception("refresh failed: %s", e)
        time.sleep(30)

if os.getenv("ENABLE_REFRESH", "1") == "1":
    threading.Thread(target=refresher, daemon=True).start()