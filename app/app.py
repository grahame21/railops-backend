# app/app.py
import os, json, time, logging
from pathlib import Path
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify, send_file

APP_ROOT = Path(__file__).resolve().parent
DATA_DIR  = APP_ROOT / "static" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRAINS_JSON_PATH = DATA_DIR / "trains.json"

# ------------ Flask ------------
app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# ------------ Config ------------
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()
UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
DEFAULT_LAT = float(os.getenv("VIEW_LAT", "-34.9285"))   # Adelaide CBD
DEFAULT_LNG = float(os.getenv("VIEW_LNG", "138.6007"))
DEFAULT_ZM  = int(os.getenv("VIEW_ZM", "7"))             # 6-7 tends to work

# Refresh interval for on-demand caching
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "30"))

# ------------ HTTP session ------------
session = requests.Session()
session.headers.update({
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "*/*",
    "Origin": "https://trainfinder.otenko.com",
    "User-Agent": UA_CHROME,
})
if TF_ASPXAUTH:
    session.cookies.set(".ASPXAUTH", TF_ASPXAUTH, domain="trainfinder.otenko.com")

# Helper: warmup + viewport POST
def fetch_viewport(lat: float, lng: float, zm: int) -> dict:
    ref = f"https://trainfinder.otenko.com/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    # Per-request referer
    H = {"Referer": ref}
    # Warmup GET
    g = session.get(ref, timeout=20)
    app.logger.info("Warmup GET %s -> %s", ref, g.status_code)

    # POST to get data
    resp = session.post(
        "https://trainfinder.otenko.com/Home/GetViewPortData",
        data={"lat": lat, "lng": lng, "zm": zm},
        headers=H,
        timeout=25,
    )
    app.logger.info(
        "POST GetViewPortData (lat=%.6f,lng=%.6f,zm=%s) -> %s; bytes=%s; preview=%r",
        lat, lng, zm, resp.status_code, len(resp.text), resp.text[:160]
    )
    resp.raise_for_status()
    # If TF returns text "null", treat as empty dict to avoid JSON error
    if resp.text.strip() == "null":
        return {}
    try:
        return resp.json()
    except Exception as e:
        app.logger.warning("JSON parse failed: %s", e)
        return {}

# Extract your real trains here (adjust if your schema differs)
def transform_tf_payload(tf: dict) -> dict:
    """
    Return { 'updated': ISO8601, 'trains': [ ... ] }
    Put your own extraction logic here. For now, keep raw TF payload too.
    """
    now = datetime.utcnow().isoformat() + "Z"
    # Example: if TF has a key 'tts' or 'places' etc. You’ll refine later.
    return {
        "updated": now,
        "source": "trainfinder",
        "viewport": {},
        "raw": tf,          # keep raw for now so you can see it on disk
        "trains": [],       # fill once you know TF’s markers array shape
    }

def write_trains(data: dict):
    tmp = TRAINS_JSON_PATH.with_suffix(".tmp.json")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(TRAINS_JSON_PATH)

def needs_refresh(path: Path, max_age_seconds: int) -> bool:
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > max_age_seconds

# ---------- Routes ----------
@app.get("/health")
def health():
    return jsonify(ok=True, ts=datetime.utcnow().isoformat()+"Z")

@app.get("/status")
def status():
    info = {
        "ok": True,
        "has_cookie": bool(TF_ASPXAUTH),
        "view": {"lat": DEFAULT_LAT, "lng": DEFAULT_LNG, "zm": DEFAULT_ZM},
        "trains_json_exists": TRAINS_JSON_PATH.exists(),
        "trains_json_mtime": (
            datetime.utcfromtimestamp(TRAINS_JSON_PATH.stat().st_mtime).isoformat()+"Z"
            if TRAINS_JSON_PATH.exists() else None
        ),
        "cache_seconds": CACHE_SECONDS,
    }
    return jsonify(info)

@app.get("/trains.json")
def trains_json():
    """
    Serve cached trains; auto-refresh if file is too old (> CACHE_SECONDS).
    """
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm = int(request.args.get("zm", DEFAULT_ZM))

    if needs_refresh(TRAINS_JSON_PATH, CACHE_SECONDS):
        app.logger.info("Cache expired -> fetching TF viewport")
        tf = fetch_viewport(lat, lng, zm)
        data = transform_tf_payload(tf)
        write_trains(data)
    # Always return file (fresh or cached)
    return send_file(TRAINS_JSON_PATH, mimetype="application/json")

@app.get("/update")
def update_now():
    """
    Force an immediate fetch (useful for manual refresh or CI pings).
    """
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm = int(request.args.get("zm", DEFAULT_ZM))

    tf = fetch_viewport(lat, lng, zm)
    data = transform_tf_payload(tf)
    write_trains(data)
    return jsonify({"ok": True, "wrote": str(TRAINS_JSON_PATH), "counts": {
        "trains": len(data.get("trains", [])),
        "raw_keys": list(data.get("raw", {}).keys()) if isinstance(data.get("raw"), dict) else None
    }})

@app.get("/debug/viewport")
def debug_viewport():
    """
    Raw passthrough of TF response (no transform) – super helpful for seeing real content.
    """
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm  = int(request.args.get("zm", DEFAULT_ZM))
    tf = fetch_viewport(lat, lng, zm)
    return (json.dumps(tf, ensure_ascii=False), 200, {"Content-Type": "application/json"})

# Root
@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "endpoints": ["/health", "/status", "/trains.json", "/update", "/debug/viewport"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
