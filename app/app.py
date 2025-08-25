import os, json, time, logging, threading, re
import requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, jsonify, request

# ---- Flask app for Gunicorn ----
app = Flask(__name__)
log = logging.getLogger("railops")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# ---- Config (env) ----
RAW_PATH   = "/app/trains.json"
API_POST   = "https://trainfinder.otenko.com/Home/GetViewPortData"
TF_AUTH    = os.getenv("TF_ASPXAUTH", "").strip()
TF_UA      = os.getenv("TF_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/126 Safari/537.36").strip()
# allow users to paste "TF_REFERER=..." by mistake; strip that prefix if present
_ref = os.getenv("TF_REFERER", "https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=7").strip()
TF_REFERER = re.sub(r"^\s*TF_REFERER\s*=\s*", "", _ref)

# ---- HTTP session ----
S = requests.Session()
S.headers.update({
    "User-Agent": TF_UA,
    "Referer": TF_REFERER,
    "Accept": "application/json,text/plain,*/*",
    "Origin": "https://trainfinder.otenko.com",
})
if TF_AUTH:
    S.cookies.set(".ASPXAUTH", TF_AUTH, domain="trainfinder.otenko.com")

def parse_view_from_url(url: str):
    try:
        q = parse_qs(urlparse(url).query)
        lat = (q.get("lat") or ["-33.86"])[0]
        lng = (q.get("lng") or ["151.21"])[0]
        zm  = (q.get("zm")  or ["7"])[0]
        return lat, lng, zm
    except Exception:
        return "-33.86", "151.21", "7"

def env_bounds():
    raw = os.getenv("TF_BOUNDS", "").strip()
    if raw:
        try:
            s, w, n, e = [x.strip() for x in raw.split(",")]
            return s, w, n, e
        except Exception:
            log.warning("Bad TF_BOUNDS; expected 'south,west,north,east'")
    # Australia-wide default (south, west, north, east)
    return "-44.0", "112.0", "-10.0", "154.0"

def warmup():
    # Best-effort GET to seed cookies
    try:
        r = S.get(TF_REFERER, timeout=15)
        log.info("Warmup GET %s -> %s", TF_REFERER, r.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

def fetch_raw():
    warmup()
    lat, lng, zm = parse_view_from_url(TF_REFERER)
    s, w, n, e = env_bounds()

    form = {
        "lat": lat, "lng": lng, "zm": zm,
        # common bbox aliases
        "south": s, "west": w, "north": n, "east": e,
        "minLat": s, "minLng": w, "maxLat": n, "maxLng": e,
        "bbox": f"{s},{w},{n},{e}",
    }

    r = S.post(API_POST, data=form, timeout=30)
    log.info("POST %s (lat=%s,lng=%s,zm=%s,bbox=%s) -> %s",
             API_POST, lat, lng, zm, form["bbox"], r.status_code)
    r.raise_for_status()
    js = r.json()
    if isinstance(js, dict):
        log.info("Sample JSON keys: %s", list(js.keys())[:8])
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(js, f, ensure_ascii=False)
    return js

def refresher_loop():
    interval = int(os.getenv("REFRESH_EVERY_SEC", "30"))
    while True:
        try:
            fetch_raw()
        except Exception as e:
            log.warning("refresher error: %s", e)
        time.sleep(interval)

# ---- Routes ----
@app.get("/")
def root():
    return jsonify(ok=True)

@app.post("/fetch-now")
def fetch_now():
    try:
        js = fetch_raw()
        return jsonify(ok=True, keys=list(js.keys()) if isinstance(js, dict) else None)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@app.get("/raw")
def raw():
    try:
        with open(RAW_PATH, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "application/json"}
    except FileNotFoundError:
        return jsonify(error="no file yet"), 404

# ---- Background thread on boot ----
def _start_bg():
    t = threading.Thread(target=refresher_loop, daemon=True)
    t.start()

_start_bg()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
