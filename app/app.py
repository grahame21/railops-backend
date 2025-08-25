# app/app.py
import os, json, time, logging, threading, requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, jsonify, send_file

# ---------- Logging ----------
logging.basicConfig(
    level=getattr(logging, os.getenv("TF_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("railops")

# ---------- Flask (must be named `app`) ----------
app = Flask(__name__)

# ---------- Env ----------
TF_COOKIE  = os.getenv("TF_ASPXAUTH", "").strip()   # ONLY the value, not ".ASPXAUTH=<...>"
TF_REFERER = os.getenv("TF_REFERER", "").strip()    # e.g. https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=7
TF_UA      = os.getenv("TF_UA", "Mozilla/5.0").strip()

DATA_PATH = "/app/trains.json"
API_WARM  = TF_REFERER or "https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=7"
API_POST  = "https://trainfinder.otenko.com/Home/GetViewPortData"

# ---------- Helpers ----------
def parse_view_from_url(u: str):
    try:
        qs = parse_qs(urlparse(u).query)
        lat = (qs.get("lat") or [None])[0]
        lng = (qs.get("lng") or [None])[0]
        zm  = (qs.get("zm")  or [None])[0]
        return lat, lng, zm
    except Exception as e:
        log.warning("Failed to parse lat/lng/zm from referer: %s", e)
        return None, None, None

# ---------- HTTP session (browser-like) ----------
S = requests.Session()
S.headers.update({
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "user-agent": TF_UA or "Mozilla/5.0",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://trainfinder.otenko.com",
    "referer": TF_REFERER or API_WARM,
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "dnt": "1",
})
if TF_COOKIE:
    S.cookies.set(".ASPXAUTH", TF_COOKIE, domain="trainfinder.otenko.com", secure=True)

def warmup():
    """Open the exact map URL (with lat/lng/zm) to set server-side viewport/session."""
    try:
        r = S.get(API_WARM, timeout=20, allow_redirects=True)
        log.info("Warmup GET %s -> %s", API_WARM, r.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

def fetch_raw():
    """POST including map view parameters parsed from TF_REFERER."""
    warmup()
    lat, lng, zm = parse_view_from_url(API_WARM)
    form = {}
    if lat and lng:
        form.update({"lat": lat, "lng": lng})
    if zm:
        form["zm"] = zm
    try:
        r = S.post(API_POST, data=form or b"", timeout=30)
        log.info("POST %s (form=%s) -> %s", API_POST, form or "{}", r.status_code)
        try:
            js = r.json()
        except Exception:
            log.error("Non-JSON response: %s", r.text[:500])
            return None
        log.info("Sample JSON keys: %s", list(js.keys())[:8] if isinstance(js, dict) else type(js))
        return js
    except Exception as e:
        log.exception("fetch_raw error: %s", e)
        return None

def extract_trains(js):
    """Heuristics until we know the exact schema."""
    if js is None:
        return []
    if isinstance(js, dict):
        merged = []
        for v in js.values():
            if isinstance(v, list):
                merged.extend(v)
        if merged:
            return merged
        for key in ("trains", "vehicles", "results", "data", "entities"):
            if isinstance(js.get(key), list):
                return js[key]
    if isinstance(js, list):
        return js
    return []

def write_trains():
    js = fetch_raw()
    trains = extract_trains(js)
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(trains, f, ensure_ascii=False)
        log.info("wrote %s with %d trains", DATA_PATH, len(trains))
    except Exception as e:
        log.exception("Failed to write trains.json: %s", e)
    return trains

# ---------- Routes ----------
@app.get("/")
def root():
    return jsonify({"ok": True, "hint": "GET /trains.json, GET /debug, POST /fetch-now"})

@app.get("/debug")
def debug():
    lat, lng, zm = parse_view_from_url(API_WARM)
    return jsonify({
        "has_cookie": bool(TF_COOKIE),
        "cookie_len": len(TF_COOKIE),
        "referer": TF_REFERER or API_WARM,
        "ua": TF_UA,
        "parsed": {"lat": lat, "lng": lng, "zm": zm},
    })

@app.post("/fetch-now")
def fetch_now():
    count = len(write_trains())
    return {"ok": True, "count": count}

@app.get("/trains.json")
def serve_trains():
    if not os.path.exists(DATA_PATH):
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
    return send_file(DATA_PATH, mimetype="application/json")

# ---------- Background refresher ----------
def refresher():
    time.sleep(5)
    while True:
        try:
            write_trains()
        except Exception as e:
            # ✅ fixed: close the parenthesis
            log.exception("refresher error: %s", e)
        time.sleep(30)

if os.getenv("ENABLE_REFRESH", "1") == "1":
    threading.Thread(target=refresher, daemon=True).start()
