import os, json, time, logging, threading, requests
from flask import Flask, jsonify, send_file

# ---------- Logging ----------
logging.basicConfig(
    level=getattr(logging, os.getenv("TF_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("railops")

# ---------- Env vars (set these in Render → Environment) ----------
TF_COOKIE  = os.getenv("TF_ASPXAUTH", "").strip()   # ONLY the value, not ".ASPXAUTH=<...>"
TF_REFERER = os.getenv("TF_REFERER", "").strip()    # e.g. https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=7
TF_UA      = os.getenv("TF_UA", "Mozilla/5.0").strip()

DATA_PATH = "/app/trains.json"
API_WARM  = TF_REFERER or "https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=7"
API_POST  = "https://trainfinder.otenko.com/Home/GetViewPortData"

# ---------- HTTP session (looks like a real browser) ----------
S = requests.Session()
S.headers.update({
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "user-agent": TF_UA or "Mozilla/5.0",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://trainfinder.otenko.com",
    "referer": TF_REFERER or API_WARM,
    # Step 3 additions:
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "dnt": "1",
})
if TF_COOKIE:
    # EXACT cookie name expected by the site; env contains ONLY the value
    S.cookies.set(".ASPXAUTH", TF_COOKIE, domain="trainfinder.otenko.com", secure=True)

def warmup():
    """Open the exact map URL (with lat/lng/zm) to set server-side viewport/session."""
    try:
        r = S.get(API_WARM, timeout=20, allow_redirects=True)
        log.info("Warmup GET %s -> %s", API_WARM, r.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

def fetch_raw():
    """POST to the viewport endpoint; site expects an empty form body with proper headers."""
    warmup()
    try:
        r = S.post(API_POST, data=b"", timeout=30)
        log.info("POST %s -> %s", API_POST, r.status_code)
        try:
            js = r.json()
        except Exception:
            log.error("Non-JSON response: %s", r.text[:500])
            return None
        if not js or (isinstance(js, dict) and all(v is None for v in js.values())):
            log.warning("Empty/NULL payload. Check TF_ASPXAUTH / TF_REFERER (zoom/viewport).")
            log.warning("Sample of JSON: %s", str(js)[:400])
            return None
        return js
    except Exception as e:
        log.exception("fetch_raw error: %s", e)
        return None

def extract_trains(js):
    """
    Adjust this once you know TrainFinder's exact JSON schema.
    For now, try common shapes; otherwise return an empty list to keep trains.json valid.
    """
    if isinstance(js, dict):
        # Common patterns worth trying:
        for key in ("trains", "data", "results", "entities"):
            if key in js and isinstance(js[key], list):
                return js[key]
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

# ---------- Flask ----------
app = Flask(__name__)

@app.get("/")
def root():
    return jsonify({"ok": True, "hint": "GET /trains.json, GET /debug, POST /fetch-now"})

@app.get("/debug")
def debug():
    return jsonify({
        "has_cookie": bool(TF_COOKIE),
        "cookie_len": len(TF_COOKIE),
        "referer": TF_REFERER or API_WARM,
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

# ---------- Optional background refresher (every 30s). Disable with ENABLE_REFRESH=0 ----------
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
