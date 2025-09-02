import os
import json
import time
import logging
from typing import Tuple, Dict, Any, List

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

# -----------------------------------------------------------------------------
# Flask setup
# -----------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)  # allow Netlify to call Render

log = logging.getLogger("railops")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:railops:%(message)s")

# -----------------------------------------------------------------------------
# Config from env
# -----------------------------------------------------------------------------
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()      # REQUIRED (from your TF cookie)
TF_UA       = os.getenv("TF_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
TF_REFERER  = os.getenv("TF_REFERER", "")  # optional; if blank we’ll construct it from lat/lng/zm

DEFAULT_LAT = float(os.getenv("TF_DEFAULT_LAT", "-33.8688"))
DEFAULT_LNG = float(os.getenv("TF_DEFAULT_LNG", "151.2093"))
DEFAULT_ZM  = int(os.getenv("TF_DEFAULT_ZM", "10"))

TRAINFINDER_BASE = "https://trainfinder.otenko.com"
VIEW_URL         = f"{TRAINFINDER_BASE}/home/nextlevel"
API_URL          = f"{TRAINFINDER_BASE}/Home/GetViewPortData"

# -----------------------------------------------------------------------------
# Utils
# -----------------------------------------------------------------------------
def build_referer(lat: float, lng: float, zm: int) -> str:
    if TF_REFERER:
        return TF_REFERER
    return f"{VIEW_URL}?lat={lat:.4f}&lng={lng:.4f}&zm={zm}"

def extract_markers(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Try a few known shapes from TrainFinder to produce [{lat,lng,name}]"""
    out: List[Dict[str, Any]] = []

    def add(lat, lng, name=""):
        try:
            lat = float(lat); lng = float(lng)
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                out.append({"lat": lat, "lng": lng, "name": name or ""})
        except Exception:
            pass

    if not isinstance(payload, dict):
        return out

    # atcsObj sometimes appears as a dict with items containing Lat/Lng
    atcs = payload.get("atcsObj")
    if isinstance(atcs, dict):
        for k, v in atcs.items():
            if isinstance(v, dict):
                lat = v.get("Lat") or v.get("lat") or v.get("Latitude")
                lng = v.get("Lng") or v.get("lng") or v.get("Longitude")
                name = v.get("Name") or v.get("name") or str(k)
                if lat is not None and lng is not None:
                    add(lat, lng, name)

    # tts sometimes a list of objects with lat/lng
    tts = payload.get("tts")
    if isinstance(tts, list):
        for v in tts:
            if isinstance(v, dict):
                lat = v.get("lat") or v.get("Lat")
                lng = v.get("lng") or v.get("Lng")
                name = v.get("name") or v.get("Name") or v.get("id") or ""
                if lat is not None and lng is not None:
                    add(lat, lng, name)

    # places may also have coordinates
    places = payload.get("places")
    if isinstance(places, list):
        for v in places:
            if isinstance(v, dict):
                lat = v.get("lat") or v.get("Lat")
                lng = v.get("lng") or v.get("Lng")
                name = v.get("name") or v.get("Name") or ""
                if lat is not None and lng is not None:
                    add(lat, lng, name)

    return out

def fetch_viewport(lat: float, lng: float, zm: int, bbox: str | None) -> Tuple[Dict[str, Any] | None, str, int]:
    """Warm up the view + fetch payload JSON. Returns (json, text, status_code)."""
    if not TF_ASPXAUTH:
        return None, "TF_ASPXAUTH not set", 401

    s = requests.Session()
    # Cookie (no 'httponly' kw — requests doesn't accept it)
    s.cookies.set("TF_ASPXAUTH", TF_ASPXAUTH, domain="trainfinder.otenko.com", path="/", secure=True)

    headers = {
        "User-Agent": TF_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": TRAINFINDER_BASE,
        "Referer": build_referer(lat, lng, zm),
    }

    # Warmup GET helps server set its internal state
    try:
        warm = s.get(build_referer(lat, lng, zm), headers={"User-Agent": TF_UA, "Referer": TRAINFINDER_BASE}, timeout=12)
        log.info("Warmup GET %s -> %s", warm.url, warm.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

    # Main POST
    form = { "lat": f"{lat:.5f}", "lng": f"{lng:.5f}", "zm": str(zm) }
    if bbox:
        form["bbox"] = bbox  # backend ignores it if it doesn’t use it

    try:
        r = s.post(API_URL, data=form, headers=headers, timeout=15)
        log.info("POST %s -> %s", API_URL, r.status_code)
        text = r.text
        if r.status_code != 200:
            return None, text, r.status_code

        # Try parse JSON; TF sometimes returns text/html on auth issues
        try:
            j = r.json()
        except Exception:
            j = None

        return j, text, r.status_code
    except Exception as e:
        return None, f"request error: {e}", 502

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return jsonify(ok=True, service="railops-json", time=int(time.time()))

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/trains")
def trains():
    """
    Returns { ok, markers: [{lat,lng,name}], meta:{...} }
    Accepts query: lat, lng, zm, bbox
    """
    try:
        lat = float(request.args.get("lat", DEFAULT_LAT))
        lng = float(request.args.get("lng", DEFAULT_LNG))
        zm  = int(float(request.args.get("zm", DEFAULT_ZM)))
    except Exception:
        lat, lng, zm = DEFAULT_LAT, DEFAULT_LNG, DEFAULT_ZM

    bbox = request.args.get("bbox")

    j, txt, code = fetch_viewport(lat, lng, zm, bbox)

    if code != 200 or j is None:
        msg = "TrainFinder unreachable" if code >= 500 else "TrainFinder payload looks empty/unauthorized."
        log.warning(msg)
        return jsonify(ok=False, message=msg, status=code), 200  # keep 200 so frontend doesn't break

    markers = extract_markers(j)

    # persist a tiny dump (optional)
    try:
        with open("/app/trains.json", "w") as f:
            json.dump({"ts": int(time.time()), "markers": markers}, f)
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "markers": markers,
        "meta": {
            "source_keys": list(j.keys()) if isinstance(j, dict) else [],
            "count": len(markers)
        }
    }), 200
