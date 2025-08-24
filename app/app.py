import os, json, time, logging, threading, requests
from flask import Flask, jsonify, send_file

# Logging
logging.basicConfig(level=getattr(logging, os.getenv("TF_LOG_LEVEL", "INFO").upper(), logging.INFO))
log = logging.getLogger("railops")

# ENV from Render (set these in the dashboard)
TF_COOKIE  = os.getenv("TF_ASPXAUTH", "").strip()   # ONLY the value, not ".ASPXAUTH=<...>"
TF_REFERER = os.getenv("TF_REFERER", "").strip()    # e.g. https://trainfinder.otenko.com/home/nextlevel?lat=-34.93&lng=138.60&zm=7
TF_UA      = os.getenv("TF_UA", "Mozilla/5.0").strip()

DATA_PATH = "/app/trains.json"
API_WARM  = "https://trainfinder.otenko.com/home/nextlevel"
API_POST  = "https://trainfinder.otenko.com/Home/GetViewPortData"

# HTTP session setup
S = requests.Session()
S.headers.update({
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "user-agent": TF_UA or "Mozilla/5.0",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://trainfinder.otenko.com",
    "referer": TF_REFERER,
})
if TF_COOKIE:
    # IMPORTANT: cookie NAME is .ASPXAUTH; env contains ONLY the VALUE
    S.cookies.set(".ASPXAUTH", TF_COOKIE, domain="trainfinder.otenko.com", secure=True)

def warmup():
    try:
        r = S.get(API_WARM, timeout=20)
        log.info("Warmup GET -> %s", r.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

def fetch_raw():
    warmup()
    try:
        r = S.post(API_POST, data=b"", timeout=30)  # mirrors the browser empty POST
        log.info("POST %s -> %s", API_POST, r.status_code)
        try:
            js = r.json()
        except Exception:
            log.error("Non-JSON response: %s", r.text[:500])
            return None
        # Common empty case when cookie/referer/zoom are wrong:
        if not js or (isinstance(js, dict) and all(v is None for v in js.values())):
            log.warning("Empty/NULL payload. Check TF_ASPXAUTH / TF_REFERER (zoom/viewport).")
            return None
        return js
    except Exception as e:
        log.exception("fetch_raw error: %s", e)
        return None

def extract_trains(js):
    """Adjust this once you know TrainFinder's exact schema."""
    if isinstance(js, dict) and "trains" in js:
        return js["trains"]
    if isinstance(js, list):
        return js
    return []

def write_trains():
    js = fetch_raw()
    trains = extract_trains(js) if js is not None else []
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(trains, f, ensure_ascii=False)
        log.info("wrote %s with %d trains", DATA_PATH, len(trains))
    except Exception as e:
        log.exception("Failed to write trains.json: %s", e)
    return trains

# Flask app & routes
app = Flask(__name__)

@app.get("/")
def root():
    return jsonify({"ok": True, "hint": "GET /trains.json, GET /debug, POST /fetch-now"})

@app.get("/debug")
def debug():
    return jsonify({
        "has_cookie": bool(TF_COOKIE),
        "cookie_len": len(TF_COOKIE),
        "referer": TF_REFERER,
        "ua": TF_UA,
    })

@app.post("/fetch-now")
def fetch_now():
    trains = write_trains()
    return {"ok": True, "count": len(trains)}

@app.get("/trains.json")
def serve_trains():
    if not os.path.exists(DATA_PATH):
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
    return send_file(DATA_PATH, mimetype="application/json")

# Optional background refresher (every 30s). Disable with ENABLE_REFRESH=0
def refresher():
    time.sleep(5)
    while True:
        try:
            write_trains()
        except Exception as e:
            log.exception("refresher error: %s", e)
        time.sleep(30)

if os.getenv("ENABLE_REFRESH", "1") == "1":
    threading.Thread(target=refresher, daemon=True).start()