# app/app.py
import os, json, time, logging, threading, requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, jsonify, send_file

logging.basicConfig(
    level=getattr(logging, os.getenv("TF_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("railops")

app = Flask(__name__)

def _strip_prefix(val: str, prefixes):
    if not isinstance(val, str):
        return val
    v = val.strip()
    for p in prefixes:
        if v.lower().startswith(p.lower()):
            return v[len(p):].lstrip()
    return v

TF_COOKIE  = _strip_prefix(os.getenv("TF_ASPXAUTH", ""), [".ASPXAUTH=", "TF_ASPXAUTH="])
TF_REFERER = _strip_prefix(os.getenv("TF_REFERER", ""), ["TF_REFERER="])
TF_UA      = os.getenv("TF_UA", "Mozilla/5.0").strip()

DATA_PATH = "/app/trains.json"
RAW_PATH  = "/app/raw.json"
API_WARM  = TF_REFERER or "https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=7"
API_POST  = "https://trainfinder.otenko.com/Home/GetViewPortData"

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

S = requests.Session()
S.headers.update({
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "user-agent": TF_UA or "Mozilla/5.0",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://trainfinder.otenko.com",
    "referer": API_WARM,
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "dnt": "1",
})
if TF_COOKIE:
    S.cookies.set(".ASPXAUTH", TF_COOKIE, domain="trainfinder.otenko.com", secure=True)

def warmup():
    try:
        r = S.get(API_WARM, timeout=20, allow_redirects=True)
        log.info("Warmup GET %s -> %s", API_WARM, r.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

def fetch_raw():
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
        if isinstance(js, dict):
            log.info("Sample JSON keys: %s", list(js.keys())[:8])
        else:
            log.info("Top-level JSON type: %s", type(js).__name__)
        try:
            with open(RAW_PATH, "w", encoding="utf-8") as f:
                json.dump(js, f, ensure_ascii=False)
        except Exception as e:
            log.warning("Failed to write raw.json: %s", e)
        return js
    except Exception as e:
        log.exception("fetch_raw error: %s", e)
        return None

# ---- NEW: deep-walk helpers -----------------------------------------------
def _flatten_values(node):
    """Yield every list/dict found anywhere in the JSON tree."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _flatten_values(v)
    elif isinstance(node, list):
        yield node
        for v in node:
            yield from _flatten_values(v)

def _looks_like_train(obj):
    if not isinstance(obj, dict):
        return False
    keys = {k.lower() for k in obj.keys()}
    hints = {"trainid", "tid", "id", "lat", "lng", "lon", "speed", "heading", "name", "service", "operator", "line"}
    return len(keys & hints) >= 2

def extract_trains(js):
    if js is None:
        return []

    # Gather candidate containers
    candidates = []
    if isinstance(js, dict):
        # direct known keys first
        for key in ("tts", "atcsObj", "atcsGomi", "trains", "vehicles", "results", "data", "entities"):
            if key in js:
                candidates.append(js[key])

    # Walk everything and collect dicts/lists
    for node in _flatten_values(js):
        candidates.append(node)

    # From candidates, build a flat list of objects
    items = []
    for c in candidates:
        if isinstance(c, list):
            items.extend([x for x in c if isinstance(x, dict)])
        elif isinstance(c, dict):
            # dict of dicts? take values
            vals = [v for v in c.values() if isinstance(v, (dict, list))]
            for v in vals:
                if isinstance(v, dict):
                    items.append(v)
                elif isinstance(v, list):
                    items.extend([x for x in v if isinstance(x, dict)])

    # Deduplicate (by repr)
    seen = set()
    uniq = []
    for it in items:
        r = repr(sorted(it.items()))
        if r not in seen:
            seen.add(r)
            uniq.append(it)

    # Prefer ones that look train-like; fallback to uniq
    trains = [x for x in uniq if _looks_like_train(x)]
    return trains if trains else uniq[:200]  # cap for safety

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

@app.get("/")
def root():
    return jsonify({"ok": True, "hint": "GET /trains.json, GET /raw, GET /debug, POST /fetch-now"})

@app.get("/debug")
def debug():
    lat, lng, zm = parse_view_from_url(API_WARM)
    return jsonify({
        "has_cookie": bool(TF_COOKIE),
        "cookie_len": len(TF_COOKIE),
        "referer_used": API_WARM,
        "ua": TF_UA,
        "parsed": {"lat": lat, "lng": lng, "zm": zm},
    })

@app.get("/raw")
def raw():
    if os.path.exists(RAW_PATH):
        return send_file(RAW_PATH, mimetype="application/json")
    return jsonify({"note": "no raw yet; POST /fetch-now first"}), 404

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
